"""Contratos de integração: fonte mínima -> medalhão e gate de qualidade."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ifood_analytics.pipeline import GOLD_TABLES, run
from ifood_analytics.quality import run_quality_checks


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    """Cria as nove fontes do contrato com um pedido entregue reconciliado."""
    source = tmp_path / "source"
    source.mkdir()
    # As colunas espelham o schema Olist: a fixture detecta regressões reais
    # sem carregar arquivos grandes nem depender do diretório data/ local.
    tables = {
        "olist_customers_dataset.csv": [{
            "customer_id": "customer-1", "customer_unique_id": "unique-1",
            "customer_zip_code_prefix": 12345, "customer_city": "sao paulo", "customer_state": "SP",
        }],
        "olist_geolocation_dataset.csv": [{
            "geolocation_zip_code_prefix": 12345, "geolocation_lat": -23.5,
            "geolocation_lng": -46.6, "geolocation_city": "sao paulo", "geolocation_state": "SP",
        }],
        "olist_order_items_dataset.csv": [{
            "order_id": "order-1", "order_item_id": 1, "product_id": "product-1", "seller_id": "seller-1",
            "shipping_limit_date": "2018-01-05 00:00:00", "price": 100.0, "freight_value": 10.0,
        }],
        "olist_order_payments_dataset.csv": [{
            "order_id": "order-1", "payment_sequential": 1, "payment_type": "credit_card",
            "payment_installments": 1, "payment_value": 110.0,
        }],
        "olist_order_reviews_dataset.csv": [{
            "review_id": "review-1", "order_id": "order-1", "review_score": 5,
            "review_comment_title": "otimo", "review_comment_message": "entrega correta",
            "review_creation_date": "2018-01-12 00:00:00", "review_answer_timestamp": "2018-01-13 00:00:00",
        }],
        "olist_orders_dataset.csv": [{
            "order_id": "order-1", "customer_id": "customer-1", "order_status": "delivered",
            "order_purchase_timestamp": "2018-01-01 10:00:00", "order_approved_at": "2018-01-01 11:00:00",
            "order_delivered_carrier_date": "2018-01-02 10:00:00",
            "order_delivered_customer_date": "2018-01-10 10:00:00",
            "order_estimated_delivery_date": "2018-01-12 10:00:00",
        }],
        "olist_products_dataset.csv": [{
            "product_id": "product-1", "product_category_name": "toys", "product_name_lenght": 10,
            "product_description_lenght": 20, "product_photos_qty": 1, "product_weight_g": 500,
            "product_length_cm": 20, "product_height_cm": 10, "product_width_cm": 10,
        }],
        "olist_sellers_dataset.csv": [{
            "seller_id": "seller-1", "seller_zip_code_prefix": 12345,
            "seller_city": "sao paulo", "seller_state": "SP",
        }],
        "product_category_name_translation.csv": [{
            "product_category_name": "toys", "product_category_name_english": "toys",
        }],
    }
    for filename, rows in tables.items():
        pd.DataFrame(rows).to_csv(source / filename, index=False)
    return source


def test_pipeline_materializes_gold_and_preserves_source_rows(source_dir: Path, tmp_path: Path) -> None:
    """O fluxo completo mantém as linhas de origem e entrega as seis tabelas gold."""
    manifest = run(source_dir, tmp_path / "warehouse")

    assert manifest["row_preservation"]["passed"] is True
    assert set(manifest["gold"]) == set(GOLD_TABLES)
    assert all(count == 1 for count in manifest["bronze"].values())
    gold = tmp_path / "warehouse" / "gold"
    assert {path.stem for path in gold.glob("*.parquet")} == set(GOLD_TABLES)
    assert len(pd.read_parquet(gold / "fact_orders.parquet")) == 1
    assert len(pd.read_parquet(gold / "fact_order_items.parquet")) == 1


def test_quality_gate_flags_duplicate_item_grain(source_dir: Path) -> None:
    """Uma chave composta duplicada deve ser sinalizada como falha crítica."""
    items_path = source_dir / "olist_order_items_dataset.csv"
    items = pd.read_csv(items_path)
    pd.concat([items, items], ignore_index=True).to_csv(items_path, index=False)

    checks = {check["check"]: check for check in run_quality_checks(source_dir)}
    item_grain = checks["items.order_id+item_id único e preenchido"]
    assert item_grain["passed"] is False
    assert item_grain["severity"] == "critical"
