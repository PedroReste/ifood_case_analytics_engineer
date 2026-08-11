"""Resumo executivo por LLM com fallback determinístico e sem expor dados pessoais.

O script envia somente métricas agregadas. Se OPENAI_API_KEY não estiver definida,
gera um resumo local para manter o case totalmente reprodutível.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

import pandas as pd


GOLD_MARTS: dict[str, set[str]] = {
    "mart_monthly_sales.parquet": {"order_month", "revenue"},
    "mart_category_performance.parquet": {"category", "revenue", "avg_review_score"},
    "mart_seller_performance.parquet": {"seller_id", "revenue"},
}


def _load_gold_marts(data: Path) -> dict[str, pd.DataFrame]:
    """Carrega e valida os marts mínimos antes de montar o payload agregado."""
    # A validação antecede qualquer cálculo para trocar erros pouco claros de
    # leitura/divisão por uma instrução acionável ao usuário do case.
    gold = data / "gold"
    missing_files = [name for name in GOLD_MARTS if not (gold / name).exists()]
    if missing_files:
        raise ValueError(
            "Camada gold ausente ou incompleta "
            f"({', '.join(missing_files)}). Execute o pipeline antes de gerar o resumo."
        )

    marts = {name: pd.read_parquet(gold / name) for name in GOLD_MARTS}
    empty_marts = [name for name, frame in marts.items() if frame.empty]
    if empty_marts:
        raise ValueError(
            "Camada gold vazia "
            f"({', '.join(empty_marts)}). Execute o pipeline com uma fonte contendo pedidos elegíveis."
        )

    invalid_schema = {
        name: sorted(columns - set(marts[name].columns))
        for name, columns in GOLD_MARTS.items()
        if columns - set(marts[name].columns)
    }
    if invalid_schema:
        raise ValueError(f"Contrato gold inválido: colunas ausentes em {invalid_schema}.")
    return marts


def collect_metrics(data: Path) -> dict[str, object]:
    """Seleciona apenas agregados gold necessários ao contexto do resumo."""
    # Carrega somente três marts agregados; facts e dados no nível do cliente
    # nunca entram no payload enviado ao modelo.
    marts = _load_gold_marts(data)
    monthly = marts["mart_monthly_sales.parquet"]
    categories = marts["mart_category_performance.parquet"]
    sellers = marts["mart_seller_performance.parquet"]
    seller_revenue = float(sellers.revenue.sum())
    return {
        "period": [str(monthly.order_month.min()), str(monthly.order_month.max())],
        "revenue": round(float(monthly.revenue.sum()), 2),
        "top_categories": categories.nlargest(5, "revenue")[["category", "revenue", "avg_review_score"]].to_dict("records"),
        "seller_top10_share": round(
            float(sellers.nlargest(max(1, math.ceil(len(sellers) * 0.10)), "revenue").revenue.sum() / seller_revenue),
            4,
        ) if seller_revenue else 0.0,
    }


def local_summary(metrics: dict[str, object]) -> str:
    """Fallback explícito quando não há credencial/API disponível."""
    # Formatação brasileira mantém o output local pronto para leitura executiva.
    categories = metrics.get("top_categories", [])
    if not categories:
        return (
            "Não há categorias com receita na camada gold para produzir um resumo executivo. "
            "Revise o período e os filtros de elegibilidade antes de tomar decisões."
        )
    top = categories[0]
    brl = lambda value: f"{value:,.2f}".translate(str.maketrans({",": ".", ".": ","}))
    seller_share = f"{float(metrics.get('seller_top10_share', 0)):.1%}".replace(".", ",")
    return (
        f"A base soma R$ {brl(float(metrics.get('revenue', 0)))} em GMV de itens. "
        f"A categoria líder é {top.get('category', 'não informada')} (R$ {brl(float(top.get('revenue', 0)))}). "
        f"Os 10% maiores sellers concentram {seller_share} do GMV. "
        "Priorize disponibilidade nas categorias líderes, confiabilidade logística e desenvolvimento da cauda de sellers."
    )


def summarize(data: Path) -> str:
    """Chama a Responses API quando configurada; caso contrário usa fallback local."""
    metrics = collect_metrics(data)
    # Ausência de chave é um caminho suportado, não uma falha de execução.
    if not os.getenv("OPENAI_API_KEY"):
        return local_summary(metrics)
    from openai import OpenAI

    # O prompt limita tamanho e proíbe inferência causal; OPENAI_MODEL permite
    # trocar o modelo sem alterar ou versionar novamente o código.
    response = OpenAI().responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        instructions="Você é um analista executivo. Resuma em português, em até 120 palavras, sem inventar causalidade.",
        input=json.dumps(metrics, ensure_ascii=False),
    )
    return response.output_text


def main() -> None:
    """CLI para imprimir e salvar o resumo versionável."""
    # Argumentos mantêm o script reutilizável para diferentes diretórios de dados.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("data/reports/ai_summary.md"))
    args = parser.parse_args()
    text = summarize(args.data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
