# Exemplo de automated summary

Output determinístico produzido sem credenciais externas:

> A base soma R$ 13.494.400,74 em GMV de itens. A categoria líder é health_beauty (R$ 1.255.695,13). Os 10% maiores sellers concentram 67,5% do GMV. Priorize disponibilidade nas categorias líderes, confiabilidade logística e desenvolvimento da cauda de sellers.

Com `OPENAI_API_KEY`, o mesmo conjunto de métricas agregadas alimenta a Responses API. Se a gold estiver ausente, vazia ou sem as colunas esperadas, o script interrompe com uma mensagem acionável em vez de gerar um resumo artificial. O texto é um rascunho sujeito à revisão humana; IDs, comentários e demais dados no nível do cliente não são enviados.

