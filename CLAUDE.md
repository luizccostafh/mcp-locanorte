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
- Arquivo principal: `server.py` (contrato **v1.12.0**)

## COMO (rodar / deploy)
- Build Command (Render): `pip install -r requirements.txt`
- Start Command (Render): `python server.py`
- Auto-Deploy: **On Commit** (todo push na `main` redeploya sozinho)
- URL pública: `https://mcp-locanorte.onrender.com`
- **Endpoint MCP: `https://mcp-locanorte.onrender.com/mcp`** (Streamable HTTP)
- Local: `python server.py` sobe em `0.0.0.0:8000` (fallback quando não há `$PORT`)

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

## TOOLS ATUAIS (v1.12.0 — dados reais, retornam dict/JSON) — 8 tools
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
- `dre_resultado(ano?, competencia?)` → **(v1.7.0/v1.10.0)** Resultado Operacional separando
  REALIZADO x PROJETADO. Fonte primária = DRE; se a `tabela_dre_omie` estiver vazia, **fallback por
  TÍTULOS** (contas a receber − contas a pagar por competência) rotulado como **APROXIMAÇÃO**
  (inclui não-operacionais; o oficial exige reconstruir a `tabela_dre_omie`).
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
3. ✅ **DRE oficial (correção 2026-07-07)**: a `tabela_dre_omie` **NÃO está mais vazia** no destino 40059
   (1303 linhas, sync 2026-06-23; detalhe completo em @HANDOFF.md, seção 6.1). O `server.py` já usa a
   DRE como fonte primária para competências fechadas (ex.: `2026-06`); `faturamento`/`dre_resultado`
   só caem no fallback (NFS-e/títulos) para o mês corrente ainda em aberto — comportamento correto.
   ⚠️ Pendências: (a) `dre_resultado()` não tem a mesma guarda de `linhas_consideradas > 0` que
   `faturamento()` tem — pode reportar `resultado_total: 0` em vez de cair pro fallback quando a
   competência pedida ainda não tem linha na DRE; (b) o gap antes observado entre Receita Líquida
   (DRE) e NFS-e do mês é, em boa parte, efeito do corte de fechamento contábil em 25/jun (não é
   inconsistência de dados) — ver @HANDOFF.md, seção 6.1.
4. ✅ **Sync do Kondado (correção 2026-07-07)**: datas reais por área — títulos/DRE/categorias em
   `2026-06-23`; saldo bancário (`omie_saldo_conta_corrente`), Ordens de Serviço e NFS-e em `2026-06-17`
   (mais antigo). `coletas`, `centro_custo` e `caixa_hoje` refletem esse corte mais antigo — conferir a
   cadência do pipeline dessas tabelas operacionais especificamente.
   ✅ O bug de `caixa_hoje.data_saldo_base` voltar com data FUTURA foi corrigido na v1.11.1 (ignora linhas
   de saldo com data futura). O frescor em si depende de religar o sync — ação no Kondado, não no código.
5. Governança: religar `enable_dns_rebinding_protection=True` com allowlist do domínio + auth por token.
   Inclui rotação periódica do `KONDADO_TOKEN` → menu ☰ do destino Via Kondado → "Alterar token"
   → atualizar no Render → validar com as tools (procedimento completo em @HANDOFF.md, seção 10).
6. Custo: avaliar baixar Render de **Standard** para **Starter** ($7/mês, também always-on).

## DESTINO KONDADO (atenção — erro já cometido)
Há dois destinos Via Kondado: **40059** (VIVO — é o que o `server.py` lê via `KONDADO_TOKEN`) e
**39010** (MORTO — `SCHEMA_NOT_FOUND`). O conector **MCP nativo do Kondado** (`run_query`) aponta
para o 39010 → não serve para amostrar os dados que o servidor usa. Para inspecionar os dados reais,
use o hub CSV (40059) que o próprio servidor consome. As integrações financeiras foram consolidadas
no conector Omie **39483 → destino 40059**.

## CONVENÇÕES
- Idioma do projeto: PT-BR.
- Toda mudança no `server.py` → commit na `main` → Render redeploya automático.
- Validar endpoint pelo navegador: `/mcp` deve responder JSON-RPC
  `"Not Acceptable: Client must accept text/event-stream"` (= servidor OK).
