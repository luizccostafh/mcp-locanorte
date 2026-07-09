# Modelo Power BI — Locanorte Caçambas e Resíduos

> Análise da camada Kondado (destino **40059**) para construção do modelo estrela e das
> medidas DAX do Power BI. Segue a metodologia padrão: tabelas → fato/dimensão → granularidade
> → relacionamentos → **conferência de totais** → DAX → KPIs → dashboards → riscos.
>
> Levantado em 2026-07-09 via `MCP_KONDADO` (`list_tables` / `get_table_schema` / `run_query`).

⚠️ **Achado preliminar:** o `HANDOFF.md` registra que o MCP nativo do Kondado (`run_query`)
aponta para o destino **39010 (morto, `SCHEMA_NOT_FOUND`)**. Neste levantamento, porém, o mesmo
conector retornou dados reais cujas datas de sync batem exatamente com o destino **40059** descrito
no HANDOFF (títulos/DRE/categorias em `2026-06-23`; saldo/OS/NFS-e em `2026-06-17`). Ou seja, o
conector parece ter sido **reapontado para o 40059** em algum momento entre 2026-07-07 e hoje.
Recomendo confirmar isso no painel do Kondado antes de usar este MCP como fonte oficial de
amostragem — se confirmado, vale atualizar o HANDOFF.md (seção "Destino Kondado").

---

## 1. Tabelas disponíveis (destino 40059)

53 tabelas no total. Agrupadas por domínio de negócio:

| Domínio | Tabelas |
|---|---|
| **Contas a pagar** | `omie_lancamentos_contas_pagar`, `..._categorias`, `..._distribuicao` |
| **Contas a receber** | `omie_lancamentos_contas_receber`, `..._categorias`, `..._distribuicao` |
| **DRE / plano de contas** | `tabela_dre_omie`, `omie_categorias`, `omie_dre_contas` |
| **Consolidado novo (2026-07-07)** | `locanorte_kondado_mcp`, `lancamentos_omie` (schemas idênticos) |
| **Operação (OS/coletas)** | `omie_servicos_ordens_de_servico`, `..._departamentos`, `..._servicosprestados`, `..._parcelas`, `..._faturamento` |
| **Faturamento fiscal** | `omie_servicos_nfse`, `..._listaservicos`, `omie_recebimento_notas_fiscais*` |
| **Caixa / bancos** | `omie_saldo_conta_corrente`, `omie_contas_correntes`, `omie_conta_corrente_lancamentos*`, `omie_bancos` |
| **Cadastros** | `omie_clientes`, `..._tags`, `..._caracteristicas`, `omie_departamentos`, `omie_projetos`, `omie_contatos`, `omie_empresas*` |
| **Fiscal (config, sem valor de BI)** | `omie_impostos_*` (7 tabelas), `omie_cenarios_de_impostos_detalhes` (**857.267 linhas** — não importar), `omie_transferencia_finalidade` |
| **Vazias / não usadas** | `omie_entrada_nota*` (0 linhas), `omie_contas_tags` (0), `omie_contas_caracteristicas` (0) |

---

## 2. Classificação fato vs. dimensão + granularidade

### Fatos

| Tabela | Grão | Linhas | Observação de granularidade |
|---|---|---|---|
| `omie_lancamentos_contas_pagar` | 1 título/parcela a pagar | 1.719 | chave `codigo_lancamento_omie` |
| `omie_lancamentos_contas_pagar_categorias` | título × categoria rateada | 1.909 | 190 títulos rateiam >1 categoria |
| `omie_lancamentos_contas_pagar_distribuicao` | título × centro de custo rateado | 2.076 | traz `distribuicao_ccoddep` — **é aqui que mora o CC das contas a pagar** (pendência do HANDOFF, resolvida) |
| `omie_lancamentos_contas_receber` | 1 título/parcela a receber | 456 | chave `codigo_lancamento_omie` |
| `omie_lancamentos_contas_receber_categorias` | título × categoria rateada | 526 | |
| `omie_lancamentos_contas_receber_distribuicao` | título × centro de custo rateado | 219 | ⚠️ cobre só **48%** dos títulos a receber — os demais ficam sem CC atribuído |
| `tabela_dre_omie` | linha do plano DRE (n1..n6) × competência | 1.315 | já vem pré-agregada; **não tem `codigo_categoria`** — não junta linha-a-linha com título |
| `locanorte_kondado_mcp` / `lancamentos_omie` | lançamento × categoria rateada (pagar+receber unificado, `valor_dre` já calculado) | 2.222 / 2.203 | schemas idênticos entre si — confirmar se são a mesma fonte exposta 2x; **ainda sem centro de custo** |
| `omie_servicos_ordens_de_servico` (cabeçalho) | 1 OS = 1 locação/coleta de caçamba | 2.392 | carrega `informacoesadicionais_ncodcc` **direto no cabeçalho** (fonte principal de CC da receita) |
| `omie_servicos_ordens_de_servico_departamentos` | OS × departamento rateado | 237 | cobre só ~10% das OS — maioria usa 1 CC único do cabeçalho |
| `omie_servicos_ordens_de_servico_servicosprestados` | OS × item de serviço prestado | 4.359 | ~1,8 itens/OS |
| `omie_servicos_ordens_de_servico_parcelas` | OS × parcela de faturamento | 2.392 | 1:1 (1 parcela por OS, em média) |
| `omie_servicos_nfse` | 1 NFS-e emitida | 2.392 | liga à OS via `ordemservico_ncodigoos` |
| `omie_saldo_conta_corrente` | conta corrente × dia | 747 | série diária; **inclui datas futuras projetadas** — filtrar `data_saldo <= hoje` |

### Dimensões

| Tabela | Chave | Linhas | Observação |
|---|---|---|---|
| `omie_clientes` | `codigo_cliente_omie` | 62 | |
| `omie_clientes_tags` | `codigo_cliente_omie` (multivalorada) | 66 | bridge cliente×tag |
| `omie_clientes_caracteristicas` | `codigo_cliente_omie` | 1 | ⚠️ praticamente vazia — não dá para segmentar por característica ainda |
| `omie_categorias` | `codigo` | 323 | 180 ativas / 143 inativas; traz hierarquia DRE n1-n6 |
| `omie_dre_contas` | `codigodre` | 28 | estrutura oficial do plano DRE |
| `omie_departamentos` | `codigo` | 106 | 78 ativos / 28 inativos — candidata a **Dim Centro de Custo**, mas ⚠️ ver risco abaixo |
| `omie_projetos` | `codigo` | 80 | 56 ativos / 24 inativos |
| `omie_contas_correntes` | `ncodcc` | 9 | dimensão banco/conta |
| **Dim Calendário** | — | — | não existe pronta; criar no Power BI (`CALENDAR`/`CALENDARAUTO`) |

---

## 3. Relacionamentos sugeridos no Power BI

Modelo em **galáxia** (dois fatos centrais — Financeiro e Operacional — compartilhando dimensões):

```
Dim Cliente/Fornecedor ──┐
Dim Categoria ───────────┤
Dim Centro de Custo ─────┼──< Fato Contas a Pagar (+ rateio Categoria, + rateio CC)
Dim Projeto ─────────────┤
Dim Data ─────────────────┘

Dim Cliente/Fornecedor ──┐
Dim Categoria ───────────┤
Dim Centro de Custo ─────┼──< Fato Contas a Receber (+ rateio Categoria, + rateio CC)
Dim Projeto ─────────────┤
Dim Data ─────────────────┘

Dim Cliente ──────────────┐
Dim Centro de Custo ──────┼──< Fato Ordens de Serviço (coletas) ──< Fato NFS-e
Dim Data ──────────────────┘

Dim Conta Corrente ───< Fato Saldo Diário

Dim Data ───< Fato DRE (hierarquia n1..n6 já embutida na própria tabela)
```

Pontos de atenção na modelagem:

- **Cross-filter**: Dim → Fato em direção única (dimensão filtra fato). As tabelas de rateio
  (`_categorias`, `_distribuicao`) são fato-a-fato em grão mais fino — tratar como tabelas
  auxiliares do fato-pai via `codigo_lancamento_omie`, não como dimensões.
- **Datas múltiplas por fato**: contas a pagar/receber têm `data_emissao`, `data_previsao`,
  `data_vencimento`. Deixar **uma** relação ativa (recomendo `data_vencimento`, para bater com
  `fluxo_caixa()` do MCP) e usar `USERELATIONSHIP()` nas medidas que precisam das outras
  (ex.: DRE por competência = `data_emissao`).
- **Dim Centro de Custo**: usar `omie_departamentos` como base, mas criar uma coluna/flag
  "É caminhão?" — o cadastro fixo da empresa lista **16 centros de custo** (15 caminhões + ALADIM),
  contra **106** linhas em `omie_departamentos`. Sem esse filtro, os dashboards de "custo por
  caminhão" vão misturar departamentos administrativos com veículos.
- **Risco de dupla contagem**: `valor_documento` no título-mãe é o valor cheio do documento. Ao
  analisar por categoria ou centro de custo, somar sempre os valores **já fracionados**
  (`categorias_valor`, `distribuicao_nvaldep`), nunca `valor_documento` da tabela-mãe junto com
  as tabelas de rateio — duplica o total.

---

## 4. Conferência de totais (ANTES do DAX definitivo)

Rodei uma amostragem agregada via `MCP_KONDADO` para viabilizar a conferência — **os números
abaixo precisam ser validados contra os relatórios nativos do Omie** antes de qualquer medida DAX
ser considerada definitiva.

### Contas a pagar — total por status (`omie_lancamentos_contas_pagar.valor_documento`)

| Status | Valor (R$) |
|---|--:|
| PAGO | 1.691.949,31 |
| A VENCER | 1.513.717,20 |
| CANCELADO | 307.763,92 |
| ATRASADO | 36.929,07 |
| VENCE HOJE | 8.952,91 |
| **Total geral (com cancelado)** | **3.559.312,41** |
| **Em aberto** (A VENCER + ATRASADO + VENCE HOJE) | **1.559.599,18** |

### Contas a receber — total por status (`omie_lancamentos_contas_receber.valor_documento`)

| Status | Valor (R$) |
|---|--:|
| RECEBIDO | 1.623.129,00 |
| A VENCER | 387.363,18 |
| CANCELADO | 303.289,20 |
| VENCE HOJE | 54.830,00 |
| ATRASADO | 7.100,00 |
| **Total geral (com cancelado)** | **2.375.711,37** |
| **Em aberto** (A VENCER + ATRASADO + VENCE HOJE) | **449.293,18** |

### Cadastros — ativos vs. inativos

| Cadastro | Ativos | Inativos | Total |
|---|--:|--:|--:|
| Categorias | 180 | 143 | 323 |
| Centros de custo (`omie_departamentos`) | 78 | 28 | 106 |
| Projetos | 56 | 24 | 80 |

### Checklist de conferência (pendente de validação do usuário)

- [ ] Total a pagar em aberto (**R$ 1.559.599,18**) bate com o relatório "Contas a Pagar" do Omie?
- [ ] Total a receber em aberto (**R$ 449.293,18**) bate com o relatório "Contas a Receber" do Omie?
- [ ] As 180 categorias ativas correspondem ao cadastro de categorias ativo no Omie?
- [ ] Dos 78 centros de custo ativos em `omie_departamentos`, quais são realmente os 16
      centros de custo operacionais (15 caminhões + ALADIM) do cadastro da empresa?
- [ ] Os 56 projetos ativos fazem sentido para o negócio (a empresa usa "projeto" como dimensão
      gerencial no Omie, ou é um campo pouco usado)?
- [ ] `data_vencimento`, `data_previsao`, `data_emissao` e `data_competencia` (na
      `locanorte_kondado_mcp`) têm o significado esperado em cada tabela — confirmar com o time
      financeiro qual data cada relatório do Omie usa como referência.

> Enquanto este checklist não for confirmado, trate as medidas DAX da seção 5 como **rascunho**.

---

## 5. Medidas DAX (rascunho — sujeito a ajuste após a conferência)

```dax
-- ===== FLUXO DE CAIXA / DINHEIRO =====

Total a Pagar (Aberto) =
CALCULATE(
    SUM('Fato Contas a Pagar'[valor_documento]),
    'Fato Contas a Pagar'[status_titulo] IN {"A VENCER","ATRASADO","VENCE HOJE"}
)

Total a Receber (Aberto) =
CALCULATE(
    SUM('Fato Contas a Receber'[valor_documento]),
    'Fato Contas a Receber'[status_titulo] IN {"A VENCER","ATRASADO","VENCE HOJE"}
)

Saldo em Caixa (Hoje) =
VAR UltimaData =
    CALCULATE(
        MAX('Fato Saldo Diário'[data_saldo]),
        'Fato Saldo Diário'[data_saldo] <= TODAY()
    )
RETURN
    CALCULATE(
        SUM('Fato Saldo Diário'[nsaldoatual]),
        'Fato Saldo Diário'[data_saldo] = UltimaData
    )

-- ===== INADIMPLÊNCIA =====

Inadimplência (R$) =
CALCULATE(
    SUM('Fato Contas a Receber'[valor_documento]),
    'Fato Contas a Receber'[status_titulo] = "ATRASADO"
)

Inadimplência (%) =
DIVIDE([Inadimplência (R$)], [Total a Receber (Aberto)])

-- ===== DRE GERENCIAL =====

Receita Líquida (DRE) =
CALCULATE(
    SUM('Fato DRE'[valor]),
    'Fato DRE'[descricaodre_n1] = "Receita Líquida Operacional",  -- ajustar ao marcador real
    'Fato DRE'[totalizadre] = "S"
)

Resultado Operacional (DRE) =
CALCULATE(
    SUM('Fato DRE'[valor]),
    'Fato DRE'[niveldre] = "1"   -- ajustar ao nível que representa o resultado final
)

-- ===== MARGEM / CUSTO POR CAMINHÃO =====

Receita Centro de Custo (OS) =
CALCULATE(
    SUM('Fato OS'[cabecalho_nvalortotal]),
    'Fato OS'[infocadastro_ccancelada] = "N"
)

Custo Centro de Custo (Rateado) =
SUM('Fato Rateio CC Pagar'[distribuicao_nvaldep])

Rentabilidade Centro de Custo =
[Receita Centro de Custo (OS)] - [Custo Centro de Custo (Rateado)]

Margem % Centro de Custo =
DIVIDE([Rentabilidade Centro de Custo], [Receita Centro de Custo (OS)])

-- ===== RESULTADO POR CLIENTE =====

Faturamento Cliente (OS) =
CALCULATE(
    SUM('Fato OS'[cabecalho_nvalortotal]),
    'Fato OS'[infocadastro_ccancelada] = "N"
)

Contas a Receber Cliente (Aberto) =
CALCULATE(
    SUM('Fato Contas a Receber'[valor_documento]),
    'Fato Contas a Receber'[status_titulo] IN {"A VENCER","ATRASADO","VENCE HOJE"}
)

-- ===== RASTREABILIDADE =====

Qtd Títulos sem Centro de Custo (Receber) =
VAR ComCC =
    DISTINCTCOUNT('Fato Rateio CC Receber'[codigo_lancamento_omie])
VAR Total =
    DISTINCTCOUNT('Fato Contas a Receber'[codigo_lancamento_omie])
RETURN
    Total - ComCC
```

---

## 6. KPIs por prioridade

| Prioridade | KPI | Medida base |
|---|---|---|
| Dinheiro | Saldo em caixa hoje | `Saldo em Caixa (Hoje)` |
| Dinheiro | Projeção de caixa 7/15/30d | `Total a Pagar/Receber (Aberto)` por janela de vencimento |
| Fluxo de caixa | Aging de vencimento (vencido / 7 / 15 / 30 / 30+) | `Total a Pagar/Receber` segmentado por `data_vencimento` |
| Inadimplência | % de recebíveis atrasados | `Inadimplência (%)` |
| Inadimplência | Dias médios de atraso | `AVERAGEX` sobre `HOJE - data_vencimento` dos títulos `ATRASADO` |
| DRE gerencial | Receita Líquida do mês | `Receita Líquida (DRE)` |
| DRE gerencial | Resultado Operacional Realizado x Projetado | `Resultado Operacional (DRE)` + fallback por títulos |
| Margem | Margem % por centro de custo | `Margem % Centro de Custo` |
| Custo por caminhão | Ranking de rentabilidade por CC | `Rentabilidade Centro de Custo` (ordenado) |
| Custo por caminhão | Receita por OS/coleta (produtividade) | `Receita Centro de Custo (OS)` ÷ contagem de OS |
| Resultado por cliente | Top clientes por faturamento | `Faturamento Cliente (OS)` |
| Resultado por cliente | Exposição em aberto por cliente | `Contas a Receber Cliente (Aberto)` |
| Decisão | Cobertura de caixa (dias) | `Saldo em Caixa (Hoje)` ÷ média diária de saídas |
| Rastreabilidade | % de títulos sem centro de custo atribuído | `Qtd Títulos sem Centro de Custo` ÷ total |

---

## 7. Dashboards executivos sugeridos

1. **Visão Financeira** — saldo em caixa hoje, aging de a pagar/receber, inadimplência, projeção
   7/15/30 dias. Público: diretoria/financeiro, atualização diária.
2. **DRE Gerencial** — receita líquida, custos por categoria, resultado por competência,
   Realizado x Projetado, comparação mês a mês. Público: diretoria, atualização mensal (fechamento).
3. **Operação por Caminhão** — receita, custo, margem % e ranking por centro de custo; produtividade
   (OS por caminhão); breakdown por etapa/tipo de serviço. Público: operação, atualização diária/semanal.
4. **Carteira de Clientes** — top clientes por faturamento e por exposição em aberto, ticket médio,
   concentração de receita (cliente âncora Novo Nordisk vs. demais). Público: comercial/financeiro.

---

## 8. Riscos, inconsistências e dados ausentes

- **Discrepância de destino do MCP_KONDADO** (ver alerta no topo) — o HANDOFF.md registra esse
  conector como apontando para o destino morto (39010), mas os dados retornados batem com o 40059
  vivo. Confirmar no painel do Kondado e atualizar a documentação se for o caso.
- **Centro de custo em contas a pagar/receber só existe na tabela filha de rateio**
  (`distribuicao_ccoddep`), confirmando a suspeita do HANDOFF — porém a cobertura em contas a
  receber é de apenas 48% dos títulos; os demais ficam sem CC atribuído.
- **`omie_departamentos` (106 linhas) ≠ 16 centros de custo operacionais** do cadastro fixo da
  empresa — necessário mapear/filtrar quais códigos são caminhões antes de qualquer dashboard de
  "custo por caminhão".
- **`omie_clientes_caracteristicas` praticamente vazia** (1 linha) — não há base ainda para
  segmentar clientes por característica, apesar de estar no roadmap do HANDOFF.
- **`tabela_dre_omie` não tem `codigo_categoria`** — vem pré-agregada por nível/competência; cruzar
  com títulos individuais exige a lógica de rateio já calculada em `locanorte_kondado_mcp.valor_dre`
  (que, por sua vez, ainda não tem centro de custo).
- **Datas de sync divergentes por domínio**: títulos/DRE/categorias em `2026-06-23`;
  saldo/OS/NFS-e em `2026-06-17`. Qualquer relatório cruzando os dois domínios (ex.: rentabilidade
  por caminhão = receita da OS × custo do título) mistura frescores diferentes.
- **`omie_saldo_conta_corrente` é série diária com datas futuras projetadas** — sempre filtrar
  `data_saldo <= HOJE`, mesma regra já aplicada no `server.py` (fix v1.11.1).
- **`locanorte_kondado_mcp` e `lancamentos_omie` têm schema idêntico** — confirmar se é a mesma
  fonte exposta duas vezes (para não importar duplicado no Power BI) ou se há diferença de negócio
  entre elas.
- **Risco de dupla contagem** ao somar `valor_documento` da tabela-mãe junto com as tabelas de
  rateio (`_categorias`, `_distribuicao`) — usar sempre os valores já fracionados nas análises por
  categoria/centro de custo.
- **`omie_cenarios_de_impostos_detalhes`** tem 857.267 linhas de configuração fiscal, sem valor de
  BI — não importar para o Power BI (pesaria o modelo à toa).

---

## Próximos passos

1. Validar o checklist da seção 4 com o time financeiro (Omie nativo).
2. Mapear os 16 centros de custo operacionais dentro de `omie_departamentos`.
3. Confirmar a natureza de `locanorte_kondado_mcp` vs. `lancamentos_omie`.
4. Após validação, fechar as medidas DAX da seção 5 e publicar o `.pbix` inicial.
