# HANDOFF — Construção do MCP Locanorte

Documento de transferência de contexto. Resume tudo o que foi construído e decidido na sessão
de criação/deploy do servidor MCP da Locanorte, para que o trabalho continue no Claude Code sem
perder histórico.

---

## 1. Objetivo

Colocar no ar um **servidor MCP remoto** próprio da Locanorte e conectá-lo ao Claude (claude.ai)
como **conector personalizado**, permitindo que o Claude consulte dados/ações da empresa via
linguagem natural. Esta sessão entregou a **infraestrutura completa funcionando**; as tools ainda
são placeholders ("esqueleto").

---

## 2. Arquitetura (estado atual, funcionando)

```
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
Tools: status_locanorte, resumo_locanorte
```

Relação com o **Kondado** (decisão do usuário): o Kondado continua sendo usado como camada de
**ETL/integração** (fontes → data warehouse → Power BI). O MCP é a camada de **acesso via IA**
(consulta sob demanda pelo Claude). As duas camadas convivem; o Kondado só será substituído mais
adiante, quando houver condições de internalizar a integração.

---

## 3. server.py atual (versão no ar — commit 8e4ef99)

```python
import os
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(
    "MCP Locanorte HTTP",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8000)),
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)

@mcp.tool()
def status_locanorte() -> str:
    return "MCP Locanorte ativo via HTTP."

@mcp.tool()
def resumo_locanorte() -> str:
    return "Locanorte Caçambas e Resíduos Ltda."

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

`requirements.txt` contém ao menos: `fastapi`, `uvicorn`, `mcp` (o pacote `mcp` já traz
`starlette`/`uvicorn`). Python detectado no Render: 3.14.

---

## 4. Configuração do Render

| Item | Valor |
|------|-------|
| Tipo | Web Service |
| Plano | Standard (always-on, sem cold start) |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python server.py` |
| Auto-Deploy | On Commit (push na `main`) |
| Region/Subdomínio | `mcp-locanorte.onrender.com` (Render Subdomain habilitado) |

Nota de custo: Standard é mais caro que o necessário para este servidor leve. **Starter ($7/mês)**
também é always-on e é suficiente — avaliar downgrade em Settings → Instance Type. Se ficar muito
tempo sem mexer, considerar suspender o serviço para não gerar custo.

---

## 5. Problemas resolvidos nesta sessão (para NÃO repetir)

1. **"Build Command" não existe no GitHub.** Ele vive na plataforma de deploy (Render). GitHub só
   versiona código.

2. **Deploy "Timed Out" / serviço não subia.** Causa: o app subia em `http://127.0.0.1:8000`
   (loopback + porta fixa). O Render não alcança `127.0.0.1` e exige a porta de `$PORT`.
   Correção: bind em `0.0.0.0` e `port=int(os.environ["PORT"])`.

3. **Transporte errado (SSE) e path errado.** A primeira versão usava `app.mount("/mcp", mcp.sse_app())`,
   cujo endpoint real fica em `/mcp/sse` (não em `/mcp`). Além disso, SSE está deprecated no conector
   do Claude. Correção: migrar para `mcp.run(transport="streamable-http")`, cujo endpoint é `/mcp`.

4. **"Invalid Host header" no `/mcp`.** O SDK do MCP ativa proteção anti-DNS-rebinding automaticamente
   quando o `host` na construção é `127.0.0.1`, travando os hosts permitidos em localhost. Definir
   `mcp.settings.host = "0.0.0.0"` DEPOIS da construção não corrige (é tarde demais). Correção:
   passar `host="0.0.0.0"` e `transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)`
   direto no construtor do `FastMCP`.

**Sinal de sucesso do endpoint:** abrir `https://mcp-locanorte.onrender.com/mcp` no navegador deve
retornar JSON-RPC `{"error":{"code":-32600,"message":"Not Acceptable: Client must accept text/event-stream"}}`.
Isso é esperado (o navegador não envia o header `Accept: text/event-stream`; o Claude envia).

---

## 6. Conexão com o Claude (conector)

- Claude → **Settings → Connectors → Add custom connector**
- Nome: `MCP Locanorte` · URL: `https://mcp-locanorte.onrender.com/mcp` · **sem token** (authless)
- Observação: o Claude bloqueia URL duplicada ("A server with this URL already exists"). Se já existe
  um conector antigo com erro (de tentativas anteriores), remover o antigo e recadastrar.

---

## 7. Roadmap (próximos passos)

1. **Primeira tool útil** — provável: consulta à **API do Omie** (faturamento do mês, contas a
   receber, status de pedido). Definir endpoint do Omie, autenticação (app key/secret), parâmetros
   tipados e tratamento de erro.
2. **Mais tools operacionais** — caçambas alocadas, status de coletas, clientes (fonte a definir:
   API, banco PostgreSQL no Render, ou planilha).
3. **Governança / segurança** — religar `enable_dns_rebinding_protection=True` com allowlist
   (`allowed_hosts=["mcp-locanorte.onrender.com", "mcp-locanorte.onrender.com:*"]`,
   `allowed_origins=["https://mcp-locanorte.onrender.com"]`) e adicionar autenticação por token.
4. **Custo** — avaliar downgrade Standard → Starter.
5. **Substituição futura do Kondado** — quando houver condições, internalizar o ETL
   (opções: Microsoft Fabric/Dataflows, Airbyte, n8n/Make, ou Python agendado).

---

## 8. Como continuar no Claude Code

1. Clonar/abrir o repositório `mcp-locanorte` localmente.
2. Colocar `CLAUDE.md` e `HANDOFF.md` na raiz do projeto (este arquivo).
3. Rodar `claude` na pasta do projeto — o `CLAUDE.md` (que importa este `HANDOFF.md`) é lido
   automaticamente.
4. Pedir, por exemplo: "crie uma tool que consulta o faturamento do mês no Omie e retorna o total".
