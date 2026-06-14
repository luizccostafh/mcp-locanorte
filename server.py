from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
import uvicorn

mcp = FastMCP("MCP Locanorte HTTP")
app = FastAPI()

@mcp.tool()
def status_locanorte() -> str:
    return "MCP Locanorte ativo via HTTP."

@mcp.tool()
def resumo_locanorte() -> str:
    return "Locanorte Caçambas e Resíduos Ltda."

# 🔴 ESSA LINHA É A CHAVE
app.mount("/", mcp.sse_app())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)