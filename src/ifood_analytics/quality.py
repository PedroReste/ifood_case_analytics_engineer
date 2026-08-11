"""Suite automatizada e reutilizável de qualidade dos dados bronze."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


# Contratos explícitos evitam que uma mudança de schema chegue à silver como um
# KeyError pouco informativo. Cada tabela deve chegar com o conjunto exato abaixo.
EXPECTED_COLUMNS: dict[str, set[str]] = {
    "olist_customers_dataset.csv": {"customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"},
    "olist_geolocation_dataset.csv": {"geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state"},
    "olist_order_items_dataset.csv": {"order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"},
    "olist_order_payments_dataset.csv": {"order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"},
    "olist_order_reviews_dataset.csv": {"review_id", "order_id", "review_score", "review_comment_title", "review_comment_message", "review_creation_date", "review_answer_timestamp"},
    "olist_orders_dataset.csv": {"order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"},
    "olist_products_dataset.csv": {"product_id", "product_category_name", "product_name_lenght", "product_description_lenght", "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"},
    "olist_sellers_dataset.csv": {"seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"},
    "product_category_name_translation.csv": {"product_category_name", "product_category_name_english"},
}

# Toda chave usada por join ou declarada como grão deve ser única antes da gold.
KEY_CONTRACTS: dict[str, tuple[str, list[str]]] = {
    "orders.order_id": ("olist_orders_dataset.csv", ["order_id"]),
    "customers.customer_id": ("olist_customers_dataset.csv", ["customer_id"]),
    "items.order_id+item_id": ("olist_order_items_dataset.csv", ["order_id", "order_item_id"]),
    "payments.order_id+sequence": ("olist_order_payments_dataset.csv", ["order_id", "payment_sequential"]),
    "products.product_id": ("olist_products_dataset.csv", ["product_id"]),
    "sellers.seller_id": ("olist_sellers_dataset.csv", ["seller_id"]),
    "translation.category": ("product_category_name_translation.csv", ["product_category_name"]),
}

ORDER_DATE_COLUMNS = [
    "order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
    "order_delivered_customer_date", "order_estimated_delivery_date",
]


def _result(name: str, passed: bool, observed: Any, expectation: str, severity: str = "critical") -> dict[str, Any]:
    """Padroniza o contrato pass/fail usado no relatório JSON."""
    return {"check": name, "passed": bool(passed), "observed": observed, "expectation": expectation, "severity": severity}


def _write_report(checks: list[dict[str, Any]], output: Path | None) -> None:
    """Persiste o relatório mesmo quando o schema impede checks posteriores."""
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(checks, indent=2, ensure_ascii=False), encoding="utf-8")


def run_quality_checks(bronze: Path, output: Path | None = None) -> list[dict[str, Any]]:
    """Executa checks de completude, unicidade, domínio, FK, outlier e datas."""
    # Leitura bruta centralizada mantém as regras independentes da silver.
    frames = {name: pd.read_csv(bronze / name, low_memory=False) for name in EXPECTED_COLUMNS}
    schema_checks = [
        _result(
            f"schema {name}",
            set(frame.columns) == expected,
            {"missing": sorted(expected - set(frame.columns)), "unexpected": sorted(set(frame.columns) - expected)},
            "colunas exatamente iguais ao contrato",
        )
        for name, expected in EXPECTED_COLUMNS.items()
        for frame in [frames[name]]
    ]
    if any(not check["passed"] for check in schema_checks):
        _write_report(schema_checks, output)
        return schema_checks

    orders_raw = frames["olist_orders_dataset.csv"]
    orders = orders_raw.copy()
    parse_failures: dict[str, int] = {}
    for column in ORDER_DATE_COLUMNS:
        parsed = pd.to_datetime(orders_raw[column], errors="coerce")
        parse_failures[column] = int((orders_raw[column].notna() & parsed.isna()).sum())
        orders[column] = parsed
    customers = frames["olist_customers_dataset.csv"]
    items = frames["olist_order_items_dataset.csv"]
    payments = frames["olist_order_payments_dataset.csv"]
    products = frames["olist_products_dataset.csv"]
    sellers = frames["olist_sellers_dataset.csv"]
    reviews = frames["olist_order_reviews_dataset.csv"]
    geolocation = frames["olist_geolocation_dataset.csv"]
    # Domínios e subconjuntos temporais usados pelos checks críticos.
    valid_status = {"approved", "canceled", "created", "delivered", "invoiced", "processing", "shipped", "unavailable"}
    delivered = orders[orders.order_status.eq("delivered")]
    delivered_with_date = delivered.dropna(subset=["order_delivered_customer_date"])
    approved_with_date = orders.dropna(subset=["order_approved_at"])

    # Tukey extremo (3 IQR) sinaliza caudas para monitoramento, sem excluir vendas
    # legítimas. A regra avalia prevalência, não a existência isolada de extremos.
    extreme_counts: dict[str, int] = {}
    extreme_mask = pd.Series(False, index=items.index)
    for column in ("price", "freight_value"):
        q1, q3 = items[column].quantile([0.25, 0.75])
        upper = q3 + 3 * (q3 - q1)
        column_mask = items[column] > upper
        extreme_counts[column] = int(column_mask.sum())
        extreme_mask |= column_mask

    # Reconciliação acontece somente após agregar ambos os lados por pedido,
    # impedindo que pagamentos e itens múltiplos criem um produto cartesiano.
    payment_by_order = payments.groupby("order_id", as_index=False).payment_value.sum()
    item_by_order = items.groupby("order_id", as_index=False).agg(
        item_value=("price", "sum"), freight_value=("freight_value", "sum")
    )
    reconciliation = payment_by_order.merge(item_by_order, on="order_id", how="outer", indicator=True)
    comparable = reconciliation[reconciliation["_merge"].eq("both")].copy()
    comparable["difference"] = (
        comparable.payment_value - comparable.item_value - comparable.freight_value
    ).abs()
    mismatch_rate = float(comparable.difference.gt(0.01).mean()) if len(comparable) else 0.0
    reconciliation_observed = {
        "only_payments": int(reconciliation["_merge"].eq("left_only").sum()),
        "only_items": int(reconciliation["_merge"].eq("right_only").sum()),
        "comparable_orders": len(comparable),
        "value_mismatches": int(comparable.difference.gt(0.01).sum()),
        "mismatch_rate_comparable": round(mismatch_rate, 4),
    }
    # Contrato final: críticos protegem chaves/semântica; warnings tornam caudas
    # observáveis sem descartar registros comercialmente plausíveis.
    key_checks = [
        _result(
            f"{name} único e preenchido",
            not frames[table].duplicated(columns).any() and not frames[table][columns].isna().any(axis=1).any(),
            {"duplicates": int(frames[table].duplicated(columns).sum()), "null_keys": int(frames[table][columns].isna().any(axis=1).sum())},
            "0 duplicatas e 0 chaves nulas",
        )
        for name, (table, columns) in KEY_CONTRACTS.items()
    ]
    checks = schema_checks + key_checks + [
        _result("orders.customer_id preenchido", orders.customer_id.notna().all(), int(orders.customer_id.isna().sum()), "0 nulos"),
        _result("datas de pedidos parseáveis", not any(parse_failures.values()), parse_failures, "0 falhas de parsing em datas não nulas"),
        _result("status dentro do domínio", set(orders.order_status) <= valid_status, sorted(set(orders.order_status) - valid_status), "somente status conhecidos"),
        _result("FK orders -> customers", orders.customer_id.isin(customers.customer_id).all(), int((~orders.customer_id.isin(customers.customer_id)).sum()), "0 órfãos"),
        _result("FK items -> orders", items.order_id.isin(orders.order_id).all(), int((~items.order_id.isin(orders.order_id)).sum()), "0 órfãos"),
        _result("FK items -> products", items.product_id.isin(products.product_id).all(), int((~items.product_id.isin(products.product_id)).sum()), "0 órfãos"),
        _result("FK items -> sellers", items.seller_id.isin(sellers.seller_id).all(), int((~items.seller_id.isin(sellers.seller_id)).sum()), "0 órfãos"),
        _result("FK payments -> orders", payments.order_id.isin(orders.order_id).all(), int((~payments.order_id.isin(orders.order_id)).sum()), "0 órfãos"),
        _result("FK reviews -> orders", reviews.order_id.isin(orders.order_id).all(), int((~reviews.order_id.isin(orders.order_id)).sum()), "0 órfãos"),
        _result("preço e frete não negativos", ((items.price >= 0) & (items.freight_value >= 0)).all(), int(((items.price < 0) | (items.freight_value < 0)).sum()), "0 valores negativos"),
        _result("review_score entre 1 e 5", reviews.review_score.between(1, 5).all(), int((~reviews.review_score.between(1, 5)).sum()), "0 fora do intervalo"),
        _result("aprovação após compra", (approved_with_date.order_approved_at >= approved_with_date.order_purchase_timestamp).all(), int((approved_with_date.order_approved_at < approved_with_date.order_purchase_timestamp).sum()), "0 inconsistências entre datas disponíveis"),
        _result("entrega após compra", (delivered_with_date.order_delivered_customer_date >= delivered_with_date.order_purchase_timestamp).all(), int((delivered_with_date.order_delivered_customer_date < delivered_with_date.order_purchase_timestamp).sum()), "0 inconsistências entre datas disponíveis"),
        _result("pedido entregue possui data de entrega", delivered.order_delivered_customer_date.notna().mean() > 0.999, round(float(delivered.order_delivered_customer_date.isna().mean()), 5), "mais de 99,9% preenchido; nulos preservados", "warning"),
        _result("categoria ausente monitorada", products.product_category_name.isna().mean() < 0.03, round(float(products.product_category_name.isna().mean()), 4), "menos de 3%; preencher como unknown", "warning"),
        _result("outliers extremos de preço/frete monitorados", extreme_mask.mean() < 0.05, {**extreme_counts, "row_rate": round(float(extreme_mask.mean()), 4)}, "menos de 5% das linhas acima de Q3 + 3*IQR; preservar e monitorar", "warning"),
        _result("coordenadas em faixa geográfica plausível", geolocation.geolocation_lat.between(-35, 6).all() and geolocation.geolocation_lng.between(-75, -30).all(), int((~geolocation.geolocation_lat.between(-35, 6) | ~geolocation.geolocation_lng.between(-75, -30)).sum()), "0 coordenadas fora da faixa ampla do Brasil", "warning"),
        _result("pagamentos reconciliam itens + frete", mismatch_rate < 0.02 and reconciliation_observed["only_payments"] == 0 and reconciliation_observed["only_items"] == 0, reconciliation_observed, "0 pedidos em apenas um lado e menos de 2% de divergência acima de R$ 0,01", "warning"),
    ]
    # O mesmo objeto retorna ao pipeline e, opcionalmente, vira relatório JSON.
    _write_report(checks, output)
    return checks
