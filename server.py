"""
============================================================================
 MCP LOCANORTE — Servidor Model Context Protocol (Streamable HTTP)
 Razão social: Locanorte Caçambas e Resíduos Ltda.
 CNPJ: 07.489.900/0001-93  |  Sede: Montes Claros/MG  |  Fundação: 2005
----------------------------------------------------------------------------
 SDK: oficial `mcp` (mcp.server.fastmcp).
 Tools:
   - status_locanorte   -> health-check estruturado (JSON)
   - resumo_locanorte   -> resumo gerencial (JSON): cadastro + financeiro vivo
 Arquitetura: Omie (fonte) -> Kondado (ETL) -> [este MCP] -> Power BI / IA
 Princípio: DEGRADAÇÃO GRACIOSA EM CAMADAS (cada sub-bloco protegido isolado).
----------------------------------------------------------------------------
 v1.4.0 — top_categorias agora traz a DESCRIÇÃO da categoria.
   (fix 2026-06-16) _fetch_csv usa follow_redirects=True: o hub Kondado passou a
   responder 302 -> S3; sem seguir o redirect, todo o financeiro ficava indisponível.
   De-para codigo_categoria -> categoria_descricao construído a partir da
   tabela_dre_omie, buscada UMA ÚNICA VEZ e reaproveitada no faturamento e
   nas duas listas de categorias (menos chamadas ao Kondado).
 v1.3.0 — schema confirmado via .pbix (valor_documento, status_titulo,
   categorias_valor; DRE com valor já assinado e Receita Líquida Operacional).
============================================================================
"""
import os
import csv
import io
import logging
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# ----------------------------------------------------------------------------
# 1) INFRAESTRUTURA
# ----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mcp_locanorte")

TZ = ZoneInfo("America/Sao_Paulo")
CONTRATO_VERSAO = "1.4.0"

mcp = FastMCP(
    "MCP Locanorte HTTP",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8000)),
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)

# ----------------------------------------------------------------------------
# 2) CONFIGURAÇÃO VIA VARIÁVEIS DE AMBIENTE (Render -> Environment)
# ----------------------------------------------------------------------------
KONDADO_TOKEN    = os.environ.get("KONDADO_TOKEN", "")
KONDADO_BASE_URL = os.environ.get("KONDADO_BASE_URL", "https://hub.kondado.io/data")
KONDADO_TIMEOUT  = float(os.environ.get("KONDADO_TIMEOUT", "20"))

# --- Tabelas (nomes confirmados no modelo) ---
TBL_PAGAR       = os.environ.get("KONDADO_TBL_PAGAR",       "omie_lancamentos_contas_pagar")
TBL_PAGAR_CAT   = os.environ.get("KONDADO_TBL_PAGAR_CAT",   "omie_lancamentos_contas_pagar_categorias")
TBL_RECEBER     = os.environ.get("KONDADO_TBL_RECEBER",     "omie_lancamentos_contas_receber")
TBL_RECEBER_CAT = os.environ.get("KONDADO_TBL_RECEBER_CAT", "omie_lancamentos_contas_receber_categorias")
TBL_DRE         = os.environ.get("KONDADO_TBL_DRE",         "tabela_dre_omie")

# --- Colunas de títulos (confirmadas) ---
COL_VALOR_DOC = os.environ.get("KONDADO_COL_VALOR_DOC", "valor_documento")
COL_STATUS    = os.environ.get("KONDADO_COL_STATUS",    "status_titulo")
STATUS_ABERTO    = os.environ.get("KONDADO_STATUS_ABERTO",    "A VENCER,ATRASADO,VENCE HOJE")
STATUS_CANCELADO = os.environ.get("KONDADO_STATUS_CANCELADO", "CANCELADO")
COL_CAT_VALOR  = os.environ.get("KONDADO_COL_CAT_VALOR",  "categorias_valor")
COL_CAT_CODIGO = os.environ.get("KONDADO_COL_CAT_CODIGO", "categorias_codigo_categoria")

# --- Colunas do DRE (confirmadas) ---
COL_DRE_VALOR    = os.environ.get("KONDADO_COL_DRE_VALOR",    "valor")   # já vem COM SINAL
COL_DRE_DATA     = os.environ.get("KONDADO_COL_DRE_DATA",     "data_emissao")
COL_DRE_COD_CAT  = os.environ.get("KONDADO_COL_DRE_COD_CAT",  "codigo_categoria")
COL_DRE_CAT_DESC = os.environ.get("KONDADO_COL_DRE_CAT_DESC", "categoria_descricao")
DRE_NIVEIS = os.environ.get(
    "KONDADO_DRE_NIVEIS",
    "descricaodre_n1,descricaodre_n2,descricaodre_n3,descricaodre_n4,descricaodre_n5,descricaodre_n6",
)
DRE_RECEITA_MARCADOR = os.environ.get("KONDADO_DRE_RECEITA_MARCADOR", "Receita")
DRE_COMPETENCIA = os.environ.get("KONDADO_DRE_COMPETENCIA", "")

# ----------------------------------------------------------------------------
# 3) BASE CADASTRAL (fallback sempre disponível, independe do Kondado)
# ----------------------------------------------------------------------------
CADASTRO: dict[str, Any] = {
    "razao_social": "Locanorte Caçambas e Resíduos Ltda.",
    "nome_fantasia": "Caçamba e Cia",
    "cnpj": "07.489.900/0001-93",
    "fundacao": 2005,
    "sede": "Montes Claros/MG",
    "centros_de_custo": 16,          # 15 caminhões + ALADIM
    "servicos_ativos": 7,
    "cliente_ancora": "Novo Nordisk",
    "bancos": ["Sicoob", "Banco do Brasil", "BNB", "Caixa"],
}

# ----------------------------------------------------------------------------
# 4) HELPERS DE BAIXO NÍVEL
# ----------------------------------------------------------------------------
def _fetch_csv(tabela: str) -> list[dict[str, str]]:
    """Busca uma tabela do hub Kondado em CSV e devolve lista de dicts."""
    if not KONDADO_TOKEN:
        raise RuntimeError("KONDADO_TOKEN não configurado nas variáveis de ambiente.")
    url = f"{KONDADO_BASE_URL}/{tabela}"
    params = {"token": KONDADO_TOKEN, "format": "csv"}
    # follow_redirects=True: o hub do Kondado responde 302 -> arquivo no S3
    # (hub-kondado.s3.amazonaws.com/.../data.csv). Sem isso, o 302 estoura
    # em raise_for_status() e todo o financeiro cai como 'indisponivel'.
    with httpx.Client(timeout=KONDADO_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        texto = resp.text
    return list(csv.DictReader(io.StringIO(texto)))


def _to_float(valor: str | None) -> float:
    """Converte string monetária (BR/EN) para float (preserva sinal), tolerante a lixo."""
    if valor is None or valor == "":
        return 0.0
    v = str(valor).strip().replace("R$", "").replace(" ", "")
    neg = v.startswith("-")
    v = v.lstrip("+-")
    if "," in v and "." in v:          # 1.234,56 -> 1234.56
        v = v.replace(".", "").replace(",", ".")
    elif "," in v:                      # 1234,56 -> 1234.56
        v = v.replace(",", ".")
    try:
        f = float(v)
    except ValueError:
        return 0.0
    return -f if neg else f


def _norm_cod(x: Any) -> str:
    """Normaliza código de categoria p/ casar de-para (remove '.0' de float)."""
    s = str(x or "").strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def _competencia_de(data_str: str | None) -> str:
    """Extrai 'YYYY-MM' de uma data em vários formatos. '' se não reconhecer."""
    s = str(data_str or "").strip()
    if len(s) >= 7 and s[:4].isdigit() and s[4] == "-":   # 2026-06-01 / ISO
        return s[:7]
    if "/" in s:                                           # 01/06/2026 (BR)
        partes = s.split("/")
        if len(partes) == 3:
            d, mth, a = partes
            if len(a) == 4 and a.isdigit() and mth.strip().isdigit():
                return f"{a}-{int(mth):02d}"
    return ""


def _set_env(nome_csv: str) -> set[str]:
    """Lê um env CSV e devolve um set em MAIÚSCULAS (p/ comparar status)."""
    return {x.strip().upper() for x in nome_csv.split(",") if x.strip()}


def _safe(label: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Executa um sub-bloco; em falha devolve status='indisponivel' sem propagar."""
    try:
        return fn()
    except Exception as exc:  # isola a falha de cada sub-bloco
        logger.warning("Falha em '%s': %s", label, exc)
        return {"status": "indisponivel", "erro": str(exc)}


# ----------------------------------------------------------------------------
# 4.1) DE-PARA codigo_categoria -> categoria_descricao (a partir do DRE)
# ----------------------------------------------------------------------------
def _mapa_categorias(dre_rows: list[dict[str, str]] | None) -> dict[str, str]:
    """Constrói {codigo_categoria: categoria_descricao} a partir das linhas do DRE."""
    mapa: dict[str, str] = {}
    for r in dre_rows or []:
        cod = _norm_cod(r.get(COL_DRE_COD_CAT))
        desc = str(r.get(COL_DRE_CAT_DESC, "") or "").strip()
        if cod and desc and cod not in mapa:
            mapa[cod] = desc
    return mapa


# ----------------------------------------------------------------------------
# 4.2) SUB-BLOCOS DE NEGÓCIO
# ----------------------------------------------------------------------------
def _resumir_titulos(tabela_main: str, tabela_cat: str, cat_map: dict[str, str]) -> dict[str, Any]:
    """
    Títulos a pagar/receber:
      - valor_total       = soma de valor_documento (exclui CANCELADO)
      - valor_em_aberto   = soma de valor_documento com status em STATUS_ABERTO
      - top_categorias    = via tabela-filha *_categorias (categorias_valor),
                            já com a DESCRIÇÃO resolvida pelo de-para do DRE.
    """
    abertos = _set_env(STATUS_ABERTO)
    cancelados = _set_env(STATUS_CANCELADO)

    rows = _fetch_csv(tabela_main)
    valor_total = valor_aberto = 0.0
    qtd_total = qtd_aberto = 0
    for r in rows:
        st = str(r.get(COL_STATUS, "") or "").strip().upper()
        if st in cancelados:
            continue
        v = _to_float(r.get(COL_VALOR_DOC))
        valor_total += v
        qtd_total += 1
        if st in abertos:
            valor_aberto += v
            qtd_aberto += 1

    # Categorias na tabela-filha (um título pode ratear em várias categorias)
    por_categoria: dict[str, float] = {}
    for c in _fetch_csv(tabela_cat):
        cod = _norm_cod(c.get(COL_CAT_CODIGO)) or "sem_categoria"
        por_categoria[cod] = por_categoria.get(cod, 0.0) + _to_float(c.get(COL_CAT_VALOR))
    top5 = sorted(por_categoria.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "status": "ok",
        "qtd_titulos": qtd_total,
        "valor_total": round(valor_total, 2),
        "qtd_em_aberto": qtd_aberto,
        "valor_em_aberto": round(valor_aberto, 2),
        "top_categorias": [
            {
                "codigo": cod,
                "descricao": cat_map.get(cod) or "(sem descrição no DRE)",
                "valor": round(v, 2),
            }
            for cod, v in top5
        ],
    }


def _faturamento_mes(dre_rows: list[dict[str, str]]) -> dict[str, Any]:
    """
    Receita do mês corrente a partir das linhas do DRE (já buscadas).
    `valor` vem COM SINAL: positivo = receita bruta; negativo = deduções.
      receita_liquida = soma total (= Receita Líquida Operacional do DRE)
    """
    alvo = DRE_COMPETENCIA or datetime.now(TZ).strftime("%Y-%m")
    niveis = [c.strip() for c in DRE_NIVEIS.split(",") if c.strip()]
    marcador = DRE_RECEITA_MARCADOR.lower()

    bruta = deducoes = 0.0
    linhas = 0
    for r in dre_rows:
        if _competencia_de(r.get(COL_DRE_DATA)) != alvo:
            continue
        caminho = " ".join(str(r.get(n, "") or "") for n in niveis).lower()
        if marcador and marcador not in caminho:
            continue
        v = _to_float(r.get(COL_DRE_VALOR))
        if v >= 0:
            bruta += v
        else:
            deducoes += v
        linhas += 1

    return {
        "status": "ok",
        "competencia": alvo,
        "receita_bruta": round(bruta, 2),
        "deducoes": round(deducoes, 2),
        "receita_liquida": round(bruta + deducoes, 2),
        "linhas_consideradas": linhas,
        "criterio": f"descricaodre contém '{DRE_RECEITA_MARCADOR}' (Receita Líquida Operacional)",
    }


def _bloco_financeiro() -> dict[str, Any]:
    """
    Sem token -> indisponível inteiro. Com token:
      1) busca tabela_dre_omie UMA vez (alimenta faturamento + de-para);
      2) cada sub-bloco é protegido isoladamente.
    """
    if not KONDADO_TOKEN:
        return {
            "status": "indisponivel",
            "fonte": KONDADO_BASE_URL,
            "erro": "KONDADO_TOKEN não configurado nas variáveis de ambiente.",
            "observacao": "Resumo entregue apenas com base cadastral. "
                          "Verifique token/instabilidade do conector Kondado.",
        }

    # DRE buscado uma única vez; se falhar, faturamento cai mas títulos seguem
    # (apenas sem descrição de categoria).
    try:
        dre_rows = _fetch_csv(TBL_DRE)
    except Exception as exc:
        logger.warning("Falha ao buscar DRE: %s", exc)
        dre_rows = None
    cat_map = _mapa_categorias(dre_rows)

    if dre_rows is None:
        faturamento = {"status": "indisponivel", "erro": "Falha ao buscar tabela_dre_omie."}
    else:
        faturamento = _safe("faturamento_mes", lambda: _faturamento_mes(dre_rows))

    return {
        "status": "ok",
        "fonte": KONDADO_BASE_URL,
        "faturamento_mes":  faturamento,
        "contas_a_pagar":   _safe("contas_a_pagar",   lambda: _resumir_titulos(TBL_PAGAR, TBL_PAGAR_CAT, cat_map)),
        "contas_a_receber": _safe("contas_a_receber", lambda: _resumir_titulos(TBL_RECEBER, TBL_RECEBER_CAT, cat_map)),
    }


# ----------------------------------------------------------------------------
# 5) TOOLS
# ----------------------------------------------------------------------------
@mcp.tool()
def status_locanorte() -> dict:
    """Health-check estruturado do servidor MCP Locanorte."""
    return {
        "servico": "MCP Locanorte",
        "status": "ativo",
        "transporte": "streamable-http",
        "contrato_versao": CONTRATO_VERSAO,
        "kondado_configurado": bool(KONDADO_TOKEN),
        "data_referencia": datetime.now(TZ).isoformat(),
    }


@mcp.tool()
def resumo_locanorte() -> dict:
    """Resumo gerencial da Locanorte (JSON): base cadastral + financeiro ao vivo."""
    return {
        "contrato_versao": CONTRATO_VERSAO,
        "data_referencia": datetime.now(TZ).isoformat(),
        "empresa": CADASTRO,
        "financeiro": _bloco_financeiro(),
    }


# ----------------------------------------------------------------------------
# 6) BOOTSTRAP
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
