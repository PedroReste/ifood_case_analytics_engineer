# Case Report Consolidado

Este documento consolida, em um unico lugar, os pontos metodologicos e executivos que estavam distribuidos nos markdowns de apoio.

## 1) Pergunta do case

Quais alavancas sao mais efetivas para aumentar o GMV nos proximos 6 meses?

## 2) Escopo e recorte

- Fonte: 9 CSVs do dataset Olist.
- Janela executiva: marco-agosto/2018 (6 meses completos).
- Metrica principal: GMV = soma de `price` para pedidos nao `canceled` e nao `unavailable`.

## 3) Qualidade de dados (pre-transformacao)

Resumo da execucao de referencia:

- 34 checks totais.
- 31 checks criticos aprovados.
- 3 warnings relevantes para monitoramento continuo.

Cobertura do gate:

- Schema das 9 fontes.
- Chaves e grao de entidades principais.
- Integridade referencial entre orders/customers/items/products/sellers/payments/reviews.
- Dominios (status, review score, valores nao negativos).
- Coerencia temporal.
- Reconciliacao financeira por `order_id` com `outer join`.

Decisoes de tratamento:

- Bronze preserva copia fiel das fontes.
- Silver padroniza tipos/texto e adiciona atributos rastreaveis.
- Categoria ausente usa `unknown` com flag de ausencia original.
- Outliers nao sao removidos; sao monitorados.
- Geolocalizacao detalhada e preservada, com visao adicional por CEP para reduzir fan-out em joins.

## 4) Viabilidade das 5 perguntas analiticas

### 4.1 Seasonality de receita

- Viabilidade: parcial.
- O que responde: padrao mensal e pico em novembro/2017.
- Limite: crescimento estrutural e seasonality se misturam.
- O que faltaria: serie mais longa e dados de trafego/midia para decomposicao robusta.

### 4.2 Categorias mais rentaveis

- Viabilidade: proxy.
- O que responde: categorias lideres por GMV, pedidos e sinais operacionais.
- Limite: sem CMV/comissao/custo logistico real, nao ha margem real.
- Decisao metodologica: tratar rentabilidade como proxy de GMV, com frete e experiencia como guardrails.

### 4.3 Atraso afeta recompra

- Viabilidade: associacao observacional.
- O que responde: atraso reduz review de forma forte; ha diferenca observada em recompra.
- Limite: censura temporal e confundidores nao observados impedem causalidade.
- Robustez: na janela de 90 dias o intervalo cruza zero para recompra.
- Implicacao: recomenda experimento de SLA/recuperacao antes de estimar uplift causal.

### 4.4 CLV por regiao

- Viabilidade: proxy.
- O que responde: CLV observado historico por cliente e escala por UF.
- Limite: nao e previsao de lifetime futuro.
- O que faltaria: cohorts mais longos, margem e CAC por canal/UF.

### 4.5 Concentracao de sellers

- Viabilidade: direta.
- O que responde: participacao da cauda, Gini e HHI.
- Leitura: ha desigualdade relevante, mas sem monopolista isolado.

## 5) Principais achados consolidados

- Top 5 categorias representam 40,8% do GMV no recorte executivo.
- SP/RJ/MG concentram 64,2% do GMV no mesmo periodo.
- Atraso: review medio cai de 4,29 para 2,57.
- Recompra: diferenca observada existe, mas sensivel ao recorte temporal.
- Sellers: top 10% concentram ~67,5% do GMV; Gini alto e HHI baixo.

## 6) Recomendacoes executivas

- Prioridade 1: disponibilidade e cross-sell nas categorias lideres.
- Prioridade 2: crescimento segmentado em SP/RJ/MG com teste controlado.
- Prioridade 3: confiabilidade logistica com experimento de SLA/recuperacao.

## 7) Resumo automatizado (IA) e governanca

O resumo automatizado existe para acelerar comunicacao executiva, com guardrails:

- Sem credenciais externas, gera fallback deterministico com metricas agregadas.
- Com `OPENAI_API_KEY`, envia apenas agregados da gold para a API.
- Nao envia IDs de cliente, pedido ou comentarios textuais.
- Se a gold estiver ausente/vazia/incompativel, falha com mensagem acionavel em vez de inventar output.

Exemplo de narrativa automatica (resumo):

> A base soma R$ 13.494.400,74 em GMV de itens. A categoria lider e health_beauty (R$ 1.255.695,13). Os 10% maiores sellers concentram 67,5% do GMV. Priorizar disponibilidade nas categorias lideres, confiabilidade logistica e desenvolvimento da cauda de sellers.

Uso recomendado:

- Tratar o texto como rascunho revisado por humano.
- Nao usar o resumo automatizado como decisao final sem contexto metodologico.

## 8) Limitacoes e guardrails

- GMV nao representa margem nem receita liquida contabil.
- Atraso x recompra nao deve ser comunicado como efeito causal sem experimento.
- Decisao de escala deve incluir CAC, margem e capacidade operacional.

## 9) Artefatos para reproducao

- `README.md`
- `notebooks/01_data_quality.ipynb`
- `notebooks/02_exploratory_analysis.ipynb`
- `src/ifood_analytics/pipeline.py`
- `src/ifood_analytics/quality.py`
- `sql/gold.sql`
- `docs/one_pager.md`