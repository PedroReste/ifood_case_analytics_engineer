# Case Analytics Engineer Senior - iFood / Olist

## Objetivo do case

Responder a pergunta:

**Quais alavancas são mais efetivas para aumentar a receita nos proximos 6 meses?**

## Escopo e premissas

- Fonte: 9 CSVs públicos do dataset Olist.
- Recorte executivo para decisão: março a agosto de 2018 (6 meses completos).
- Metrica principal: GMV (soma de `price` dos itens) para pedidos não `canceled` e não `unavailable`.
- Objetivo: construir um MVP analítico para priorizacao de alavancas, sem prometer causalidade quando o desenho for observacional.

## Processo completo de tratamento de dados

### 1) Bronze

- A camada bronze copia os CSVs sem alterar dados.
- Objetivo: preservar rastreabilidade total da origem.

### 2) Gate de qualidade antes da silver

O gate de qualidade roda sobre a origem e cobre:

- Schema esperado por tabela.
- Chaves candidatas (unicidade e não nulos).
- Integridade referêncial entre pedidos, clientes, itens, produtos, sellers, pagamentos e reviews.
- Domínios validos (status, notas, valores não negativos).
- Coerência temporal das datas de compra, aprovação e entrega.
- Reconciliação financeira por pedido (pagamentos vs itens + frete, com `outer join`).

Regra de decisão:

- Checks críticos reprovados interrompem a execução.
- Warnings não bloqueiam, mas ficam visiveis no relatorio para monitoramento.

### 3) Silver

Tratamentos aplicados:

- Conversão de tipos e datas.
- Normalização leve de texto (sem descaracterizar conteúdo).
- Categoria ausente em produto vira `unknown`, mantendo sinalização da ausência original.
- Geolocalização detalhada e preservada; a visão por CEP e criada para evitar multiplicação em joins.
- Nulos condicionais ao status do pedido são mantidos (sem inventar datas/eventos).

### 4) Gold

- O SQL gera as facts e marts em staging.
- Consolidação das visão de pedidos e produtos.

## Análises realizadas (5 perguntas)

### 1) Sazonalidade de pedidos e GMV

- Série mensal e comparacao por meses de calendário.
- Resultado: existe pico forte (ex.: novembro/2017), mas tendência de crescimento e sazonalidade se misturam.

### 2) Categorias com maior alavanca comercial

- Ranking por GMV, pedidos e ticket.
- Cruzamento com experiência operacional (atraso/review/frete).
- Resultado: top 5 categorias concentram 40,8% do GMV no recorte executivo.

### 3) Relacao entre atraso e recompra

- Comparação entre pedidos no prazo e atrasados.
- Análise de sensibilidade com janela uniforme de 90 dias.
- Resultado: queda de review e robusta; impacto em recompra permanece observacional e sensível ao recorte.

### 4) Variação de valor observado por região

- Leitura de escala por UF e valor médio observado por cliente.
- Resultado: SP/RJ/MG concentram 64,2% do GMV no recorte.

### 5) Concentração de sellers

- Curva acumulada, participação dos maiores sellers, HHI e Gini.
- Resultado: concentração relevante de receita na cauda, sem monopolista isolado.

## Resultado executivo resumido

- Alavanca 1: disponibilidade e cross-sell nas categorias líderes.
- Alavanca 2: crescimento segmentado em SP/RJ/MG com teste controlado.
- Alavanca 3: confiabilidade de entrega para reduzir friccao de experiencia.

Resumo com plano de 6 meses: `docs/one_pager.md`.

## Como executar

Requer Python 3.11+.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.lock
$env:PYTHONPATH = "src"

# Ajuste para a pasta com os 9 CSVs do Olist
$env:OLIST_SOURCE = "C:\caminho\archive"

# 1) Diagnostico de qualidade da fonte
jupyter notebook notebooks\01_data_quality.ipynb

# 2) Pipeline completo bronze -> silver -> gold
python -m ifood_analytics.pipeline --source "C:\caminho\archive" --data data --docs docs

# 3) Analise exploratoria e recomendacoes
jupyter notebook notebooks\02_exploratory_analysis.ipynb

# 4) Resumo automatizado em markdown (docs/ai_summary.md)
python -m ifood_analytics.ai_summary --data data

# 5) Testes de contrato
python -m pytest
```