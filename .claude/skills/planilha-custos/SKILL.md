---
name: planilha-custos
description: >
  Use para montar ou atualizar a planilha de custos e MARGEM da Locanorte (por centro de
  custo / caminhão / operação) a partir do warehouse Kondado, pronta para migrar ao Power
  BI. Aciona em pedidos como "planilha de custos", "margem por caminhão/serviço/projeto",
  "custo por centro de custo", "rentabilidade da frota", "quanto custa cada caminhão".
---

# Montar a planilha de custos e margem (Kondado → Excel → Power BI)

## Fonte de dados (destino Kondado 40059, via conector MCP_KONDADO ou hub CSV)

O centro de custo do TÍTULO no Omie fica no **rateio/distribuição** (tabela-filha), não no título:

- **Custo por centro de custo:** `omie_lancamentos_contas_pagar_distribuicao`
  (`distribuicao_ccoddep` = centro de custo, `distribuicao_nvaldep` = valor).
- **Receita por centro de custo:** `omie_lancamentos_contas_receber_distribuicao` (mesmo grão).
- **Nome do centro de custo/caminhão:** `omie_departamentos` (`codigo` = ccoddep → `descricao`;
  placas aparecem como `2.x CAM-...`; a Frota é a estrutura `001.002.xxx`).
- Para excluir CANCELADO e filtrar competência, juntar cada filha ao **título-pai**
  (`omie_lancamentos_contas_{pagar,receber}`) por `codigo_lancamento_omie` (status + data_vencimento).

## Estrutura da planilha (abas)

1. **Custo_por_CC** — todos os centros de custo, com categoria (Caminhão / Área / Operação /
   Sócios / Investimento / Inativo) e custo.
2. **Resumo_Categoria** — custo agregado por categoria + %.
3. **Custo_por_Caminhao** — só a Frota (2.x CAM-...) — **base para custo/km** (liga à telemetria).
4. **Receita_por_Operacao** — receita rateada por operação (4.1 Estacionárias, 4.8 Compactador,
   4.2 Roll On, 4.5 Destinação).
5. **Margem_por_Operacao** — receita × custo do mesmo grupo 4.x (aproximado — ver ⚠️).
6. **Leia-me** — método, limitações e migração ao Power BI.

## ⚠️ Limitação a comunicar SEMPRE
A **receita é rateada por OPERAÇÃO (4.x)** e o **custo por CAMINHÃO (2.x)/ÁREA** — as dimensões
**não se alinham**, então **margem por caminhão exata não é possível hoje**. Dá para: custo por
caminhão (sólido), receita por operação (sólido), margem por operação (aproximada). Para margem
por caminhão/serviço, alinhar o rateio no Omie (receita e custo no mesmo centro de custo).

## Como gerar
1. Consultar as 3 tabelas acima (agent `kondado-query`).
2. Montar o `.xlsx` com openpyxl (categorizar por `descricao`: `CAM-`/`2.`=Frota; `4.`=Operação;
   `8.`/PRO-LABORE/DIST=Sócios; `7.`/NOVAS CACAMBAS/REFORMA=Investimento; `INATIVO`=Inativo).
3. Números são **acumulados** se não filtrar competência (a filha não tem data) — rotular isso.
4. Entregar o arquivo e explicar a limitação de dimensões.

> Já existe uma tool no servidor (`centro_custo`, v1.16.0) que faz esse cruzamento ao vivo — use-a
> para conferência rápida; a planilha é para o detalhamento/BI.
