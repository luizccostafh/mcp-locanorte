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
- Arquivo principal: `server.py` (contrato **v1.5.0**)

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
| `PORT` | injetada pelo Render | `8000` | nunca fixar porta no código |

## REGRAS DE OURO (erros já cometidos — NÃO repetir)
1. **Bind sempre em `0.0.0.0` e na porta `os.environ["PORT"]`** — nunca `127.0.0.1` nem porta fixa.
   No Render, `127.0.0.1`/porta fixa causa deploy "Timed Out" (porta não detectada).
2. **Transporte = `streamable-http`** (endpoint `/mcp`). Não usar `sse_app()` (SSE está deprecated no Claude).
3. **`TransportSecuritySettings` deve ser definido NA CONSTRUÇÃO do `FastMCP`**, não depois via
   `mcp.settings.*`. Como `host` default é `127.0.0.1`, a proteção anti-DNS-rebinding ativa sozinha
   travada em localhost → rejeita o domínio do Render com "Invalid Host header".
   Por isso passamos `host="0.0.0.0"` e `transport_security=...` direto no construtor.
4. Health check do Render bate em `HEAD /` e recebe `404` — isso é **normal** (o MCP vive em `/mcp`).
5. **Não rebaixar as tools para placeholder.** O `server.py` já é v1.5.0 com integração Kondado
   real (degradação graciosa em camadas). Evoluir, nunca substituir por "esqueleto".
6. **Kondado redireciona para o S3 (`302 Found`).** `GET /data/<tabela>` responde 302 → arquivo
   em `hub-kondado.s3.amazonaws.com/.../data.csv`. O httpx **não segue redirect por padrão**,
   então o 302 estoura em `raise_for_status()` e todo o financeiro vira "indisponível".
   Correção: criar o client com `httpx.Client(..., follow_redirects=True)` em `_fetch_csv`.

## TOOLS ATUAIS (v1.5.0 — dados reais, retornam dict/JSON)
- `status_locanorte()` → health-check estruturado: serviço, status, transporte,
  `contrato_versao`, `kondado_configurado` (bool), `data_referencia` (TZ America/Sao_Paulo).
- `resumo_locanorte()` → resumo gerencial: base cadastral (sempre) + bloco `financeiro` ao vivo
  do Kondado (faturamento do mês via DRE, contas a pagar e a receber com top categorias).
  Cada sub-bloco é protegido isoladamente: falha de um não derruba o resto.
- `fluxo_caixa()` → **(v1.5.0)** caixa hoje (último saldo por conta corrente, com `data_saldo_base`),
  vencimentos por janela (vencido / 7d / 15d / 30d / 30d+) de contas a pagar e a receber EM ABERTO,
  e projeção curta (7/15/30d). Filtro de "em aberto" é o **mesmo** `_esta_em_aberto` do `resumo_locanorte`
  (garante que `total_aberto` bata com `valor_em_aberto`). Projeção **conservadora**: paga o vencido,
  mas não conta recebível vencido como entrada. Degradação graciosa por bloco.

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
2. ✅ `fluxo_caixa` entregue (v1.5.0). Próximas tools operacionais: caçambas alocadas, status de coletas, clientes.
   Requer no warehouse a tabela `omie_saldo_conta_corrente` e a coluna `data_vencimento` nos títulos.
3. Parâmetros tipados nas tools (ex.: competência/mês como argumento).
4. Governança: religar `enable_dns_rebinding_protection=True` com allowlist do domínio + auth por token.
   Inclui rotação periódica do `KONDADO_TOKEN` → menu ☰ do destino Via Kondado → "Alterar token"
   → atualizar no Render → validar com as tools (procedimento completo em @HANDOFF.md, seção 10).
5. Custo: avaliar baixar Render de **Standard** para **Starter** ($7/mês, também always-on).

## CONVENÇÕES
- Idioma do projeto: PT-BR.
- Toda mudança no `server.py` → commit na `main` → Render redeploya automático.
- Validar endpoint pelo navegador: `/mcp` deve responder JSON-RPC
  `"Not Acceptable: Client must accept text/event-stream"` (= servidor OK).
