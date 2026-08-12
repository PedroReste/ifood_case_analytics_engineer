-- Camada gold do case Olist.
-- Cada tabela tem granularidade declarada e evita fan-out entre itens, pagamentos
-- e reviews por meio de agregações no nível do pedido antes dos joins.

CREATE OR REPLACE TEMP VIEW orders AS
SELECT * FROM read_parquet('${SILVER}/orders.parquet');
CREATE OR REPLACE TEMP VIEW customers AS
SELECT * FROM read_parquet('${SILVER}/customers.parquet');
CREATE OR REPLACE TEMP VIEW items AS
SELECT * FROM read_parquet('${SILVER}/order_items.parquet');
CREATE OR REPLACE TEMP VIEW products AS
SELECT * FROM read_parquet('${SILVER}/products.parquet');
CREATE OR REPLACE TEMP VIEW sellers AS
SELECT * FROM read_parquet('${SILVER}/sellers.parquet');
CREATE OR REPLACE TEMP VIEW translations AS
SELECT * FROM read_parquet('${SILVER}/product_category_name_translation.parquet');
CREATE OR REPLACE TEMP VIEW payments AS
SELECT order_id, SUM(payment_value) AS payment_value
FROM read_parquet('${SILVER}/order_payments.parquet') GROUP BY 1;
CREATE OR REPLACE TEMP VIEW reviews AS
SELECT order_id, AVG(review_score) AS review_score
FROM read_parquet('${SILVER}/order_reviews.parquet') GROUP BY 1;

-- Grão: uma linha por pedido. `item_revenue` é GMV de itens (soma de price),
-- não receita contábil líquida: custo, comissão, subsídio e margem não existem
-- na fonte. Pagamentos permanecem disponíveis para reconciliação, sem serem
-- multiplicados por itens.
CREATE OR REPLACE TABLE fact_orders AS
WITH item_totals AS (
    SELECT order_id, SUM(price) AS item_revenue, SUM(freight_value) AS freight_value,
           COUNT(*) AS item_count, COUNT(DISTINCT seller_id) AS seller_count
    FROM items GROUP BY 1
)
SELECT o.order_id, o.customer_id, c.customer_unique_id, c.customer_state,
       o.order_status, o.order_purchase_timestamp, o.order_approved_at,
       o.order_delivered_customer_date, o.order_estimated_delivery_date,
       COALESCE(i.item_revenue, 0) AS item_revenue,
       COALESCE(i.freight_value, 0) AS freight_value,
       COALESCE(i.item_count, 0) AS item_count,
       COALESCE(i.seller_count, 0) AS seller_count,
       p.payment_value, r.review_score,
       CASE WHEN o.order_delivered_customer_date IS NOT NULL
            THEN date_diff('day', o.order_purchase_timestamp, o.order_delivered_customer_date) END AS delivery_days,
       CASE WHEN o.order_delivered_customer_date IS NOT NULL
            THEN o.order_delivered_customer_date > o.order_estimated_delivery_date END AS is_late
FROM orders o
-- LEFT JOIN preserva o pedido mesmo se uma dimensão estiver ausente. O DQ
-- continua sinalizando a FK, mas a camada analítica não apaga a evidência.
LEFT JOIN customers c USING (customer_id)
LEFT JOIN item_totals i USING (order_id)
LEFT JOIN payments p USING (order_id)
LEFT JOIN reviews r USING (order_id);

-- Grão: um item de pedido. Adequado para categoria e seller; não somar payment_value aqui.
CREATE OR REPLACE TABLE fact_order_items AS
SELECT i.order_id, i.order_item_id, i.product_id, i.seller_id,
       o.customer_id, c.customer_unique_id, c.customer_state,
       o.order_status, o.order_purchase_timestamp, o.order_delivered_customer_date,
       o.order_estimated_delivery_date, i.price, i.freight_value,
       COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category,
       p.is_category_missing,
       s.seller_state, r.review_score,
       CASE WHEN o.order_delivered_customer_date IS NOT NULL
            THEN o.order_delivered_customer_date > o.order_estimated_delivery_date END AS is_late
FROM items i
-- LEFT JOINs preservam todos os itens; chaves órfãs permanecem visíveis como
-- dimensões nulas e são reportadas pela suíte de qualidade.
LEFT JOIN orders o USING (order_id)
LEFT JOIN customers c USING (customer_id)
LEFT JOIN products p USING (product_id)
LEFT JOIN sellers s USING (seller_id)
LEFT JOIN translations t USING (product_category_name)
LEFT JOIN reviews r USING (order_id);

-- Grão: mês de compra. A coluna `revenue` destes marts significa GMV comercial:
-- soma do preço de itens em pedidos que não são canceled/unavailable. Ela pode
-- incluir pedidos em etapas anteriores à entrega e não deve ser lida como receita
-- reconhecida contabilmente.
CREATE OR REPLACE TABLE mart_monthly_sales AS
SELECT date_trunc('month', order_purchase_timestamp) AS order_month,
       COUNT(DISTINCT order_id) AS orders,
       COUNT(DISTINCT customer_unique_id) AS customers,
       SUM(item_revenue) AS revenue,
       SUM(item_revenue) / NULLIF(COUNT(DISTINCT order_id), 0) AS avg_order_value
FROM fact_orders
WHERE order_status NOT IN ('canceled', 'unavailable')
GROUP BY 1 ORDER BY 1;

-- Grão: categoria. "Rentabilidade" é aproximada por GMV, pois não há custo/margem.
-- As médias de review e atraso são ponderadas por linha de item, pois a tabela
-- mede a experiência associada aos itens comercializados na categoria.
CREATE OR REPLACE TABLE mart_category_performance AS
SELECT category, COUNT(DISTINCT order_id) AS orders, SUM(price) AS revenue,
       SUM(freight_value) AS freight_value, AVG(review_score) AS avg_review_score,
       AVG(CAST(is_late AS INTEGER)) AS late_rate
FROM fact_order_items
WHERE order_status NOT IN ('canceled', 'unavailable')
GROUP BY 1 ORDER BY revenue DESC;

-- Grão: cliente único. CLV observado (receita histórica), não valor futuro previsto.
CREATE OR REPLACE TABLE mart_customer_value AS
SELECT customer_unique_id, MODE(customer_state) AS customer_state,
       COUNT(*) AS orders, SUM(item_revenue) AS observed_clv,
       MIN(order_purchase_timestamp) AS first_order_at,
       MAX(order_purchase_timestamp) AS last_order_at,
       COUNT(*) > 1 AS is_repeat_customer
FROM fact_orders
WHERE order_status NOT IN ('canceled', 'unavailable')
GROUP BY 1;

-- Grão: seller. Permite medir concentração e qualidade operacional; as médias
-- de review/atraso são ponderadas por item vendido pelo seller.
CREATE OR REPLACE TABLE mart_seller_performance AS
SELECT seller_id, MODE(seller_state) AS seller_state,
       COUNT(DISTINCT order_id) AS orders, SUM(price) AS revenue,
       AVG(review_score) AS avg_review_score, AVG(CAST(is_late AS INTEGER)) AS late_rate
FROM fact_order_items
WHERE order_status NOT IN ('canceled', 'unavailable')
GROUP BY 1 ORDER BY revenue DESC;
