# Case Analytics Engineer Senior - iFood / Olist

## Objetivo do case

Responder, com dados reproduziveis e leitura executiva clara, a pergunta:

**Quais alavancas sao mais efetivas para aumentar o GMV nos proximos 6 meses?**

## Escopo e premissas

- Fonte: 9 CSVs publicos do dataset Olist.
- Recorte executivo para decisao: marco a agosto de 2018 (6 meses completos).
- Metrica principal: GMV (soma de `price` dos itens) para pedidos nao `canceled` e nao `unavailable`.
- Objetivo: construir um MVP analitico para priorizacao de alavancas, sem prometer causalidade quando o desenho for observacional.

## Estrutura simplificada para apresentacao

- `notebooks/01_data_quality.ipynb`: diagnostico da fonte e justificativa dos tratamentos.
- `src/ifood_analytics/quality.py`: contratos de qualidade usados no gate do pipeline.
- `src/ifood_analytics/pipeline.py`: orquestracao bronze -> silver -> gold e validacoes finais.
- `sql/gold.sql`: modelagem das facts e marts analiticas.
- `notebooks/02_exploratory_analysis.ipynb`: respostas das 5 perguntas e recomendacoes.
- `docs/one_pager.md`: resumo executivo para decisao.
- `docs/case_report.md`: apendice tecnico curto.

Documentos historicos de apoio ficam em `docs/archive/`.

## Processo completo de tratamento de dados

### 1) Bronze: copia fiel da origem

- O pipeline valida se os 9 arquivos esperados existem.
- A camada bronze copia os CSVs sem alterar dados.
- Objetivo: preservar rastreabilidade total da origem.

### 2) Gate de qualidade antes da silver

O gate de qualidade roda sobre a origem e cobre:

- Schema esperado por tabela.
- Chaves candidatas (unicidade e nao nulos).
- Integridade referencial entre pedidos, clientes, itens, produtos, sellers, pagamentos e reviews.
- Dominios validos (status, notas, valores nao negativos).
- Coerencia temporal das datas de compra, aprovacao e entrega.
- Reconciliacao financeira por pedido (pagamentos vs itens + frete, com `outer join`).

Regra de decisao:

- Checks criticos reprovados interrompem a execucao.
- Warnings nao bloqueiam, mas ficam visiveis no relatorio para monitoramento.

### 3) Silver: padronizacao sem perder informacao

Tratamentos aplicados:

- Conversao de tipos e datas monitoradas.
- Normalizacao leve de texto (sem descaracterizar conteudo).
- Categoria ausente em produto vira `unknown`, mantendo sinalizacao da ausencia original.
- Geolocalizacao detalhada e preservada; a visao por CEP e criada para evitar multiplicacao em joins.
- Nulos condicionais ao status do pedido sao mantidos (sem inventar datas/eventos).

Ponto importante: nao ha exclusao de linhas da bronze para a silver.

### 4) Gold: modelo analitico e contratos finais

- O SQL gera as facts e marts em staging.
- So depois da materializacao completa o conteudo e publicado na gold.
- Contratos finais validam:
	- presenca das tabelas esperadas,
	- grao correto por entidade,
	- consistencia de GMV entre fatos.

## Analises realizadas (5 perguntas)

### 1) Sazonalidade de pedidos e GMV

- Serie mensal e comparacao por meses de calendario.
- Resultado: existe pico forte (ex.: novembro/2017), mas tendencia de crescimento e sazonalidade se misturam.

### 2) Categorias com maior alavanca comercial

- Ranking por GMV, pedidos e ticket.
- Cruzamento com experiencia operacional (atraso/review/frete).
- Resultado: top 5 categorias concentram 40,8% do GMV no recorte executivo.

### 3) Relacao entre atraso e recompra

- Comparacao entre pedidos no prazo e atrasados.
- Bootstrap agrupado por cliente para intervalo de confianca.
- Analise de sensibilidade com janela uniforme de 90 dias.
- Resultado: queda de review e robusta; impacto em recompra permanece observacional e sensivel ao recorte.

### 4) Variacao de valor observado por regiao

- Leitura de escala por UF e valor medio observado por cliente.
- Resultado: SP/RJ/MG concentram 64,2% do GMV no recorte.

### 5) Concentracao de sellers

- Curva acumulada, participacao dos maiores sellers, HHI e Gini.
- Resultado: concentracao relevante de receita na cauda, sem monopolista isolado.

## Resultado executivo resumido

- Alavanca 1: disponibilidade e cross-sell nas categorias lideres.
- Alavanca 2: crescimento segmentado em SP/RJ/MG com teste controlado.
- Alavanca 3: confiabilidade de entrega para reduzir friccao de experiencia.

Resumo com plano de 6 meses: `docs/one_pager.md`.

## Como apresentar o case (roteiro)

1. Contexto, premissas e limites neste README.
2. Qualidade da fonte e decisoes de tratamento em `notebooks/01_data_quality.ipynb`.
3. Evidencias das 5 perguntas em `notebooks/02_exploratory_analysis.ipynb`.
4. Decisao executiva e plano em `docs/one_pager.md`.

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
python -m ifood_analytics.pipeline --source "C:\caminho\archive" --data data

# 3) Analise exploratoria e recomendacoes
jupyter notebook notebooks\02_exploratory_analysis.ipynb

# 4) Testes de contrato
python -m pytest
```

## Limitacoes e cuidados de interpretacao

- GMV nao e margem nem receita liquida contabil.
- Atraso x recompra e relacao observacional; nao deve ser vendido como efeito causal sem experimento.
- Decisao final de escala deve incorporar CAC, margem e capacidade operacional.