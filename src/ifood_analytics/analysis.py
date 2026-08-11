"""Métricas usadas no EDA e na recomendação executiva."""

from __future__ import annotations

import pandas as pd


def bootstrap_mean_difference(
    values_a: pd.Series, values_b: pd.Series, *, iterations: int = 2_000, seed: int = 42
) -> tuple[float, float, float]:
    """Estima diferença de médias e IC95% por bootstrap reprodutível."""
    # NumPy é importado localmente porque este módulo possui uma única rotina
    # estatística e o carregamento pode ser evitado em fluxos que não usam EDA.
    import numpy as np

    # Higieniza entradas e falha cedo: bootstrap de amostra vazia não é definido.
    rng = np.random.default_rng(seed)
    a, b = values_a.dropna().to_numpy(), values_b.dropna().to_numpy()
    if len(a) == 0 or len(b) == 0:
        raise ValueError("As duas amostras precisam conter ao menos um valor não nulo.")
    # Cada iteração reamostra os dois grupos de forma independente e calcula A-B.
    diffs = [rng.choice(a, len(a), replace=True).mean() - rng.choice(b, len(b), replace=True).mean() for _ in range(iterations)]
    return float(a.mean() - b.mean()), float(np.quantile(diffs, 0.025)), float(np.quantile(diffs, 0.975))


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
    diffs = np.empty(iterations, dtype=float)
    batch_size = 25
    for start in range(0, iterations, batch_size):
        batch = min(batch_size, iterations - start)
        draws = rng.integers(0, len(clusters), size=(batch, len(clusters)))
        sampled_counts_a = counts_a[draws].sum(axis=1)
        sampled_counts_b = counts_b[draws].sum(axis=1)
        # Os grupos existem na amostra original; ainda assim, protege contra a
        # rara reamostra que não contenha um deles.
        valid = (sampled_counts_a > 0) & (sampled_counts_b > 0)
        batch_diffs = np.full(batch, np.nan)
        batch_diffs[valid] = (
            sums_a[draws][valid].sum(axis=1) / sampled_counts_a[valid]
            - sums_b[draws][valid].sum(axis=1) / sampled_counts_b[valid]
        )
        diffs[start : start + batch] = batch_diffs

    diffs = diffs[~np.isnan(diffs)]
    if len(diffs) == 0:
        raise ValueError("Nenhuma reamostra continha os dois grupos.")
    return float(observed), float(np.quantile(diffs, 0.025)), float(np.quantile(diffs, 0.975))
