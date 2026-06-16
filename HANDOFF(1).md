# HANDOFF — Construção do MCP Locanorte

Documento de transferência de contexto. Resume o que foi construído e decidido na criação/deploy
do servidor MCP da Locanorte, para que o trabalho continue no Claude Code sem perder histórico.

> **Atualizado em 2026-06-16** para refletir o código realmente no ar (`server.py` v1.4.0).
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
Tools: status_locanorte, resumo_locanorte (dados reais)
```

Relação com o **Kondado** (decisão do usuário): o Kondado continua sendo a camada de
**ETL/integração** (Omie → data warehouse → Power BI **e** este MCP). O MCP é a camada de
**acesso via IA**. As duas convivem; o Kondado só será substituído mais adiante.

---

## 3. server.py atual (v1.4.0 — no ar)

O arquivo já NÃO é placeholder. Estrutura real (ver `server.py` para o código completo):

- Cria `FastMCP("MCP Locanorte HTTP", host="0.0.0.0", port=$PORT, transport_security=...)`.
- Lê configuração de tabelas/colunas do Kondado via variáveis de ambiente (ver CLAUDE.md).
- `_fetch_csv(tabela)` busca o hub Kondado em CSV (httpx) usando `KONDADO_TOKEN`.
- Helpers: `_to_float` (BR/EN com sinal), `_norm_cod`, `_competencia_de`, `_safe` (degradação
  graciosa por sub-bloco), `_mapa_categorias` (de-para codigo→descrição via DRE).
- Sub-blocos de negócio: `_resumir_titulos` (pagar/receber + top categorias),
  `_faturamento_mes` (DRE, valor já com sinal → receita líquida), `_bloco_financeiro`.
- Tools expostas:
  - `status_locanorte()` → dict (health-check estruturado).
  - `resumo_locanorte()` → dict (cadastro + financeiro ao vivo).
- Bootstrap: `if __name__ == "__main__": mcp.run(transport="streamable-http")`.

**Princípio de design:** degradação graciosa em camadas — cada sub-bloco é protegido isolado;
a falha de um (ex.: DRE) não derruba os outros (ex.: títulos seguem, só sem descrição de categoria).

`requirements.txt`: `mcp` (pin de versão para garantir `mcp.server.transport_security`) + `httpx`.
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

**Sinal de sucesso do endpoint:** abrir `/mcp` no navegador retorna JSON-RPC
`{"error":{"code":-32600,"message":"Not Acceptable: Client must accept text/event-stream"}}`.

---

## 6. Verificação ao vivo (2026-06-16)

Teste feito chamando as tools pelo conector:
- `status_locanorte` → `status: "ativo"`, `transporte: "streamable-http"`, `contrato_versao: "1.4.0"`,
  **`kondado_configurado: false`**, resposta instantânea (sem cold start, confirma Standard).
- `resumo_locanorte` → cadastro OK; **`financeiro.status = "indisponivel"`** porque
  `KONDADO_TOKEN` não está nas env vars do Render.

➡️ **Ação pendente nº1:** setar `KONDADO_TOKEN` no Render → Environment, e redeployar.

---

## 7. Conexão com o Claude (conector)

- Claude → **Settings → Connectors → Add custom connector**
- Nome: `MCP Locanorte` · URL: `https://mcp-locanorte.onrender.com/mcp` · **sem token** (authless)
- O Claude bloqueia URL duplicada ("A server with this URL already exists"). Se já existe um
  conector antigo com erro, remover o antigo e recadastrar.

---

## 8. Roadmap (próximos passos)

1. **Setar `KONDADO_TOKEN` no Render** — destrava o financeiro (bloqueio atual).
2. **Mais tools operacionais** — caçambas alocadas, status de coletas, clientes.
3. **Parâmetros tipados** — ex.: competência/mês como argumento da tool.
4. **Governança / segurança** — religar `enable_dns_rebinding_protection=True` com allowlist
   (`allowed_hosts=["mcp-locanorte.onrender.com", "mcp-locanorte.onrender.com:*"]`,
   `allowed_origins=["https://mcp-locanorte.onrender.com"]`) e auth por token.
5. **Custo** — avaliar downgrade Standard → Starter.
6. **Substituição futura do Kondado** — internalizar o ETL quando houver condições.

---

## 9. Como continuar no Claude Code

1. Abrir o repositório `mcp-locanorte`.
2. `CLAUDE.md` e `HANDOFF.md` já estão na raiz — o `CLAUDE.md` (que importa este `HANDOFF.md`)
   é lido automaticamente.
3. Pedir, por exemplo: "crie uma tool que lista as caçambas alocadas por cliente".
