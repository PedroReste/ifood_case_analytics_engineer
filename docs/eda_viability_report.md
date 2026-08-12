# Viabilidade de Resposta — Perguntas de EDA

Documento de referência para as cinco perguntas analíticas do case. Para cada pergunta, avalia-se o que foi possível responder diretamente com os dados Olist, o que exigiu um proxy declarado e o que permanece como limitação estrutural.

---

## Pergunta 1 — Qual é a sazonalidade de receita?

### Viabilidade: **Parcialmente respondida com ressalvas**

**O que é possível responder:**
A série histórica de março/2016 a agosto/2018 permite identificar padrões mensais. Novembro/2017 é o maior mês observado (R$ 1,00 mi de GMV, 7.423 pedidos), compatível com Black Friday. A comparação YoY de jan–jul/2017 vs. jan–jul/2018 mostra crescimento consistente.

| Resultado observado | Valor |
|---|---|
| Maior mês (GMV) | Novembro/2017 — R$ 1,00 mi |
| Crescimento médio YoY (jan–jul) | Positivo em todos os meses comparáveis |
| Recorte executivo | Março–agosto/2018: R$ 5,56 mi, 39,7k pedidos |

**Limitação estrutural — por que a sazonalidade não pode ser isolada:**

A Olist crescia rapidamente no período. **Tendência de crescimento** e **sazonalidade** estão misturadas na série: um pico em novembro/2017 pode refletir Black Friday *e* o fato de novembro ser um mês mais maduro da plataforma em comparação a meses anteriores.

Para decompor sazonalidade da tendência são necessários ao menos três anos completos com crescimento estabilizado. A base cobre apenas ~30 meses.

**Proxy utilizado:**

Comparação por mês do calendário restrita a 2017 e meses completos de 2018, reduzindo (mas não eliminando) a mistura. Setembro e outubro/2018 são residuais e excluídos do recorte executivo.

**Para resposta definitiva, faltam:**
- Dados de sessão/tráfego (para separar conversão de volume)
- Histórico de pelo menos 3 anos estabilizados
- Dados de investimento em mídia por período (para isolar efeito de campanhas)

---

## Pergunta 2 — Quais categorias são mais rentáveis?

### Viabilidade: **Respondida com proxy declarado de rentabilidade**

**O que é possível responder:**

O GMV por categoria é calculável e seguro no período março–agosto/2018. As cinco categorias líderes concentram **40,8%** do GMV total (R$ 2,27 mi de R$ 5,56 mi).

| Ranking | Categoria | GMV (período) | Revenue share | Review médio | Taxa de atraso |
|---|---|---|---|---|---|
| 1 | health_beauty | — | — | — | — |
| 2 | watches_gifts | — | — | — | — |
| 3 | bed_bath_table | — | ~19,7% frete/GMV | <4,0 | elevada |
| 4 | sports_leisure | — | — | — | — |
| 5 | housewares | — | — | — | — |

> Os valores exatos por categoria são gerados na execução do notebook `02_exploratory_analysis.ipynb`.

**Limitação estrutural — por que "rentabilidade" não é calculável:**

A fonte Olist não contém:
- Custo de aquisição de produto (CMV)
- Comissão da plataforma por categoria
- Custo logístico real (somente `freight_value` pago pelo cliente, que não é o custo de operação)
- Margem de contribuição por seller ou categoria
- Subsídios ou incentivos por vertical

**Proxy utilizado:**

GMV (soma de `price` por categoria, excluindo pedidos `canceled`/`unavailable`) como aproximação de "receita bruta de itens". Frete é analisado separadamente como `freight_burden` (frete / GMV) para sinalizar categorias com custo logístico desproporcional.

A matriz de decisão cruza GMV com review médio e taxa de atraso, para não escalar categorias com experiência deteriorada.

**Para resposta definitiva, faltam:**
- Tabela de CMV por produto/categoria
- Tabela de comissões por categoria (a Olist cobra percentuais diferentes por vertical)
- Custo logístico operacional por rota/peso

---

## Pergunta 3 — Atraso na entrega afeta a recompra?

### Viabilidade: **Respondida com associação observacional — causalidade indeterminada**

**O que é possível responder:**

A associação entre atraso e comportamento posterior é mensurável com os dados disponíveis.

| Métrica | Pedidos no prazo | Pedidos atrasados | Diferença |
|---|---|---|---|
| Taxa de recompra (janela total) | 3,31% | 2,72% | −0,59 p.p. |
| IC95% bootstrap agrupado por cliente | — | — | −0,97 a −0,20 p.p. |
| Review médio | 4,29 | 2,57 | −1,72 pontos |

**Análise de robustez (janela de 90 dias):**

Ao equalizar a oportunidade de observação — restringindo a coorte a pedidos com ao menos 90 dias de janela — a diferença cai para **−0,29 p.p.** (IC95%: −0,66 a +0,10 p.p.), **cruzando zero**. A evidência de efeito sobre recompra é sensível à censura temporal e não sustenta afirmação causal.

**Por que causalidade não é determinável:**

- **Censura temporal**: pedidos recentes têm menos tempo para gerar recompra, criando viés de sobrevivência. A análise de 90 dias mitiga parcialmente isso.
- **Confundidores não observados**: clientes de menor renda, regiões mais distantes ou categorias específicas podem ter simultaneamente maior taxa de atraso e menor frequência de compra por razões independentes do atraso.
- **Ausência de grupo de controle exógeno**: o atraso não foi aleatorizado; pedidos atrasados diferem sistematicamente dos pontuais em rota, seller e período.

**Proxy utilizado:**

A queda de review de 4,29 para 2,57 é o sinal mais robusto e direto. A diferença de recompra observada (−0,59 p.p.) justifica a hipótese, mas a recomendação é um **experimento de SLA/recuperação** para medir efeito causal, não assumir que a diferença observada se tornará receita incremental.

**Exposição logística:**
R$ 490,5 mil de GMV passaram por pedidos atrasados no recorte executivo. Reduzir 25% dos atrasos "trata" R$ 122,6 mil de GMV sob risco — não é uplift projetado.

**Para resposta definitiva, faltam:**
- Experimento controlado (holdout de SLA ou recuperação proativa)
- Dados de sessão pós-entrega (visitas, abandonos, buscas) para medir intenção antes da recompra
- Dados de contato com SAC/reclamações por pedido atrasado

---

## Pergunta 4 — Como varia o CLV por região?

### Viabilidade: **Respondida com proxy de CLV histórico — valor futuro indeterminável**

**O que é possível responder:**

O GMV histórico acumulado por `customer_unique_id` e seu estado de entrega é calculável diretamente.

| Região | GMV mar–ago/2018 | Share | CLV médio observado | CLV index (vs. média) |
|---|---|---|---|---|
| SP | Maior absoluto | ~46% | 0,91× média | Escala alta, valor abaixo da média |
| RJ | 2º absoluto | ~10% | 1,04× média | Valor ligeiramente acima |
| MG | 3º absoluto | ~8% | — | — |
| BA | Menor do grupo | ~3% | 1,10× média | Valor alto, base pequena |

> Os valores exatos por UF são gerados na execução do notebook.

**Limitação estrutural — por que CLV futuro não é estimável:**

O CLV no sentido canônico (valor presente de compras futuras esperadas) exige:
- Modelo de probabilidade de churn por cohort (ex.: BG/NBD ou Pareto/NBD)
- Taxa de desconto e horizonte de projeção
- Ao menos 3 cohorts completos para calibração

A janela de dados (~30 meses, plataforma em crescimento) não é suficiente para separar "ainda é cliente ativo" de "churnou". A taxa de recompra observada na base é de ~3% por pedido, tornando o sinal muito ruidoso para uma curva de sobrevivência confiável.

**Proxy utilizado:**

"CLV observado" = soma do GMV histórico por `customer_unique_id` na janela disponível. Clientes com primeira compra ao menos 180 dias antes do fim da base recebem um índice de maturidade para evitar subestimação de clientes recentes.

A análise regional usa escala absoluta (GMV total por UF) combinada com CLV médio indexado, porque CLV médio isolado pode privilegiar estados pequenos por ruído amostral.

**Para resposta definitiva, faltam:**
- Dados de pelo menos 3 cohorts anuais completos
- Taxa de desconto e margem por cliente (para calcular valor presente)
- Dados de custo de aquisição por canal/UF (para calcular ROI de aquisição regional)

---

## Pergunta 5 — Há concentração de sellers?

### Viabilidade: **Respondida diretamente — pergunta mais completa com os dados disponíveis**

**O que é possível responder:**

A distribuição de GMV por seller é calculável sem proxies. As métricas de concentração estão disponíveis diretamente.

| Métrica | Valor | Interpretação |
|---|---|---|
| Top 1% de sellers, share de GMV | ~26% | Concentração significativa na ponta |
| Top 10% de sellers, share de GMV | **67,5%** | Maioria do GMV em minoria dos sellers |
| Gini de receita | **0,79** | Desigualdade alta na distribuição |
| HHI | **0,0036** | Mercado não-concentrado (sem monopolista) |
| Maior seller individual | ~1,7% do GMV | Sem seller dominante isolado |
| Atraso ponderado por GMV (sellers 30+ pedidos) | **7,9%** | Risco logístico concentrável em poucos sellers |

**Interpretação:**

A cauda é desigual (Gini 0,79), mas não há monopolista (HHI 0,0036). Isso significa que a receita está distribuída de forma muito assimétrica, mas nenhum seller individual é grande o suficiente para representar risco de concentração crítico. A gestão de SLA pode ser priorizada nos sellers de maior GMV que também têm atraso elevado — identificáveis pelo scatter `revenue × late_rate`.

**Limitações residuais:**
- `avg_review_score` e `late_rate` por seller são médias ponderadas por item vendido, não por pedido — coerente com o grão da visão, mas não equivale à experiência média por transação.
- Sellers com poucos pedidos (< 30) têm métricas de atraso ruidosas e são excluídos da análise de risco operacional.

**Para análise mais completa, faltam:**
- Dados de estoque/ruptura por seller (para identificar sellers que atradem por problema operacional vs. logístico)
- Contrato e histórico de SLA por seller
- Dados de fulfillment (seller entrega ou usa centro de distribuição Olist)

---

## Resumo consolidado de viabilidade

| Pergunta | Viabilidade | Proxy utilizado | Dados que desbloqueiam resposta definitiva |
|---|---|---|---|
| 1. Sazonalidade | ⚠️ Parcial | Comparação YoY restrita a meses completos | 3+ anos estabilizados, dados de tráfego/mídia |
| 2. Categorias rentáveis | ⚠️ Proxy | GMV como proxy de rentabilidade | CMV, comissões, custo logístico operacional |
| 3. Atraso × recompra | ⚠️ Associação | Diferença observada + bootstrap agrupado | Experimento com holdout de SLA/recuperação |
| 4. CLV por região | ⚠️ Proxy | GMV histórico observado por cliente | Cohorts completos, margem, CAC por canal/UF |
| 5. Concentração de sellers | ✅ Direta | — (métricas calculáveis sem proxy) | Dados de estoque, fulfillment, SLA contratual |

**Nota sobre GMV vs. receita:** todas as análises usam GMV (soma de `price` excluindo `canceled`/`unavailable`) porque custo, margem, comissão e subsídio não existem na fonte. Frete é analisado separadamente. As recomendações são hipóteses a validar com experimentos, não projeções causais.
