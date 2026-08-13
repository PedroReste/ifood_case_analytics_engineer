"""Estatística usada no EDA: bootstrap agrupado por cliente para estimar diferenças de média com IC95%."""

from __future__ import annotations
import pandas as pd

def bootstrap_clustered_mean_difference(
    data: pd.DataFrame,
    *,
    cluster_column: str,
    group_column: str,
    value_column: str,
    group_a: object = True,
    group_b: object = False,
    iterations: int = 2_000,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Estima A-B por bootstrap que reamostra clusters inteiros.
    Cada cliente sorteado entra com todos os seus pedidos elegíveis. Assim, a
    incerteza não trata pedidos do mesmo ``customer_unique_id`` como observações
    independentes. ``group_a`` e ``group_b`` definem a ordem da diferença.
    """
    import numpy as np

    required = {cluster_column, group_column, value_column}
    missing = required.difference(data.columns)
    if missing:
        raise KeyError(f"Colunas ausentes para bootstrap agrupado: {sorted(missing)}")
    if iterations <= 0:
        raise ValueError("iterations precisa ser maior que zero.")

    # Remove apenas linhas inelegíveis para a métrica; não altera a fact usada
    # pelo notebook. A conversão permite outcomes booleanos, como recompra.
    sample = data[[cluster_column, group_column, value_column]].dropna().copy()
    sample = sample[sample[group_column].isin([group_a, group_b])]
    sample[value_column] = pd.to_numeric(sample[value_column], errors="coerce")
    sample = sample.dropna(subset=[value_column])
    if sample.empty:
        raise ValueError("Não há linhas elegíveis para o bootstrap agrupado.")

    # Pré-agregar soma e contagem por cluster torna a reamostragem eficiente e
    # preserva a multiplicidade de todos os pedidos de cada cliente sorteado.
    clusters = pd.Index(sample[cluster_column].unique())
    grouped = sample.groupby([cluster_column, group_column], observed=True)[value_column].agg(["sum", "count"])

    def totals_for(group: object, metric: str) -> np.ndarray:
        try:
            values = grouped.xs(group, level=group_column)[metric]
        except KeyError:
            values = pd.Series(dtype=float)
        return values.reindex(clusters, fill_value=0).to_numpy(dtype=float)

    sums_a, counts_a = totals_for(group_a, "sum"), totals_for(group_a, "count")
    sums_b, counts_b = totals_for(group_b, "sum"), totals_for(group_b, "count")
    if counts_a.sum() == 0 or counts_b.sum() == 0:
        raise ValueError("Os dois grupos precisam conter ao menos uma observação elegível.")

    observed = sums_a.sum() / counts_a.sum() - sums_b.sum() / counts_b.sum()
    rng = np.random.default_rng(seed)

    # A cada iteração: sorteia clientes com reposição e recalcula a diferença de médias.
    raw_diffs = []
    for _ in range(iterations):
        idx = rng.integers(0, len(clusters), size=len(clusters))
        ca, cb = counts_a[idx].sum(), counts_b[idx].sum()
        if ca > 0 and cb > 0:
            raw_diffs.append(sums_a[idx].sum() / ca - sums_b[idx].sum() / cb)

    diffs = np.array(raw_diffs)
    if len(diffs) == 0:
        raise ValueError("Nenhuma reamostra continha os dois grupos.")
    # Iterações descartadas reduzem a confiabilidade do IC; avisa quando excede 5%.
    discarded = iterations - len(diffs)
    if discarded > iterations * 0.05:
        import warnings
        warnings.warn(f"Bootstrap: {discarded}/{iterations} iterações descartadas por grupo ausente na reamostra.")
    return float(observed), float(np.quantile(diffs, 0.025)), float(np.quantile(diffs, 0.975))
