# HANDOFF — Construção do MCP Locanorte

Documento de transferência de contexto. Resume o que foi construído e decidido na criação/deploy
do servidor MCP da Locanorte, para que o trabalho continue no Claude Code sem perder histórico.

> **Atualizado em 2026-06-19** para refletir o código realmente no ar (`server.py` v1.11.0,
> 7 tools, financeiro + 1ª tool operacional `coletas` validados ao vivo).
> A versão anterior deste handoff descrevia tools "placeholder"; isso já não é verdade.

---

## 1. Objetivo

Colocar no ar um **servidor MCP remoto** próprio da Locanorte e conectá-lo ao Claude (claude.ai)
como **conector personalizado**, permitindo que o Claude consulte dados/ações da empresa via
linguagem natural. A infraestrutura está **completa e funcionando**; as tools já entregam
**dados financeiros reais** via Kondado (não são mais placeholders).

---

## 2. Arquitetura (estado atual, funcionando)

```
Omie (ERP) → Kondado (ETL → data warehouse)
        │
GitHub (luizccostafh/mcp-locanorte, server.py)
        │  push na main → Auto-Deploy
        ▼
Render (Web Service · plano Standard · always-on)
        │  python server.py  →  Uvicorn em 0.0.0.0:$PORT
        ▼
Endpoint Streamable HTTP:  https://mcp-locanorte.onrender.com/mcp
        ▼
Claude → Settings → Connectors → conector "MCP Locanorte"
        ▼
Tools (7): status_locanorte, resumo_locanorte, faturamento, fluxo_caixa,
           dre_resultado, top_clientes, coletas (dados reais)
```

**Destinos Via Kondado:** **40059** = VIVO (o `server.py` lê via `KONDADO_TOKEN`);
**39010** = MORTO (`SCHEMA_NOT_FOUND`). O MCP nativo do Kondado (`run_query`) aponta para o 39010
— não serve p/ amostrar os dados do servidor; use o hub CSV (40059). Integrações no conector Omie
**39483 → destino 40059**.

Relação com o **Kondado** (decisão do usuário): o Kondado continua sendo a camada de
**ETL/integração** (Omie → data warehouse → Power BI **e** este MCP). O MCP é a camada de
**acesso via IA**. As duas convivem; o Kondado só será substituído mais adiante.

---

## 3. server.py atual (v1.11.0 — no ar)

> **Evolução v1.6.0 → v1.11.0 (resumo):** parâmetros tipados (`competencia`/`ano`/`limite`);
> tools `faturamento`, `dre_resultado`, `top_clientes`, `coletas`; FALLBACKS quando a
> `tabela_dre_omie` (kubo) está vazia — faturamento via **NFS-e**, de-para de categoria via
> **omie_categorias**, Resultado via **títulos** (aproximação), e NOME do cliente via **omie_clientes**.
> `coletas` (v1.11.0) é a 1ª tool operacional: lê as **Ordens de Serviço** (cada OS = locação/coleta
> de caçamba) e agrega por etapa, centro de custo, cliente, tipo de serviço e mês.

O arquivo já NÃO é placeholder. Estrutura real (ver `server.py` para o código completo):

- Cria `FastMCP("MCP Locanorte HTTP", host="0.0.0.0", port=$PORT, transport_security=...)`.
- Lê configuração de tabelas/colunas do Kondado via variáveis de ambiente (ver CLAUDE.md),
  incluindo status considerados "em aberto"/"cancelado" e critérios do DRE
  (`KONDADO_STATUS_ABERTO`, `KONDADO_STATUS_CANCELADO`, `KONDADO_DRE_NIVEIS`, `KONDADO_DRE_RECEITA_MARCADOR`).
- `CADASTRO`: base cadastral hardcoded (sempre disponível, independe do Kondado) — Locanorte
  Caçambas e Resíduos Ltda., CNPJ 07.489.900/0001-93, Montes Claros/MG, fundação 2005,
  16 centros de custo, 7 serviços ativos, cliente âncora Novo Nordisk.
- `_fetch_csv(tabela)` busca o hub Kondado em CSV (httpx) usando `KONDADO_TOKEN`.
- Helpers: `_to_float` (BR/EN com sinal), `_norm_cod`, `_competencia_de`, `_safe` (degradação
  graciosa por sub-bloco), `_mapa_categorias` (de-para codigo→descrição via DRE), `_set_env` (parse de status em CSV).
  **(v1.5.0)** `_parse_date` (ISO/BR → `date`), `_agora` (datetime TZ único), `_esta_em_aberto`
  (predicado central de "em aberto", agora reaproveitado por `_resumir_titulos` E `fluxo_caixa`).
- Sub-blocos de negócio: `_resumir_titulos` (pagar/receber + top categorias),
  `_faturamento_mes` (DRE, valor já com sinal → receita líquida), `_bloco_financeiro`.
  **(v1.5.0)** `_caixa_hoje` (último saldo por conta de `omie_saldo_conta_corrente`) e
  `_janelas_vencimento` (faixas vencido/7/15/30/30+ dos títulos em aberto, mesmo filtro do resumo).
- Env vars novas **(v1.5.0)**: `KONDADO_COL_VENCIMENTO` (default `data_vencimento`) +
  `KONDADO_TBL_SALDO`/`KONDADO_COL_SALDO_{CONTA,DATA,DESC,ATUAL,DISP}` (tabela de saldo de contas correntes).
- Tools expostas:
  - `status_locanorte()` → dict (health-check estruturado).
  - `resumo_locanorte()` → dict (cadastro + financeiro ao vivo).
  - `fluxo_caixa()` → dict **(v1.5.0)**: `caixa_hoje` (saldo por conta + `data_saldo_base`),
    `a_pagar`/`a_receber` por janela de vencimento e `projecao` 7/15/30d (conservadora:
    paga o vencido, não conta recebível vencido como entrada). Degradação graciosa por bloco;
    `total_aberto` casa com `valor_em_aberto` do resumo por usar o MESMO `_esta_em_aberto`.
- Bootstrap: `if __name__ == "__main__": mcp.run(transport="streamable-http")`.

**Princípio de design:** degradação graciosa em camadas — cada sub-bloco é protegido isolado;
a falha de um (ex.: DRE) não derruba os outros (ex.: títulos seguem, só sem descrição de categoria).

`requirements.txt`: `mcp>=1.27` (pin mínimo p/ garantir `mcp.server.transport_security`) + `httpx>=0.27`.
O pacote `mcp` já traz `starlette`/`uvicorn`. Python detectado no Render: 3.14.

---

## 4. Configuração do Render

| Item | Valor |
|------|-------|
| Tipo | Web Service |
| Plano | Standard (always-on, sem cold start) |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python server.py` |
| Auto-Deploy | On Commit (push na `main`) |
| Region/Subdomínio | `mcp-locanorte.onrender.com` |
| **Env var crítica** | **`KONDADO_TOKEN`** (sem ela, financeiro = indisponível) |

Nota de custo: Standard é mais caro que o necessário. **Starter ($7/mês)** também é always-on e
suficiente — avaliar downgrade em Settings → Instance Type.

---

## 5. Problemas resolvidos (para NÃO repetir)

1. **"Build Command" não existe no GitHub.** Ele vive na plataforma de deploy (Render).
2. **Deploy "Timed Out".** Causa: app subia em `127.0.0.1:8000` (loopback + porta fixa).
   Correção: bind em `0.0.0.0` e `port=int(os.environ["PORT"])`.
3. **Transporte errado (SSE) e path errado.** `app.mount("/mcp", mcp.sse_app())` expõe em `/mcp/sse`,
   e SSE está deprecated. Correção: `mcp.run(transport="streamable-http")`, endpoint `/mcp`.
4. **"Invalid Host header" no `/mcp`.** Proteção anti-DNS-rebinding ativa quando `host`=`127.0.0.1`
   na construção, travando hosts em localhost. Definir `mcp.settings.host` DEPOIS não corrige.
   Correção: `host="0.0.0.0"` + `transport_security=TransportSecuritySettings(
   enable_dns_rebinding_protection=False)` direto no construtor.

5. **Kondado passou a responder `302 Found` (redirect para o S3).** `GET /data/<tabela>` redireciona
   para `hub-kondado.s3.amazonaws.com/.../data.csv` (URL pré-assinada). O httpx não segue redirect
   por padrão → o 302 estourava em `raise_for_status()` e o financeiro inteiro caía como
   "indisponível" (mesmo com `KONDADO_TOKEN` setado). Correção: `httpx.Client(..., follow_redirects=True)`
   em `_fetch_csv`.

**Sinal de sucesso do endpoint:** abrir `/mcp` no navegador retorna JSON-RPC
`{"error":{"code":-32600,"message":"Not Acceptable: Client must accept text/event-stream"}}`.

---

## 6. Verificação ao vivo (2026-06-16)

Teste feito chamando as tools pelo conector:
- **1ª rodada (token ausente):** `status_locanorte` → `kondado_configurado: false`;
  `resumo_locanorte` → `financeiro.status = "indisponivel"`.
- **2ª rodada (após setar `KONDADO_TOKEN` no Render):** `status_locanorte` →
  **`kondado_configurado: true`**, resposta instantânea (confirma Standard always-on).
  `resumo_locanorte` → cadastro OK e `financeiro.status = "ok"`, **mas** os três sub-blocos
  (faturamento, contas a pagar, contas a receber) caíram com **`302 Found`** — o hub do
  Kondado passou a redirecionar para o S3 e o httpx não seguia o redirect.

✅ **Ação pendente nº1 (setar `KONDADO_TOKEN`) concluída.**
➡️ **Novo bloqueio resolvido no código:** `follow_redirects=True` em `_fetch_csv` (ver seção 5, item 5).
   Falta subir o `server.py` corrigido para o Render redeployar e validar os números do financeiro.

---

## 7. Conexão com o Claude (conector)

- Claude → **Settings → Connectors → Add custom connector**
- Nome: `MCP Locanorte` · URL: `https://mcp-locanorte.onrender.com/mcp` · **sem token** (authless)
- O Claude bloqueia URL duplicada ("A server with this URL already exists"). Se já existe um
  conector antigo com erro, remover o antigo e recadastrar.

---

## 8. Roadmap (próximos passos)

1. ✅ **`KONDADO_TOKEN` setado** + fix `follow_redirects=True` → financeiro ao vivo OK (2026-06-16).
2. ✅ **Tools operacionais/financeiras** — `fluxo_caixa` (v1.5.0), `faturamento` (v1.6.0),
   `dre_resultado` (v1.7.0), `top_clientes` (v1.8.0) e `coletas` (v1.11.0) entregues e validados.
   A seguir: detalhe de uma OS, ranking por centro de custo (rentabilidade por caminhão),
   clientes por tag/característica. Atenção: `coletas` e `caixa_hoje` refletem o ÚLTIMO sync
   (tabelas operacionais com `last_updated` em 2026-05-26) — conferir a cadência do pipeline.
3. ⚠️ **DRE oficial** — a `tabela_dre_omie` (kubo) está VAZIA no 40059; por isso `faturamento` cai
   p/ NFS-e e `dre_resultado` cai p/ aproximação por títulos. Reconstruir a transformação destrava
   o Resultado Operacional oficial (jan–jun ≈ +629 mil, ver a referência DAX).
4. ✅ **Parâmetros tipados** — entregue na v1.6.0 (`competencia`/`ano`/`limite`).
5. **Governança / segurança** — religar `enable_dns_rebinding_protection=True` com allowlist
   (`allowed_hosts=["mcp-locanorte.onrender.com", "mcp-locanorte.onrender.com:*"]`,
   `allowed_origins=["https://mcp-locanorte.onrender.com"]`) e auth por token.
   Inclui **rotação periódica do `KONDADO_TOKEN`** — procedimento documentado na seção 10.
6. **Custo** — avaliar downgrade Standard → Starter.
7. **Substituição futura do Kondado** — internalizar o ETL quando houver condições.

---

## 9. Como continuar no Claude Code

1. Abrir o repositório `mcp-locanorte`.
2. `CLAUDE.md` e `HANDOFF.md` já estão na raiz — o `CLAUDE.md` (que importa este `HANDOFF.md`)
   é lido automaticamente.
3. Pedir, por exemplo: "crie uma tool que lista as caçambas alocadas por cliente".

---

## 10. Procedimento — Rotação do `KONDADO_TOKEN` (token do Via Kondado)

> Governança/segurança. **Não é emergência** — é higiene; faça periodicamente ou se suspeitar
> que o token vazou. A rotação **invalida o token antigo na hora**, então só execute quando
> puder atualizar o Render em seguida (há uma janela curta de financeiro indisponível até o redeploy).

### ⚠️ Qual token é (para não mexer no errado)
O `server.py` lê dados em `https://hub.kondado.io/data/<tabela>?token=...`. Esse parâmetro é o
**token do destino Via Kondado** — é ele que vai na env var `KONDADO_TOKEN` do Render.
**NÃO confundir** com a página *Configurações → Tokens* ("Tokens de acesso"), que é para
API/webhooks (criar/editar conectores, disparar integrações) e **não** afeta este MCP.
A própria doc avisa: "Os tokens de acesso são diferentes dos tokens do Via Kondado".

### Passo a passo (menu exato)
1. Login em `https://app.kondado.com.br`.
2. Abrir o **destino Via Kondado** (menu Destinos → selecionar a instância).
3. Clicar no ícone de **3 barras horizontais** (☰) do destino → **"Alterar token"**.
   (A opção **"Ver token"** no mesmo menu apenas exibe o atual, sem rotacionar.)
4. A plataforma gera um **token novo** e **invalida o anterior** imediatamente. Copiar o novo
   e guardar em local seguro (gerenciador de segredos) — **nunca colar em chat/log**.
5. Render → serviço `mcp-locanorte` → **Environment** → editar **`KONDADO_TOKEN`** → colar o novo
   valor → **Save Changes** (Auto-Deploy On Commit/Save dispara o redeploy).
6. Aguardar o deploy e **validar**:
   - `status_locanorte` → `kondado_configurado: true`.
   - `resumo_locanorte` → `financeiro.status: "ok"` e os três sub-blocos `"ok"`.

### Checklist
- [ ] Token novo gerado em "Alterar token" (não na página de Tokens de acesso da API).
- [ ] `KONDADO_TOKEN` atualizado no Render e **Save** feito.
- [ ] Redeploy concluído (logs sem erro).
- [ ] `status_locanorte` e `resumo_locanorte` validados.
- [ ] Token antigo descartado do gerenciador de segredos.

### Pontos de atenção
- O **mesmo** token do Via Kondado serve como **Bearer** no MCP nativo da Kondado
  (`https://mcp.kondado.io/mcp`). Se um dia esse caminho for usado, lembrar de atualizar lá também.
- Boa prática de governança da própria Kondado: login com **2FA** e **domínios restritos**,
  já que o token pode ser obtido por quem tiver acesso à conta.

### Links oficiais (PT-BR)
- Ver/obter token: `https://kondado.com.br/wiki/a/via-kondado#anchor-get-access-token`
- Alterar (rotacionar) token: `https://kondado.com.br/wiki/a/via-kondado#anchor-change-token`
- Recomendações de segurança: `https://kondado.com.br/wiki/a/via-kondado#anchor-security-recomendations`
