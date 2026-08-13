# Data quality report — execução de referência

Execução sobre os nove CSVs Olist fornecidos. O arquivo estruturado é recriado em `data/reports/data_quality.json` a cada execução; este documento registra a leitura humana da execução de referência.

Foram executados **34 checks**: 31 críticos (todos aprovados) e três warnings, que permanecem visíveis sem descartar nenhum registro.

| Dimensão | Verificações | Resultado da referência |
|---|---|---|
| Schema | Conjunto exato de colunas das 9 fontes | Pass; mudança de coluna agora gera relatório DQ legível antes da silver |
| Grain e chaves | 7 chaves de negócio/dimensões, incluindo `(order_id, order_item_id)` e `(order_id, payment_sequential)` | Pass; zero duplicatas e chaves nulas |
| Domínios | status, review 1–5, preço/frete não negativos | Pass |
| Integridade referencial | orders→customers; items→orders/products/sellers; payments/reviews→orders | Pass; zero órfãos |
| Temporal | parsing, aprovação e entrega posteriores à compra | Pass para datas disponíveis |
| Outliers | Tukey extremo em preço/frete | Warning: 7,41% das linhas; são preservadas e monitoradas, não removidas |
| Geografia | coordenadas em faixa ampla do Brasil | Warning: 29 coordenadas fora da faixa; mantidas para investigação |
| Reconciliação | pagamentos versus itens + frete, por pedido | Warning: 775 pedidos somente em pagamentos, 1 somente em itens e 417 divergências monetárias entre 98.665 pedidos comparáveis (0,42%) |
| Completude de produto | categoria ausente | Pass como limiar monitorado: 1,85%; flag preservada e valor analítico `unknown` na silver |

## Decisões de tratamento

- Checks críticos interrompem o pipeline; warnings apenas tornam risco e oportunidade de melhoria observáveis.
- Nenhuma linha é removida entre bronze e silver. O manifesto registra diferença zero nas nove entidades de origem.
- A bronze é uma cópia fiel dos CSVs. A silver apenas tipa datas, normaliza espaços de texto e adiciona atributos derivados rastreáveis.
- Categorias ausentes recebem `is_category_missing = true` antes de `unknown`; a ausência original continua disponível para análise.
- As 261.831 linhas totalmente duplicadas de geolocalização permanecem em `geolocation.parquet`. A visão adicional `geolocation_by_zip.parquet` usa mediana por CEP e moda segura para cidade/UF, sem substituir o detalhe.
- Reviews sem texto e datas condicionais ao status permanecem nulos; não há imputação que invente uma entrega ou comentário.
- Valores extremos são preservados: a fonte não oferece um limite de negócio que prove erro, e removê-los alteraria o GMV observado.
- A reconciliação (reconciliation) usa `outer join` após agregar cada lado por `order_id`. Assim, pedidos presentes em somente uma fonte não são escondidos pelo universo comparável.

Além do gate pré-silver, a execução valida a gold: existem exatamente seis relações publicadas, `fact_orders` mantém uma linha por `order_id`, `fact_order_items` uma por `(order_id, order_item_id)`, e o GMV de itens reconcilia entre as duas facts.

