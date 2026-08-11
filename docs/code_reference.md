# Referência técnica do repositório

Este guia documenta a finalidade de cada arquivo executável e de seus blocos lógicos. Os scripts também possuem docstrings e comentários próximos da regra que explicam o motivo do tratamento. A estrutura é intencionalmente pequena para caber no prazo do case, mas conserva os controles essenciais de um pipeline analítico.

## `src/ifood_analytics/config.py`

- **`SOURCE_FILES`**: contrato nominal dos nove CSVs obrigatórios, em ordem determinística. Uma carga sem algum deles falha antes de escrever a bronze.
- **`PipelinePaths`**: recebe somente a origem e a raiz de dados; as propriedades derivam `bronze/`, `silver/`, `gold/` e `reports/`.
- **`create()`**: cria apenas diretórios de saída que pertencem ao pipeline. A origem nunca é alterada.

## `src/ifood_analytics/quality.py`

- **`EXPECTED_COLUMNS`**: schema exato de cada fonte. Esse bloco converte uma coluna ausente/inesperada em um relatório de DQ claro, em vez de um `KeyError` posterior.
- **`KEY_CONTRACTS`**: declara sete grãos/chaves usados pelos joins: pedido, customer, item composto, pagamento composto, produto, seller e tradução de categoria.
- **`ORDER_DATE_COLUMNS`**: concentra as cinco datas de pedido cuja conversão é auditada.
- **`_result()` e `_write_report()`**: padronizam e persistem o contrato `check/passed/observed/expectation/severity`, inclusive quando um erro de schema interrompe os checks seguintes.
- **Leitura e schema**: carrega as nove tabelas bronze, compara conjuntos de colunas e retorna cedo somente quando o contrato de schema impede uma análise segura.
- **Datas, domínios e FKs**: faz parsing não destrutivo, verifica status conhecidos, relações referenciais, valores não negativos, score de review e ordem temporal das etapas.
- **Outliers**: calcula Tukey extremo (`Q3 + 3×IQR`) em preço/frete. Mede prevalência para monitoramento; não elimina nem winsoriza valores.
- **Reconciliação**: agrega pagamentos e itens por `order_id`, aplica `outer join`, separa pedidos presentes em um único lado das diferenças monetárias comparáveis e registra ambos no warning.
- **Lista de checks**: 31 regras críticas bloqueiam a silver; warnings tornam caudas e anomalias toleradas observáveis sem apagar dados.

## `src/ifood_analytics/pipeline.py`

- **`DATE_COLUMNS`**: mapeia apenas campos que devem virar `datetime`, evitando conversão acidental de IDs e CEPs.
- **`GOLD_TABLES`**: contrato fechado das seis relações permitidas na saída gold.
- **`_first_mode_or_na()`**: calcula moda de cidade/UF por CEP e devolve nulo se o grupo futuro for inteiramente nulo; evita falha de indexação.
- **`_contract_result()`**: formata checks pós-gold no mesmo estilo auditável do DQ.
- **`table_name()`**: converte o nome físico Olist em nome curto e estável de tabela.
- **`ingest_bronze()`**: verifica a presença dos nove arquivos, copia bytes sem tratamento e contabiliza linhas.
- **`build_silver()`**: tipa datas, remove apenas espaços periféricos de texto e preserva a contagem de cada fonte. Em produtos, grava `is_category_missing` antes de preencher a visão analítica `unknown`. Em geolocalização, mantém o detalhe e cria a tabela adicional `geolocation_by_zip` por mediana/moda.
- **`build_gold()`**: executa o SQL DuckDB e grava todas as seis relações primeiro em um diretório temporário.
- **`_publish_gold()`**: troca a gold anterior pelo staging somente depois da materialização completa; se a troca falhar, restaura o diretório anterior.
- **`validate_gold_contracts()`**: garante conjunto de arquivos, uma linha por pedido, uma linha por item composto e igualdade de GMV entre as duas facts.
- **`run()`**: orquestra bronze → DQ → silver → preservação de linhas → gold → contratos gold → manifesto. Falhas críticas impedem uma saída parcial de ser aceita.
- **`main()`**: expõe `--source` e `--data` para terminal ou job local.

O manifesto em `data/reports/pipeline_manifest.json` registra volumes, DQ, preservação bronze→silver e contratos gold.

## `sql/gold.sql`

- **Views de entrada**: leem os Parquets silver; payments e reviews são pré-agregados por pedido.
- **`fact_orders`**: grão de um `order_id`; traz cliente, status, datas, GMV de itens, frete, pagamento, review e SLA.
- **`fact_order_items`**: grão de `(order_id, order_item_id)`; traz produto, seller, categoria, preço e frete. `LEFT JOINs` preservam a evidência mesmo diante de uma dimensão órfã, que continua visível no DQ.
- **Marts comercial**: `mart_monthly_sales`, `mart_category_performance`, `mart_customer_value` e `mart_seller_performance` excluem somente `canceled`/`unavailable` de métricas de GMV. Facts preservam todos os status.
- **Semântica**: as colunas chamadas `revenue` nos marts são GMV comercial (soma de `price`), não receita reconhecida nem margem. Review e atraso nos marts de categoria/seller são médias ponderadas por item, como declara o SQL.

## `src/ifood_analytics/analysis.py`

- **`bootstrap_mean_difference()`**: rotina genérica de reamostragem independente de duas séries, preservada para usos simples.
- **`bootstrap_clustered_mean_difference()`**: recebe uma tabela, cluster, grupo e resultado; agrega internamente por cluster e reamostra clientes inteiros com seed fixa. É usada no EDA para não tratar múltiplos pedidos do mesmo `customer_unique_id` como independentes.

## `src/ifood_analytics/ai_summary.py`

- **`GOLD_MARTS`**: contrato mínimo dos três marts agregados que podem ser usados pelo resumo.
- **`_load_gold_marts()`**: valida existência, schema e não-vazio da gold antes de calcular métricas. O erro orienta executar/corrigir o pipeline.
- **`collect_metrics()`**: lê somente agregados, monta período, GMV, categorias e concentração de sellers; facts, IDs e comentários não entram no payload.
- **`local_summary()`**: fallback determinístico, seguro para payload sem categoria e formatado para português.
- **`summarize()`**: usa o fallback sem credencial; com `OPENAI_API_KEY`, envia apenas o payload agregado à Responses API e limita o prompt a um rascunho sem causalidade inventada.
- **`main()`**: recebe diretório/arquivo de saída, persiste Markdown e imprime o texto.

## Notebooks

### `notebooks/01_data_quality.ipynb`

1. Localiza a raiz do projeto, independente do diretório de abertura, e lê a origem configurável por `OLIST_SOURCE`.
2. Perfil geral, nulos e duplicatas da fonte bruta.
3. Execução visual da mesma suíte automatizada usada pelo pipeline.
4. Distribuições, sensibilidade e participação financeira dos outliers.
5. Grão/chaves candidatas, nulidade condicionada ao status e coerência temporal.
6. Reconciliação financeira via `outer join`, incluindo investigação dos lados ausentes.
7. Ambiguidade de CEP e risco de fan-out geográfico.
8. Schema, parsing e cobertura temporal da carga.
9. Auditoria bronze→silver, com `OLIST_SILVER` opcional, e contrato de não exclusão.

### `notebooks/02_exploratory_analysis.ipynb`

1. Localiza a raiz e lê a gold configurável por `OLIST_GOLD`.
2. Explicita quais status entram no GMV comercial, sem exclusão física nas facts.
3. Sazonalidade, comparação por mês de calendário e cobertura temporal.
4. Categorias por GMV, frete, review e atraso, com SQL DuckDB.
5. Delivery/recompra: bootstrap agrupado por cliente e sensibilidade de 90 dias.
6. CLV observado regional, maturidade de clientes e escala versus valor médio.
7. Concentração de sellers (participação, HHI, Gini e risco de SLA).
8. Cenários de março–agosto/2018, os seis meses de calendário completos finais da amostra.

## Testes e configuração

- **`tests/conftest.py`**: adiciona `src/` ao caminho de teste sem exigir instalação editável.
- **`tests/test_pipeline.py`**: constrói uma fonte mínima com os nove schemas, executa o medalhão, verifica preservação/saídas gold e confirma que duplicidade da chave composta de item é crítica.
- **`tests/test_ai_summary.py`**: verifica mensagens para gold ausente/vazia, payload somente agregado e fallback seguro.
- **`requirements.txt`**: faixas compatíveis para pipeline, notebook, IA e pytest.
- **`requirements.lock`**: versões diretas pinadas de referência para reprodução local do case; o `pip` resolve transitivas para a plataforma alvo.
- **`pyproject.toml`**: metadados do pacote, extra `dev` para pytest e configuração enxuta de descoberta de testes.
- **`.gitignore`**: protege dados locais, credenciais, ambientes, caches Python/Jupyter e cache do pytest.

Execute `python -m pytest` para rodar a suíte curta de contratos. Não há arquivos de dados ou relatórios temporários versionados; `data/` é completamente local.
