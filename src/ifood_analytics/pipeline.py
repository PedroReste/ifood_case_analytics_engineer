"""
Pipeline medalhão local: CSV (origem) -> Parquet bronze/silver/gold.
Bronze preserva o conteúdo recebido. 
Silver aplica regras justificadas pelo notebook de qualidade. 
Gold cria tabelas analíticas em granularidades explícitas.
"""

from __future__ import annotations
import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any
import duckdb
import pandas as pd
from .config import PipelinePaths, SOURCE_FILES
from .quality import run_quality_checks

# Mapa explícito de datas por tabela. Colunas não listadas mantêm o tipo inferido
# pela leitura; assim, identificadores e CEPs não são convertidos por engano.
DATE_COLUMNS: dict[str, list[str]] = {
    "orders": [
        "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "order_items": ["shipping_limit_date"],
    "order_reviews": ["review_creation_date", "review_answer_timestamp"],
}

# Contrato de saída gold. Apenas estas relações são exportadas do DuckDB.
GOLD_TABLES: tuple[str, ...] = (
    "fact_orders", "fact_order_items", "mart_monthly_sales",
    "mart_category_performance", "mart_customer_value", "mart_seller_performance",
)

def _first_mode_or_na(values: pd.Series) -> object:
    """Retorna uma moda determinística ou nulo quando o grupo só tem nulos."""
    modes = values.dropna().mode()
    return modes.iat[0] if not modes.empty else pd.NA

def _contract_result(
    name: str, passed: bool, observed: Any, expectation: str, severity: str = "critical"
) -> dict[str, Any]:
    """Mantém contratos pós-gold legíveis no manifesto do pipeline."""
    return {
        "check": name,
        "passed": bool(passed),
        "observed": observed,
        "expectation": expectation,
        "severity": severity,
    }

def table_name(filename: str) -> str:
    """Converte nomes dos CSVs em nomes curtos e estáveis de tabela."""
    return filename.removeprefix("olist_").removesuffix("_dataset.csv").removesuffix(".csv")

def ingest_bronze(paths: PipelinePaths) -> dict[str, int]:
    """Valida o pacote de entrada e copia CSVs sem alteração para bronze."""
    # 1) Valida o pacote completo antes de copiar qualquer arquivo.
    missing = [name for name in SOURCE_FILES if not (paths.source / name).exists()]
    if missing:
        raise FileNotFoundError(f"Arquivos de origem ausentes: {', '.join(missing)}")
    # 2) Copia bytes/metadados sem aplicar limpeza e registra o volume da carga.
    counts: dict[str, int] = {}
    for filename in SOURCE_FILES:
        source = paths.source / filename
        target = paths.bronze / filename
        shutil.copy2(source, target)
        # read_csv contabiliza corretamente campos de texto com quebras de linha (reviews).
        counts[table_name(filename)] = len(pd.read_csv(source, usecols=[0]))
    return counts

def build_silver(paths: PipelinePaths) -> dict[str, int]:
    """Tipa datas e normaliza campos sem remover registros da origem.
    Nulos semânticos são preservados. A categoria ausente recebe 'unknown' para
    evitar perda de receita em agregações, acompanhada por uma flag de nulidade.
    Geolocalização detalhada é preservada; uma tabela adicional por CEP usa
    mediana/moda para consumo analítico sem substituir os registros originais.
    """
    # Cada fonte é tratada isoladamente para manter rastreabilidade 1:1.
    counts: dict[str, int] = {}
    for filename in SOURCE_FILES:
        name = table_name(filename)
        frame = pd.read_csv(paths.bronze / filename, low_memory=False)
        # Tipagem e higiene textual comuns a todas as entidades.
        for column in DATE_COLUMNS.get(name, []):
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
        for column in frame.select_dtypes(include="object"):
            frame[column] = frame[column].str.strip()
        # Regras específicas justificadas no notebook de Data Quality.
        if name == "products":
            frame["is_category_missing"] = frame["product_category_name"].isna()
            frame["product_category_name"] = frame["product_category_name"].fillna("unknown")
        if name == "geolocation":
            geolocation_by_zip = (
                frame.groupby("geolocation_zip_code_prefix", as_index=False)
                .agg(
                    geolocation_lat=("geolocation_lat", "median"),
                    geolocation_lng=("geolocation_lng", "median"),
                    geolocation_city=("geolocation_city", _first_mode_or_na),
                    geolocation_state=("geolocation_state", _first_mode_or_na),
                )
            )
            geolocation_by_zip.to_parquet(paths.silver / "geolocation_by_zip.parquet", index=False)
            counts["geolocation_by_zip"] = len(geolocation_by_zip)
        frame.to_parquet(paths.silver / f"{name}.parquet", index=False)
        counts[name] = len(frame)
    return counts

def _publish_gold(staging: Path, target: Path) -> None:
    """Troca a camada gold somente após todos os Parquets estarem prontos.
    A publicação usa diretórios irmãos para que uma falha durante a geração
    preserve a gold anterior. Em caso de erro na troca, o backup é restaurado.
    """
    backup = target.parent / ".gold-backup"
    if backup.exists():
        shutil.rmtree(backup)
    target_existed = target.exists()
    try:
        if target_existed:
            target.replace(backup)
        staging.replace(target)
    except Exception:
        if target_existed and backup.exists() and not target.exists():
            backup.replace(target)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if backup.exists() and target.exists():
            shutil.rmtree(backup, ignore_errors=True)

def build_gold(paths: PipelinePaths) -> dict[str, int]:
    """Materializa fatos e marts de negócio com SQL DuckDB e publica por staging."""
    # Carrega o modelo SQL e injeta somente o diretório silver normalizado.
    sql_file = Path(__file__).parents[2] / "sql" / "gold.sql"
    sql = sql_file.read_text(encoding="utf-8").replace("${SILVER}", paths.silver.as_posix())
    connection = duckdb.connect()
    staging = Path(tempfile.mkdtemp(prefix=".gold-staging-", dir=paths.data))
    # Exporta primeiro para uma área isolada; a gold em produção não é tocada
    # até que todas as seis relações tenham sido materializadas com sucesso.
    counts: dict[str, int] = {}
    try:
        connection.execute(sql)
        for name in GOLD_TABLES:
            frame = connection.execute(f'SELECT * FROM "{name}"').fetch_df()
            frame.to_parquet(staging / f"{name}.parquet", index=False)
            counts[name] = len(frame)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        connection.close()
    # Contratos são avaliados ainda no staging: uma modelagem inválida não
    # substitui a gold anterior apenas para então falhar na orquestração.
    try:
        staged_contracts = validate_gold_contracts(paths, gold_path=staging)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if any(item["severity"] == "critical" and not item["passed"] for item in staged_contracts):
        shutil.rmtree(staging, ignore_errors=True)
        raise ValueError("Falha em contrato gold durante a publicação por staging.")
    _publish_gold(staging, paths.gold)
    return counts

def validate_gold_contracts(
    paths: PipelinePaths, gold_path: Path | None = None
) -> list[dict[str, Any]]:
    """Valida grão e reconciliação de receita após os joins da camada gold."""
    # Esses contratos bloqueiam fan-out silencioso mesmo se uma nova fonte
    # introduzir duplicidade numa dimensão usada pelos LEFT JOINs do modelo SQL.
    gold = gold_path or paths.gold
    orders = pd.read_parquet(paths.silver / "orders.parquet")
    items = pd.read_parquet(paths.silver / "order_items.parquet")
    fact_orders = pd.read_parquet(gold / "fact_orders.parquet")
    fact_items = pd.read_parquet(gold / "fact_order_items.parquet")
    expected_files = {f"{name}.parquet" for name in GOLD_TABLES}
    observed_files = {path.name for path in gold.glob("*.parquet")}
    order_grain_ok = (
        len(fact_orders) == len(orders)
        and fact_orders.order_id.notna().all()
        and not fact_orders.order_id.duplicated().any()
    )
    item_grain_ok = (
        len(fact_items) == len(items)
        and fact_items[["order_id", "order_item_id"]].notna().all(axis=1).all()
        and not fact_items.duplicated(["order_id", "order_item_id"]).any()
    )
    fact_item_revenue = float(fact_items.price.sum())
    fact_order_revenue = float(fact_orders.item_revenue.sum())
    return [
        _contract_result(
            "gold contém todas as relações esperadas",
            expected_files == observed_files,
            {"missing": sorted(expected_files - observed_files), "unexpected": sorted(observed_files - expected_files)},
            "exatamente as seis relações gold declaradas",
        ),
        _contract_result(
            "gold fact_orders preserva grão de pedido",
            order_grain_ok,
            {"source_rows": len(orders), "fact_rows": len(fact_orders), "duplicate_order_ids": int(fact_orders.order_id.duplicated().sum())},
            "uma linha única por order_id e mesma contagem da silver.orders",
        ),
        _contract_result(
            "gold fact_order_items preserva grão de item",
            item_grain_ok,
            {"source_rows": len(items), "fact_rows": len(fact_items), "duplicate_item_keys": int(fact_items.duplicated(["order_id", "order_item_id"]).sum())},
            "uma linha única por (order_id, order_item_id) e mesma contagem da silver.order_items",
        ),
        _contract_result(
            "GMV de itens reconcilia entre fatos gold",
            abs(fact_item_revenue - fact_order_revenue) < 0.01,
            {"fact_order_items_price": round(fact_item_revenue, 2), "fact_orders_item_revenue": round(fact_order_revenue, 2)},
            "diferença absoluta menor que R$ 0,01",
        ),
    ]

def run(source: Path, data: Path) -> dict[str, object]:
    """Executa todas as camadas e falha caso uma regra crítica de DQ não passe."""
    # Orquestração: caminhos -> bronze -> gate de DQ -> silver -> gold -> manifesto.
    paths = PipelinePaths(source=source.resolve(), data=data.resolve())
    paths.create()
    manifest: dict[str, object] = {"bronze": ingest_bronze(paths)}
    quality = run_quality_checks(paths.bronze, paths.reports / "data_quality.json")
    if any(item["severity"] == "critical" and not item["passed"] for item in quality):
        raise ValueError("Falha em regra crítica. Consulte data/reports/data_quality.json")
    manifest["silver"] = build_silver(paths)
    # Contrato de preservação: toda entidade de origem deve manter o mesmo
    # número de linhas na silver. Tabelas derivadas, como geolocation_by_zip,
    # são adicionais e não substituem o detalhe.
    row_differences = {
        name: manifest["silver"][name] - manifest["bronze"][name]
        for name in manifest["bronze"]
    }
    if any(row_differences.values()):
        raise ValueError(f"Silver não preservou linhas da bronze: {row_differences}")
    manifest["row_preservation"] = {"passed": True, "differences": row_differences}
    manifest["gold"] = build_gold(paths)
    gold_contracts = validate_gold_contracts(paths)
    if any(item["severity"] == "critical" and not item["passed"] for item in gold_contracts):
        raise ValueError("Falha em contrato gold. Consulte a execução e os dados da camada gold.")
    manifest["gold_contracts"] = gold_contracts
    manifest["quality_checks"] = quality
    (paths.reports / "pipeline_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest

def main() -> None:
    """Interface de linha de comando do pipeline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Diretório dos 9 CSVs")
    parser.add_argument("--data", type=Path, default=Path("data"), help="Diretório de saída")
    args = parser.parse_args()
    result = run(args.source, args.data)
    print(json.dumps({key: value if key != "quality_checks" else "ver relatório" for key, value in result.items()}, indent=2))

if __name__ == "__main__":
    main()
