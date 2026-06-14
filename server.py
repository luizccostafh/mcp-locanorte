import os
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("MCP Locanorte HTTP")

@mcp.tool()
def status_locanorte() -> str:
    return "MCP Locanorte ativo via HTTP."

@mcp.tool()
def resumo_locanorte() -> str:
    return "Locanorte Caçambas e Resíduos Ltda."

if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="streamable-http")