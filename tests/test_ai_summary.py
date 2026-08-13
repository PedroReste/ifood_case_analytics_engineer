"""Contratos do resumo executivo local e do pré-requisito da camada gold."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ifood_analytics.ai_summary import collect_metrics, local_summary


def test_collect_metrics_explains_missing_gold(tmp_path: Path) -> None:
    """Ausência dos marts deve orientar a execução do pipeline, sem KeyError."""
    with pytest.raises(ValueError, match="Camada gold ausente ou incompleta"):
        collect_metrics(tmp_path / "data")


def test_collect_metrics_explains_empty_gold(tmp_path: Path) -> None:
    """Marts vazios devem bloquear um resumo que teria conclusões artificiais."""
    gold = tmp_path / "data" / "gold"
    gold.mkdir(parents=True)
    pd.DataFrame(columns=["order_month", "revenue"]).to_parquet(gold / "mart_monthly_sales.parquet")
    pd.DataFrame(columns=["category", "revenue", "avg_review_score"]).to_parquet(gold / "mart_category_performance.parquet")
    pd.DataFrame(columns=["seller_id", "revenue"]).to_parquet(gold / "mart_seller_performance.parquet")

    with pytest.raises(ValueError, match="Camada gold vazia"):
        collect_metrics(tmp_path / "data")


def test_collect_metrics_uses_only_aggregated_gold_marts(tmp_path: Path) -> None:
    """O payload local calcula métricas sem precisar carregar fatos ou PII."""
    gold = tmp_path / "data" / "gold"
    gold.mkdir(parents=True)
    pd.DataFrame([{"order_month": "2018-01-01", "revenue": 250.0}]).to_parquet(
        gold / "mart_monthly_sales.parquet"
    )
    pd.DataFrame([{"category": "toys", "revenue": 250.0, "avg_review_score": 4.5}]).to_parquet(
        gold / "mart_category_performance.parquet"
    )
    pd.DataFrame([{"seller_id": "seller-1", "revenue": 250.0}]).to_parquet(
        gold / "mart_seller_performance.parquet"
    )

    metrics = collect_metrics(tmp_path / "data")
    assert metrics["revenue"] == 250.0
    assert metrics["top_categories"][0]["category"] == "toys"
    assert metrics["seller_top10_share"] == 1.0


def test_local_summary_handles_empty_categories() -> None:
    """O fallback segue seguro mesmo se chamado diretamente com payload vazio."""
    summary = local_summary({"top_categories": []})
    assert "Não há categorias" in summary
