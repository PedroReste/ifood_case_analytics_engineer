"""Configurações e contrato dos nove arquivos de origem do case."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

# Contrato de entrada: a carga só começa quando os nove arquivos estão presentes.
SOURCE_FILES: tuple[str, ...] = (
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
)

@dataclass(frozen=True)
class PipelinePaths:
    source: Path
    data: Path

    # As propriedades derivam todos os destinos de um único diretório raiz.
    # Isso evita caminhos globais espalhados pelos scripts e facilita execução local.
    @property
    def bronze(self) -> Path:
        return self.data / "bronze"

    @property
    def silver(self) -> Path:
        return self.data / "silver"

    @property
    def gold(self) -> Path:
        return self.data / "gold"

    @property
    def reports(self) -> Path:
        return self.data / "reports"

    def create(self) -> None:
        """Cria somente os diretórios de saída controlados pelo pipeline."""
        for path in (self.bronze, self.silver, self.gold, self.reports):
            path.mkdir(parents=True, exist_ok=True)
