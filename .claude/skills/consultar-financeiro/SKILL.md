---
name: consultar-financeiro
description: >
  Use ao responder perguntas financeiras/gerenciais da Locanorte — DRE / Resultado
  Operacional, fluxo de caixa, faturamento, contas a pagar/receber, maiores clientes,
  coletas (Ordens de Serviço) e rentabilidade por centro de custo/caminhão. Orienta
  qual tool do conector MCP Locanorte usar e as ressalvas de interpretação (visão
  "livros do Omie" x "gerencial"). Aciona em perguntas como "qual o resultado do mês",
  "como está o caixa", "quanto faturamos", "quem são os maiores clientes", "rentabilidade
  por caminhão", "quanto pagamos de imposto".
---

# Consultar o financeiro da Locanorte (conector MCP Locanorte)

O servidor MCP Locanorte (`https://mcp-locanorte.onrender.com/mcp`) expõe 9 tools com
dados reais do Omie via Kondado. **Escolha a tool pela pergunta** — não invente números,
sempre chame a tool.

## Mapa pergunta → tool

| Pergunta do usuário | Tool | Observações |
|---|---|---|
| "Está no ar? conectado?" | `status_locanorte()` | health-check |
| "Resumo do mês / visão geral" | `resumo_locanorte(competencia?)` | cadastro + financeiro ao vivo |
| "Quanto faturamos em <mês>?" | `faturamento(competencia)` | Receita Líquida (DRE); fallback NFS-e |
| "Qual o resultado / DRE?" | `dre_resultado(ano?, competencia?)` | Resultado Operacional + `demonstrativo_realizado` |
| "Como está o caixa? vou ter caixa?" | `fluxo_caixa()` | saldo hoje + vencimentos + projeção 7/15/30d |
| "Maiores clientes / quem deve" | `top_clientes(limite)` | por contas a receber |
| "Quantas coletas / OS no mês?" | `coletas(competencia?, limite)` | Ordens de Serviço, por etapa/serviço/caminhão |
| "Rentabilidade por caminhão / centro de custo" | `centro_custo(competencia?, limite)` | receita − custo por rateio (v1.16.0) |
| "Razão / lançamentos pagar+receber" | `lancamentos(competencia?, limite)` | tabela curada, `valor_dre` assinado |

`competencia` é sempre `'AAAA-MM'`. Vazio = mês corrente (ou acumulado, conforme a tool).

## ⚠️ Ressalvas OBRIGATÓRIAS ao reportar números

1. **DRE — duas visões válidas do MESMO resultado (jan–jun/2026):**
   - `dre_resultado` retorna **+R$ 591.420,03** = Resultado pelos **livros do Omie**.
   - A **DRE gerencial do contador** (motor v10) mostra **+R$ 427.889,53** — reclassifica os impostos
     sobre vendas (ISS/PIS/ISS-retido, ~−125.929,81, calculados das NFS-e) como dedução da receita.
   - A diferença é **reclassificação, não dinheiro novo**. Ao dar o resultado, **diga qual visão** e,
     se relevante, cite as duas. O ajuste gerencial vive no Power BI, não no servidor.
2. **`lancamentos.resultado_liquido_dre`** é o NET de TODOS os títulos (inclui não-operacionais) —
   **NÃO** é o Resultado Operacional; para esse use `dre_resultado`.
3. **`centro_custo`**: a receita costuma ser rateada por OPERAÇÃO (4.x) e o custo por CAMINHÃO (2.x)/ÁREA —
   dimensões que podem não alinhar (o campo `aviso` sinaliza). Não prometa "margem por caminhão" exata.
4. **Frescor:** as tools refletem o ÚLTIMO sync do Kondado; se a data importar, cite `data_referencia`.

## Se o conector MCP Locanorte estiver fora do ar / bloqueado
Dá para consultar as MESMAS tabelas direto no **Kondado** (destino 40059) via o conector
`MCP_KONDADO` (KSQL) — use o agent `kondado-query` para montar as consultas.
