# CLAUDE.md — MCP Locanorte

> Memória de projeto para o Claude Code. Lida automaticamente no início de cada sessão.
> Contexto completo da construção em @HANDOFF.md

## POR QUÊ (objetivo)
Servidor **MCP (Model Context Protocol) remoto** da **Locanorte Caçambas e Resíduos Ltda.**,
para que o Claude (claude.ai) consulte dados/ações da empresa sob demanda via conector.
As tools JÁ entregam dados financeiros reais (via Kondado). A evolução continua para mais
dados operacionais (caçambas, coletas, clientes) e governança.

## O QUÊ (stack)
- Linguagem: **Python 3** (rodando 3.14 no Render)
- Framework MCP: **FastMCP** (pacote `mcp`, transporte **Streamable HTTP**)
- HTTP client: **httpx** (consome o hub do Kondado em CSV)
- Repositório: GitHub `luizccostafh/mcp-locanorte`, branch `main`
- Hospedagem: **Render** (Web Service, plano **Standard**, always-on)
- Arquivo principal: `server.py` (contrato **v1.15.0**)

## COMO (rodar / deploy)
- Build Command (Render): `pip install -r requirements.txt`
- Start Command (Render): `python server.py`
- Auto-Deploy: **On Commit** (todo push na `main` redeploya sozinho)
- URL pública: `https://mcp-locanorte.onrender.com`
- **Endpoint MCP: `https://mcp-locanorte.onrender.com/mcp`** (Streamable HTTP)
- Local: `python server.py` sobe em `0.0.0.0:8000` (fallback quando não há `$PORT`)

## COMANDOS ÚTEIS (não há suíte de testes automatizados neste repo)
Repo de um único arquivo (`server.py`) sem `pytest`/linter configurado. Para validar uma mudança:
1. **Checagem de sintaxe:** `python -m py_compile server.py` (rápido, pega erro de sintaxe/import antes do commit).
2. **Rodar local:** `python server.py` → sobe em `0.0.0.0:8000`. Sem `KONDADO_TOKEN` no ambiente local,
   `status_locanorte` funciona normalmente (`kondado_configurado: false`) e `resumo_locanorte` entrega
   só a base cadastral (financeiro `"indisponivel"`) — isso é esperado, não é bug.
3. **Smoke-test do endpoint** (local ou produção): `curl -s http://localhost:8000/mcp` (ou a URL do Render)
   deve responder o JSON-RPC `"Not Acceptable: Client must accept text/event-stream"` — é o sinal de que
   o transporte `streamable-http` está de pé (ver CONVENÇÕES).
4. Para validar uma tool específica de ponta a ponta, é preciso um `KONDADO_TOKEN` válido (só existe no
   Render) e chamar via um cliente MCP (ex.: o conector do Claude) — não há mock do Kondado neste repo.
5. Push na `main` → Render redeploya sozinho (Auto-Deploy On Commit); confira os logs do deploy
   (`Application startup complete`, `Uvicorn running on 0.0.0.0:$PORT`) e então revalide pelas tools.

## ⚙️ VARIÁVEIS DE AMBIENTE (Render → Environment) — OBRIGATÓRIO
Sem `KONDADO_TOKEN`, todo o bloco financeiro de `resumo_locanorte` retorna
`status: "indisponivel"` (entrega só a base cadastral). Verificado ao vivo em 2026-06-16:
após setar o token, `kondado_configurado=true`; o financeiro só destravou de fato
depois do fix `follow_redirects=True` (ver Regra de Ouro nº6).

| Variável | Obrigatória? | Default no código | Observação |
|----------|--------------|-------------------|------------|
| `KONDADO_TOKEN` | **SIM** | `""` (vazio) | Sem ele → financeiro indisponível |
| `KONDADO_BASE_URL` | não | `https://hub.kondado.io/data` | |
| `KONDADO_TIMEOUT` | não | `20` | segundos |
| `KONDADO_TBL_*` | não | nomes confirmados no modelo | tabelas Omie no warehouse |
| `KONDADO_COL_*` | não | colunas confirmadas via .pbix | |
| `KONDADO_STATUS_ABERTO` | não | `A VENCER,ATRASADO,VENCE HOJE` | status contados como "em aberto" |
| `KONDADO_STATUS_CANCELADO` | não | `CANCELADO` | status excluídos do total |
| `KONDADO_DRE_NIVEIS` | não | `descricaodre_n1…n6` | níveis do DRE varridos p/ achar receita |
| `KONDADO_DRE_RECEITA_MARCADOR` | não | `Receita` | marcador da Receita Líquida Operacional |
| `KONDADO_DRE_N1_RESULTADO` | não | `1,2` | grupos n1 do DRE que compõem o Resultado Operacional ((1)+(2)); exclui (3) CAPEX e não-classificados |
| `KONDADO_DRE_COMPETENCIA` | não | mês corrente | forçar competência YYYY-MM |
| `KONDADO_COL_VENCIMENTO` | não | `data_vencimento` | coluna de vencimento (janelas do `fluxo_caixa`) |
| `KONDADO_TBL_SALDO` | não | `omie_saldo_conta_corrente` | tabela de saldo de contas correntes (`fluxo_caixa`) |
| `KONDADO_COL_SALDO_CONTA` | não | `ncodcc` | código da conta corrente |
| `KONDADO_COL_SALDO_DATA` | não | `data_saldo` | data do saldo (pega o mais recente por conta) |
| `KONDADO_COL_SALDO_DESC` | não | `cdescricao` | descrição/nome da conta |
| `KONDADO_COL_SALDO_ATUAL` | não | `nsaldoatual` | saldo atual |
| `KONDADO_COL_SALDO_DISP` | não | `nsaldodisponivel` | saldo disponível |
| `KONDADO_TBL_CATEGORIAS` | não | `omie_categorias` | de-para categoria (fallback do DRE) |
| `KONDADO_TBL_NFSE` | não | `omie_servicos_nfse` | faturamento via NFS-e (fallback do DRE) |
| `KONDADO_TBL_CLIENTES` | não | `omie_clientes` | de-para código→NOME do cliente |
| `KONDADO_COL_CLIENTE_COD` | não | `codigo_cliente_omie` | chave do de-para de clientes |
| `KONDADO_COL_CLIENTE_NOME` | não | `razao_social` | nome do cliente |
| `KONDADO_COL_TITULO_DATA` | não | `data_emissao` | competência dos títulos (fallback do `dre_resultado`) |
| `KONDADO_TBL_OS` | não | `omie_servicos_ordens_de_servico` | Ordens de Serviço (`coletas`/`centro_custo`) |
| `KONDADO_TBL_OS_SERV` | não | `..._servicosprestados` | tipos de serviço por OS (`coletas`) |
| `KONDADO_COL_PAGAR_CC` | não | `ncodcc` | coluna de centro de custo nas contas a pagar (`centro_custo`) |
| `KONDADO_TBL_CC` | não | `""` (vazio) | cadastro centro de custo→NOME do caminhão (`centro_custo`, opt-in) |
| `KONDADO_COL_CC_COD` | não | `codigo` | código no cadastro de centro de custo |
| `KONDADO_COL_CC_NOME` | não | `descricao` | nome do caminhão no cadastro de centro de custo |
| `PORT` | injetada pelo Render | `8000` | nunca fixar porta no código |

> Acima estão os principais. Quase tudo é auto-detectado por candidatos no código
> (`_detecta_coluna`); as env vars só são necessárias se o nome da coluna divergir.
> Lista completa de `KONDADO_COL_OS_*` / `KONDADO_COL_OSSERV_*` etc. no topo do `server.py`.

## REGRAS DE OURO (erros já cometidos — NÃO repetir)
1. **Bind sempre em `0.0.0.0` e na porta `os.environ["PORT"]`** — nunca `127.0.0.1` nem porta fixa.
   No Render, `127.0.0.1`/porta fixa causa deploy "Timed Out" (porta não detectada).
2. **Transporte = `streamable-http`** (endpoint `/mcp`). Não usar `sse_app()` (SSE está deprecated no Claude).
3. **`TransportSecuritySettings` deve ser definido NA CONSTRUÇÃO do `FastMCP`**, não depois via
   `mcp.settings.*`. Como `host` default é `127.0.0.1`, a proteção anti-DNS-rebinding ativa sozinha
   travada em localhost → rejeita o domínio do Render com "Invalid Host header".
   Por isso passamos `host="0.0.0.0"` e `transport_security=...` direto no construtor.
4. Health check do Render bate em `HEAD /` e recebe `404` — isso é **normal** (o MCP vive em `/mcp`).
5. **Não rebaixar as tools para placeholder.** O `server.py` já é v1.12.0 com integração Kondado
   real (degradação graciosa em camadas). Evoluir, nunca substituir por "esqueleto".
6. **Kondado redireciona para o S3 (`302 Found`).** `GET /data/<tabela>` responde 302 → arquivo
   em `hub-kondado.s3.amazonaws.com/.../data.csv`. O httpx **não segue redirect por padrão**,
   então o 302 estoura em `raise_for_status()` e todo o financeiro vira "indisponível".
   Correção: criar o client com `httpx.Client(..., follow_redirects=True)` em `_fetch_csv`.

## TOOLS ATUAIS (v1.15.0 — dados reais, retornam dict/JSON) — 9 tools
- `status_locanorte()` → health-check estruturado: serviço, status, transporte,
  `contrato_versao`, `kondado_configurado` (bool), `data_referencia` (TZ America/Sao_Paulo).
- `resumo_locanorte(competencia?)` → resumo gerencial: base cadastral (sempre) + bloco `financeiro`
  ao vivo (faturamento do mês, contas a pagar e a receber com top categorias). `competencia='AAAA-MM'`
  afeta só o faturamento. Cada sub-bloco protegido isoladamente.
- `faturamento(competencia?)` → **(v1.6.0)** receita de UM mês. Usa `tabela_dre_omie`; se faltar/sem
  linhas, **cai para NFS-e** (`omie_servicos_nfse`) — `fonte_faturamento` indica a origem.
- `fluxo_caixa()` → **(v1.5.0/v1.11.1)** caixa hoje (último saldo por conta, com `data_saldo_base`),
  vencimentos por janela (vencido / 7d / 15d / 30d / 30d+) de contas a pagar e a receber EM ABERTO,
  e projeção curta (7/15/30d). Mesmo `_esta_em_aberto` do resumo (`total_aberto` bate com `valor_em_aberto`).
  Projeção **conservadora**: paga o vencido, não conta recebível vencido como entrada.
  **(v1.11.1)** `_caixa_hoje` ignora linhas de saldo com data FUTURA (a tabela é série diária com dias
  projetados); só considera `data_saldo <= hoje` e expõe `linhas_futuras_ignoradas`.
- `dre_resultado(ano?, competencia?)` → **(v1.7.0/v1.10.0/v1.14.0/v1.15.0)** **RESULTADO OPERACIONAL** do DRE,
  REALIZADO x PROJETADO. **(v1.15.0)** inclui `demonstrativo_realizado`: a DRE linha a linha (por
  `descricaodre_n3`, ordenada pelo código) com subtotais por grupo n1 e o Resultado Operacional — o P&L
  completo (como no Power BI), da hierarquia já classificada da `tabela_dre_omie`.
  **(v1.14.0)** soma só os grupos operacionais do DRE (n1 (1) Lucro Bruto +
  (2) Despesas, via `KONDADO_DRE_N1_RESULTADO`) e **EXCLUI** (3) Investimentos/CAPEX e os lançamentos
  SEM classificação no DRE (não-operacionais: distribuição de lucros, transferência entre contas,
  retenções/guias descontadas em folha), reportando-os à parte em `excluidos`. Alinhado à DRE gerencial
  do Power BI (`GER Resultado Liquido` = EBIT + Res. Financeiro; CAPEX/empréstimos só no DFC). jan–jun/2026:
  **+R$ 591.420,03** (excluídos: CAPEX −80.510,06 e não-classificado +302.001,40). Fonte primária = DRE;
  se a `tabela_dre_omie` estiver vazia, **fallback por TÍTULOS** rotulado como **APROXIMAÇÃO**.
- `top_clientes(limite=10)` → **(v1.8.0/v1.10.0)** maiores clientes por contas a receber
  (`valor_total` + `valor_em_aberto`), com o **NOME** resolvido via `omie_clientes` (`fonte_nome`).
- `coletas(competencia?, limite=10)` → **(v1.11.0)** operação via Ordens de Serviço (cada OS = uma
  locação/coleta de caçamba): total e valor (exclui CANCELADA), faturadas x não faturadas, quebras por
  etapa, centro de custo (qual caminhão), cliente (NOME), tipo de serviço (`cdescserv` + soma de `nqtde`)
  e mês. `competencia='AAAA-MM'` filtra pela data de previsão. Reflete o ÚLTIMO sync do Kondado.
- `centro_custo(competencia?, limite=10)` → **(v1.12.0)** rentabilidade por **centro de custo (caminhão)**:
  cruza a RECEITA das OS (soma de `cabecalho_nvalortotal` por `informacoesadicionais_ncodcc`, exclui
  CANCELADA) com o CUSTO das contas a pagar do mesmo centro de custo (soma de `valor_documento`, exclui
  CANCELADO). Saída por CC: `receita_os`, `custo_pagar`, `rentabilidade` (= receita − custo) e `margem_pct`,
  ranqueada por rentabilidade, com `totais`. `competencia='AAAA-MM'` opcional (receita por previsão da OS,
  custo por vencimento do título). A coluna de centro de custo nas contas a pagar é AUTO-DETECTADA
  (candidatos + `KONDADO_COL_PAGAR_CC`); se não for achada (no Omie o centro de custo pode estar num
  rateio/filha), o bloco `custo` volta `indisponivel` com `colunas_disponiveis` — a receita por CC ainda
  sai (degradação graciosa). Nome do caminhão é OPT-IN via `KONDADO_TBL_CC` (default exibe o código `ncodcc`).
- `lancamentos(competencia?, limite=10)` → **(v1.13.0)** razão **UNIFICADO** de contas a pagar + a receber
  a partir da tabela curada `locanorte_kondado_mcp` (1 linha = lançamento × categoria rateada; `valor_dre`
  já assinado: PAGAR negativo, RECEBER positivo). Exclui CANCELADO. Retorna `a_receber_valor_dre`,
  `a_pagar_valor_dre`, `resultado_liquido_dre` (net) separando `resultado_realizado` x `resultado_projetado`,
  e quebras por categoria (com descrição), cliente/fornecedor (NOME) e mês. `competencia='AAAA-MM'` filtra
  pela `data_competencia`. Colunas auto-detectadas (`KONDADO_COL_MCP_*`). ⚠️ `resultado_liquido_dre` é o
  NET de TODOS os títulos (inclui não-operacionais como CAPEX/financiamentos) — **NÃO** é o Resultado
  Operacional oficial; para esse, use `dre_resultado` (fonte `tabela_dre_omie`, classificado por DRE).

## BASE CADASTRAL (hardcoded no `server.py`, sempre disponível)
Independe do Kondado — é o fallback que `resumo_locanorte` sempre entrega:
Locanorte Caçambas e Resíduos Ltda. (fantasia "Caçamba e Cia"), CNPJ 07.489.900/0001-93,
sede Montes Claros/MG, fundação 2005, 16 centros de custo (15 caminhões + ALADIM),
7 serviços ativos, cliente âncora Novo Nordisk, bancos: Sicoob, Banco do Brasil, BNB, Caixa.

## ARQUITETURA DE DADOS
```
Omie (ERP, fonte) → Kondado (ETL → data warehouse) → [este MCP] → Power BI / Claude (IA)
```
O Kondado continua como camada de integração; o MCP é a camada de acesso via IA. Convivem.
Substituição do Kondado fica para quando houver condições de internalizar o ETL.

## PRÓXIMOS PASSOS
1. ✅ **`KONDADO_TOKEN` setado no Render** + fix `follow_redirects=True` → financeiro ao vivo OK (validado 2026-06-16).
2. ✅ `fluxo_caixa` (v1.5.0), `faturamento` (v1.6.0), `dre_resultado` (v1.7.0), `top_clientes` (v1.8.0),
   `coletas` (v1.11.0) e `centro_custo` (v1.12.0 — rentabilidade por caminhão) entregues. Próximas tools:
   clientes por característica/tag, detalhe de uma OS específica.
   ⚠️ `centro_custo`: o lado do CUSTO depende de onde o Omie/Kondado guardam o centro de custo nas contas
   a pagar. Pela `lancamentos_omie`, o título financeiro não carrega `ncodcc` no próprio registro (no Omie
   o centro de custo costuma vir num rateio/distribuição/filha). Na 1ª execução, se `custo` voltar
   `indisponivel`, usar o `colunas_disponiveis` p/ apontar `KONDADO_COL_PAGAR_CC` — ou adicionar o join
   pela filha (ex.: `omie_lancamentos_contas_pagar_departamentos`) numa v1.12.1.
3. ✅ **DRE oficial DESTRAVADO (validado 2026-07-17 via conector MCP Kondado):** a `tabela_dre_omie`
   voltou a ter dados (**1.371 linhas**, `last_updated` 2026-07-16). Logo, `faturamento` e `dre_resultado`
   agora usam o **DRE oficial** — não mais os fallbacks NFS-e/títulos. A Receita está classificada
   (`(1.01) Receita Liquida Operacional → (1.01.01) Receita Bruta de Vendas`), então o `_faturamento_mes`
   (marcador "Receita") funciona via DRE. Números conferidos jan–jun/2026:
   - Receita Líquida Operacional = **R$ 1.982.578,58** (Bruta 1.987.259,20 − Deduções 4.680,62)
   - Custo dos Serviços = −937.477,67 → **Lucro Bruto = 1.045.100,91**
   - Despesas = −453.680,88 → **Resultado Operacional = +R$ 591.420,03**
   - Investimentos (CAPEX) = −80.510,06 → após investimentos = +510.909,97
   - No patamar dos **~629 mil** da referência DAX (gap = base de data `data_emissao` vs competência).
   ⚠️ Restam **R$ 302.001,40** de lançamentos SEM classificação no DRE (`niveldre`/`totalizadre` vazios):
   categorias ainda não mapeadas na estrutura do DRE no Omie — mapear para o resultado oficial fechar 100%.
   ✅ **(v1.14.0) TRATADO NO CÓDIGO:** o `dre_resultado` passou a somar SÓ os grupos operacionais
   (n1 (1)+(2)) e a reportar (3) CAPEX e o não-classificado à parte em `excluidos` → o headline já é o
   **Resultado Operacional correto (+591.420,03)**, não mais a soma bruta que misturava tudo (+812.911).
   Regra confirmada pela DRE gerencial do Power BI (`.pbix`: `GER Resultado Liquido` = EBIT + Res.
   Financeiro; CAPEX/empréstimos só no DFC) e pelo modelo de categorias v23 (guias/retenções descontadas
   em folha = "baixa de passivo — fora da DRE"). ➡️ **Ação do lado do Omie (contador):** importar o
   **`MODELO_IMPORTAR_OMIE_PLANO_CONTAS_e_CATEGORIAS_v23`** (Painel do Contador → Importar → Plano de
   Contas; e Categorias x Plano Contábil) para mapear as categorias restantes → depois do próximo sync,
   o `nao_classificado_dre` tende a zerar e o oficial fecha 100%.
   ✅ **(v1.15.0) VALIDADO com os 5 arquivos do contador** (`categorias_atual`, `.pbix`, modelo v23,
   `FECHAMENTO_202606_V5`, plano de contas): **TODAS** as categorias não-classificadas são
   intencionalmente **fora da DRE** — empréstimos, **PIS/COFINS sobre faturamento** (= "guias a recolher"
   no FECHAMENTO, caixa/passivo), adiantamentos, retenções (INSS/IRRF/ISS/consignado/VT/pensão) e
   distribuição de lucros. Ou seja, o Resultado Operacional +591.420,03 **já é o correto**; um motor de
   classificação por categoria seria **redundante** (mesmo número) e mais frágil (casamento por nome +
   snapshot que envelhece). O que a v1.15.0 agregou foi o **`demonstrativo_realizado`** (a DRE linha a
   linha, da hierarquia já classificada), não uma reclassificação.
4. ✅ **Sync do Kondado RELIGADO (validado 2026-07-17):** o pipeline voltou a rodar — títulos/categorias
   com `last_updated` em 2026-06-23, OS/saldo em 2026-06-17 e o DRE em 2026-07-16 (antes estava parado
   em 2026-05-26). `coletas`, `centro_custo` e `caixa_hoje` refletem o último sync; seguir conferindo a
   cadência do pipeline. ✅ O bug de `caixa_hoje.data_saldo_base` voltar com data FUTURA já estava
   corrigido na v1.11.1 (ignora linhas de saldo com data futura).
5. Governança: religar `enable_dns_rebinding_protection=True` com allowlist do domínio + auth por token.
   Inclui rotação periódica do `KONDADO_TOKEN` → menu ☰ do destino Via Kondado → "Alterar token"
   → atualizar no Render → validar com as tools (procedimento completo em @HANDOFF.md, seção 10).
6. Custo: avaliar baixar Render de **Standard** para **Starter** ($7/mês, também always-on).
7. 🆕 **`locanorte_kondado_mcp` — INSPECIONADA ao vivo (2026-07-17):** existe no destino **40059**
   (modelo "Kondado MCP Fin Locanorte", ID 9926) → o `server.py` PODE lê-la via hub CSV. Grão =
   1 lançamento × categoria rateada; 13 colunas: `tipo_lancamento` (PAGAR/RECEBER),
   `codigo_lancamento_omie`, `codigo_cliente_fornecedor`, `codigo_projeto`, `data_competencia`,
   `data_vencimento`, `status_titulo`, `codigo_categoria`, `percentual_categoria`, `valor_rateado`,
   `valor_dre` (com sinal), `valor_documento`.
   ⚠️ **A inspeção DERRUBOU as duas hipóteses anteriores:**
   (a) **NÃO tem centro de custo/`ncodcc`** (só `codigo_projeto`) → **NÃO** destrava o CUSTO do
       `centro_custo`.
   (b) Somar `valor_dre` **NÃO reproduz o Resultado Operacional oficial**: jan–jun/2026 dá **net
       −33.416** (todos os títulos por `data_competencia`, inclui não-operacionais/CAPEX) vs
       **+591.420** do `tabela_dre_omie`. Falta-lhe a CLASSIFICAÇÃO DRE (Receita/Custo/Despesa),
       que só existe na `tabela_dre_omie`.
   ➡️ Como o **DRE oficial voltou** (item 3), a `tabela_dre_omie` continua sendo a fonte de
   `dre_resultado`/`faturamento` — **NÃO** migrar para a `locanorte_kondado_mcp` como primária
   (regrediria o número oficial).
   ✅ **DECISÃO (2026-07-17): opção aditiva implementada — tool `lancamentos` (v1.13.0).** Expõe o
   **razão unificado pagar+receber** por competência/categoria/cliente com `valor_dre` assinado, SEM
   tocar no que já funciona (zero risco de regressão). O `resultado_liquido_dre` vem rotulado como NET
   de títulos (≠ Resultado Operacional oficial). Fallback melhorado do `_dre_resultado_titulos` fica
   como possível evolução futura (baixa prioridade, pois o DRE oficial está de pé).

## DESTINO KONDADO (atenção — erro já cometido)
Histórico: havia dois destinos Via Kondado — **40059** (VIVO — é o que o `server.py` lê via
`KONDADO_TOKEN`) e **39010** (MORTO — `SCHEMA_NOT_FOUND`). As integrações financeiras foram
consolidadas no conector Omie **39483 → destino 40059**.

> **Atualização 2026-07-17:** o conector **MCP do Kondado** (`run_query` KSQL) disponível no Claude Code
> agora aponta para um **destino VIVO** com TODAS as tabelas reais — as mesmas que o `server.py` consome
> via hub CSV. Ou seja, dá para amostrar os dados de verdade por ele (antes o `run_query` caía no 39010
> morto). Confirmado via `list_tables`/`run_query`: `tabela_dre_omie` **populada** (1.371 linhas) e uma
> **nova tabela curada** `locanorte_kondado_mcp` (2.203 linhas, `last_updated` 2026-07-07). Essa tabela
> unifica **contas a pagar + a receber** já com o **valor rateado por categoria e com sinal**
> (`tipo_lancamento`, `data_competencia`, `codigo_categoria`, `percentual_categoria`, `valor_rateado`,
> `valor_dre`, `valor_documento`). ⚠️ **Inspecionada em 2026-07-17:** NÃO tem centro de custo/`ncodcc`
> (só `codigo_projeto`) e a soma de `valor_dre` NÃO é o Resultado Operacional oficial (dá um net de
> todos os títulos). Portanto **não substitui** o `tabela_dre_omie` nem destrava o `centro_custo` —
> ver os detalhes e o uso adequado em PRÓXIMOS PASSOS, item 7.

## CONVENÇÕES
- Idioma do projeto: PT-BR.
- Toda mudança no `server.py` → commit na `main` → Render redeploya automático.
- Validar endpoint pelo navegador: `/mcp` deve responder JSON-RPC
  `"Not Acceptable: Client must accept text/event-stream"` (= servidor OK).
