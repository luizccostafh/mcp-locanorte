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