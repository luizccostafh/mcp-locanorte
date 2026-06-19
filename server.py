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
                           [param opcional: competencia='AAAA-MM' p/ o faturamento]
   - faturamento        -> receita de UM mês específico (DRE, com fallback NFS-e)
   - fluxo_caixa        -> caixa hoje + vencimentos por janela + projeção 7/15/30d
   - dre_resultado      -> Resultado Operacional separando REALIZADO x PROJETADO
   - top_clientes       -> maiores clientes por contas a receber (total + em aberto)
   - coletas            -> operação: Ordens de Serviço (locações/coletas de caçamba)
                           por etapa, centro de custo, cliente, tipo de serviço e mês
 Arquitetura: Omie (fonte) -> Kondado (ETL) -> [este MCP] -> Power BI / IA
 Princípio: DEGRADAÇÃO GRACIOSA EM CAMADAS (cada sub-bloco protegido isolado).
----------------------------------------------------------------------------
 v1.11.1 — FIX no caixa: _caixa_hoje ignora linhas de saldo com data FUTURA.
   A tabela de saldo é série diária com dias projetados; pegar o maior data_saldo
   sem teto trazia data_saldo_base no futuro e saldo "atual" = projeção. Agora só
   considera data_saldo <= hoje (expõe `linhas_futuras_ignoradas` p/ transparência).
 v1.11.0 — PRIMEIRA TOOL OPERACIONAL: coletas. Lê as Ordens de Serviço do Omie
   (`omie_servicos_ordens_de_servico` + filha `_servicosprestados`) — cada OS é uma
   locação/coleta de caçamba. Agrega total/valor (exclui CANCELADA), faturadas x
   não faturadas, e quebras por etapa, centro de custo (qual caminhão), cliente
   (NOME via `omie_clientes`, reaproveitando _mapa_clientes), tipo de serviço
   (cdescserv + soma de nqtde) e mês. competencia 'AAAA-MM' filtra pela data de
   previsão da OS (fallback: data de inclusão). Colunas AUTO-DETECTADAS; degradação
   graciosa por bloco. OBS: reflete o ÚLTIMO sync do Kondado (a OS não tem
   "tempo real"); confira a cadência do pipeline.
 v1.10.0 — top_clientes resolve o NOME do cliente via `omie_clientes`
   (join codigo_cliente_fornecedor -> razao_social/nome_fantasia; auto-detecção,
   cai para o código se não achar). dre_resultado ganha FALLBACK por TÍTULOS
   (contas a receber − contas a pagar por competência; realizado x projetado)
   quando a `tabela_dre_omie` não existe — rotulado como APROXIMAÇÃO (inclui
   não-operacionais como empréstimos/CAPEX; p/ o Resultado Operacional oficial,
   reconstrua a tabela_dre_omie).
 v1.9.0 — FALLBACKS quando a transformação `tabela_dre_omie` não existe no
   destino Kondado (caso comum logo após recriar o destino, antes de reconstruir
   o modelo "kubo" do DRE):
     (a) DE-PARA de categoria via `omie_categorias` (tabela de cadastro JÁ
         sincronizada). Antes, sem o DRE, as top_categorias saíam como
         "(sem descrição no DRE)". Agora, se o de-para do DRE vier vazio, o
         servidor monta codigo->descricao a partir de omie_categorias
         (colunas auto-detectadas). _mapa_categorias permanece a fonte primária.
     (b) FATURAMENTO via NFS-e (`omie_servicos_nfse`). Se o DRE faltar OU não
         tiver linhas para a competência, soma as notas de serviço do mês
         (exclui canceladas). O bloco indica fonte_faturamento p/ não confundir
         com a Receita Líquida do DRE. Colunas auto-detectadas (sem chutar).
   Tudo configurável por env (KONDADO_TBL_CATEGORIAS, KONDADO_TBL_NFSE, etc.)
   e com degradação graciosa: se nada bater, devolve 'indisponivel' com as
   colunas disponíveis (para configurar a env var) — nunca quebra o resto.
 v1.8.0 — nova tool top_clientes: ranking de clientes por contas a receber
   (valor_total acumulado + valor_em_aberto, com o MESMO _esta_em_aberto das
   demais tools). Coluna de cliente AUTO-DETECTADA (candidatos + env var).
 v1.7.0 — nova tool dre_resultado: Resultado Operacional do DRE (soma de `valor`,
   que já vem com sinal) separando REALIZADO de PROJETADO (derivado da data).
 v1.6.0 — PARÂMETROS TIPADOS. resumo_locanorte aceita competencia ('AAAA-MM');
   nova tool faturamento(competencia). Helper _valida_competencia.
 v1.5.0 — nova tool fluxo_caixa: omie_saldo_conta_corrente x títulos em aberto,
   janelas de vencimento e projeção. Helpers _parse_date e _esta_em_aberto.
 v1.4.0 — top_categorias com DESCRIÇÃO da categoria (de-para via DRE).
   (fix 2026-06-16) _fetch_csv usa follow_redirects=True (hub Kondado -> 302 S3).
 v1.3.0 — schema confirmado via .pbix (valor_documento, status_titulo,
   categorias_valor; DRE com valor já assinado e Receita Líquida Operacional).
============================================================================
"""
import os
import csv
import io
import logging
from datetime import datetime, date
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
CONTRATO_VERSAO = "1.11.1"

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
COL_VENCIMENTO = os.environ.get("KONDADO_COL_VENCIMENTO", "data_vencimento")  # usado por fluxo_caixa
STATUS_ABERTO    = os.environ.get("KONDADO_STATUS_ABERTO",    "A VENCER,ATRASADO,VENCE HOJE")
STATUS_CANCELADO = os.environ.get("KONDADO_STATUS_CANCELADO", "CANCELADO")
COL_CAT_VALOR  = os.environ.get("KONDADO_COL_CAT_VALOR",  "categorias_valor")
COL_CAT_CODIGO = os.environ.get("KONDADO_COL_CAT_CODIGO", "categorias_codigo_categoria")

# --- Cliente em contas a receber (top_clientes) — nome não confirmado: auto-detecta ---
COL_RECEBER_CLIENTE = os.environ.get("KONDADO_COL_RECEBER_CLIENTE", "nome_cliente")
CLIENTE_CANDIDATOS = [
    "nome_cliente", "cliente", "nome_razao_social", "razao_social",
    "nome_fantasia", "cliente_fornecedor", "nome_cliente_fornecedor",
    "codigo_cliente_fornecedor", "codigo_cliente", "nome",
]

# --- Colunas do DRE (confirmadas) ---
COL_DRE_VALOR    = os.environ.get("KONDADO_COL_DRE_VALOR",    "valor")   # já vem COM SINAL
COL_DRE_DATA     = os.environ.get("KONDADO_COL_DRE_DATA",     "data_emissao")
COL_DRE_COD_CAT  = os.environ.get("KONDADO_COL_DRE_COD_CAT",  "codigo_categoria")
COL_DRE_CAT_DESC = os.environ.get("KONDADO_COL_DRE_CAT_DESC", "categoria_descricao")
DRE_NIVEIS = os.environ.get(
    "KONDADO_DRE_NIVEIS",
    "descricaodre_n1,descricaodre_n2,descricaodre_n3,descricaodre_n4,descricaodre_n5,descricaodre_n6",
)
COL_DRE_N1 = os.environ.get("KONDADO_COL_DRE_N1", (DRE_NIVEIS.split(",")[0].strip() or "descricaodre_n1"))
DRE_RECEITA_MARCADOR = os.environ.get("KONDADO_DRE_RECEITA_MARCADOR", "Receita")
DRE_COMPETENCIA = os.environ.get("KONDADO_DRE_COMPETENCIA", "")

# --- Saldo de contas correntes (fluxo_caixa) — nomes reais confirmados no warehouse ---
TBL_SALDO       = os.environ.get("KONDADO_TBL_SALDO",       "omie_saldo_conta_corrente")
COL_SALDO_CONTA = os.environ.get("KONDADO_COL_SALDO_CONTA", "ncodcc")
COL_SALDO_DATA  = os.environ.get("KONDADO_COL_SALDO_DATA",  "data_saldo")
COL_SALDO_DESC  = os.environ.get("KONDADO_COL_SALDO_DESC",  "cdescricao")
COL_SALDO_ATUAL = os.environ.get("KONDADO_COL_SALDO_ATUAL", "nsaldoatual")
COL_SALDO_DISP  = os.environ.get("KONDADO_COL_SALDO_DISP",  "nsaldodisponivel")

# --- (v1.9.0) Cadastro de categorias: FALLBACK do de-para quando o DRE faltar ---
TBL_CATEGORIAS   = os.environ.get("KONDADO_TBL_CATEGORIAS",   "omie_categorias")
COL_CATEG_CODIGO = os.environ.get("KONDADO_COL_CATEG_CODIGO", "codigo_categoria")
COL_CATEG_DESC   = os.environ.get("KONDADO_COL_CATEG_DESC",   "descricao_categoria")
CATEG_COD_CAND  = ["codigo_categoria", "codigo", "cod_categoria", "ccodcateg", "codigo_cat", "cod"]
CATEG_DESC_CAND = ["descricao_categoria", "descricao", "cdescricao", "nome_categoria", "nome", "descricao_cat"]

# --- (v1.9.0) NFS-e: FALLBACK de faturamento quando a tabela_dre_omie não existe ---
TBL_NFSE        = os.environ.get("KONDADO_TBL_NFSE",        "omie_servicos_nfse")
COL_NFSE_VLIQ   = os.environ.get("KONDADO_COL_NFSE_VLIQ",   "valores_nvalorliquido")
COL_NFSE_VBRUTO = os.environ.get("KONDADO_COL_NFSE_VBRUTO", "valores_nvalortotalservicos")
COL_NFSE_DATA   = os.environ.get("KONDADO_COL_NFSE_DATA",   "emissao_cdataemissao")
COL_NFSE_STATUS = os.environ.get("KONDADO_COL_NFSE_STATUS", "cabecalho_cstatusnfse")
NFSE_STATUS_CANCELADO = os.environ.get("KONDADO_NFSE_STATUS_CANCELADO", "CANCELADA,CANCELADO")
NFSE_VLIQ_CAND   = ["valores_nvalorliquido", "valor_liquido", "nvalorliquido", "valorliquido"]
NFSE_VBRUTO_CAND = ["valores_nvalortotalservicos", "valor_total", "valor_servicos",
                    "nvalortotalservicos", "valorservicos", "valor_total_servicos"]
NFSE_DATA_CAND   = ["emissao_cdataemissao", "data_emissao", "dataemissao", "cdataemissao", "data"]
NFSE_STATUS_CAND = ["cabecalho_cstatusnfse", "status_nfse", "cstatusnfse", "status", "situacao"]

# --- (v1.10.0) Cadastro de clientes: resolve NOME do cliente em top_clientes ---
TBL_CLIENTES     = os.environ.get("KONDADO_TBL_CLIENTES",     "omie_clientes")
COL_CLIENTE_COD  = os.environ.get("KONDADO_COL_CLIENTE_COD",  "codigo_cliente_omie")
COL_CLIENTE_NOME = os.environ.get("KONDADO_COL_CLIENTE_NOME", "razao_social")
CLIENTE_COD_CAND  = ["codigo_cliente_omie", "codigo_cliente", "codigo",
                     "codigo_cliente_fornecedor", "codigo_fornecedor"]
CLIENTE_NOME_CAND = ["razao_social", "nome_fantasia", "nome", "razao", "nome_razao_social"]

# --- (v1.10.0) Data de competência dos títulos (fallback do dre_resultado) ---
COL_TITULO_DATA = os.environ.get("KONDADO_COL_TITULO_DATA", "data_emissao")

# --- (v1.11.0) Ordens de Serviço (tool coletas) — colunas confirmadas via schema ---
TBL_OS      = os.environ.get("KONDADO_TBL_OS",      "omie_servicos_ordens_de_servico")
TBL_OS_SERV = os.environ.get("KONDADO_TBL_OS_SERV", "omie_servicos_ordens_de_servico_servicosprestados")
COL_OS_ID      = os.environ.get("KONDADO_COL_OS_ID",      "cabecalho_ncodos")
COL_OS_CLIENTE = os.environ.get("KONDADO_COL_OS_CLIENTE", "cabecalho_ncodcli")
COL_OS_ETAPA   = os.environ.get("KONDADO_COL_OS_ETAPA",   "cabecalho_cetapa")
COL_OS_VALOR   = os.environ.get("KONDADO_COL_OS_VALOR",   "cabecalho_nvalortotal")
COL_OS_DT_PREV = os.environ.get("KONDADO_COL_OS_DT_PREV", "cabecalho_ddtprevisao")
COL_OS_DT_INC  = os.environ.get("KONDADO_COL_OS_DT_INC",  "infocadastro_ddtinc")
COL_OS_CANC    = os.environ.get("KONDADO_COL_OS_CANC",    "infocadastro_ccancelada")
COL_OS_FAT     = os.environ.get("KONDADO_COL_OS_FAT",     "infocadastro_cfaturada")
COL_OS_CC      = os.environ.get("KONDADO_COL_OS_CC",      "informacoesadicionais_ncodcc")
COL_OSSERV_ID   = os.environ.get("KONDADO_COL_OSSERV_ID",   "cabecalho_ncodos")
COL_OSSERV_DESC = os.environ.get("KONDADO_COL_OSSERV_DESC", "servicosprestados_cdescserv")
COL_OSSERV_QTD  = os.environ.get("KONDADO_COL_OSSERV_QTD",  "servicosprestados_nqtde")

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
    # follow_redirects=True: o hub do Kondado responde 302 -> arquivo no S3.
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


def _valida_competencia(s: str | None) -> str | None:
    """Valida/normaliza competência mensal. None/'' -> None; 'AAAA-MM'/'AAAA/MM' -> 'AAAA-MM'."""
    if s is None or str(s).strip() == "":
        return None
    txt = str(s).strip().replace("/", "-")
    partes = txt.split("-")
    if len(partes) == 2 and partes[0].isdigit() and partes[1].isdigit() and len(partes[0]) == 4:
        ano, mes = int(partes[0]), int(partes[1])
        if 1 <= mes <= 12:
            return f"{ano:04d}-{mes:02d}"
    raise ValueError(f"competência inválida: '{s}'. Use o formato AAAA-MM (ex.: 2026-03).")


def _set_env(nome_csv: str) -> set[str]:
    """Lê um env CSV e devolve um set em MAIÚSCULAS (p/ comparar status)."""
    return {x.strip().upper() for x in nome_csv.split(",") if x.strip()}


def _parse_date(valor: str | None) -> date | None:
    """Converte string de data (ISO 'YYYY-MM-DD' ou BR 'DD/MM/YYYY') para date. None se não reconhecer."""
    s = str(valor or "").strip()
    if not s:
        return None
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
        except ValueError:
            return None
    if "/" in s:
        partes = [p.strip() for p in s.split("/")]
        if len(partes) == 3 and len(partes[2]) == 4 and all(p.isdigit() for p in partes):
            d, m, a = partes
            try:
                return date(int(a), int(m), int(d))
            except ValueError:
                return None
    return None


def _agora() -> datetime:
    """'Agora' único no fuso America/Sao_Paulo, usado por todas as tools."""
    return datetime.now(TZ)


def _esta_em_aberto(row: dict[str, str]) -> bool:
    """Predicado ÚNICO de 'título em aberto' (status em STATUS_ABERTO e fora de STATUS_CANCELADO)."""
    st = str(row.get(COL_STATUS, "") or "").strip().upper()
    return st in _set_env(STATUS_ABERTO) and st not in _set_env(STATUS_CANCELADO)


def _detecta_coluna(header: list[str], candidatos: list[str]) -> str | None:
    """Acha no header (case-insensitive) a 1ª coluna candidata; devolve o nome REAL. None se nenhuma bater."""
    norm = {h.strip().lower(): h for h in header}
    for c in candidatos:
        real = norm.get(str(c).strip().lower())
        if real:
            return real
    return None


def _safe(label: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Executa um sub-bloco; em falha devolve status='indisponivel' sem propagar."""
    try:
        return fn()
    except Exception as exc:
        logger.warning("Falha em '%s': %s", label, exc)
        return {"status": "indisponivel", "erro": str(exc)}


def _safe_map(label: str, fn: Callable[[], dict[str, str]]) -> dict[str, str]:
    """Como _safe, mas para de-para (dict codigo->descricao); em falha devolve {}."""
    try:
        return fn() or {}
    except Exception as exc:
        logger.warning("Falha em '%s': %s", label, exc)
        return {}


# ----------------------------------------------------------------------------
# 4.1) DE-PARA codigo_categoria -> categoria_descricao
# ----------------------------------------------------------------------------
def _mapa_categorias(dre_rows: list[dict[str, str]] | None) -> dict[str, str]:
    """De-para {codigo_categoria: categoria_descricao} a partir das linhas do DRE."""
    mapa: dict[str, str] = {}
    for r in dre_rows or []:
        cod = _norm_cod(r.get(COL_DRE_COD_CAT))
        desc = str(r.get(COL_DRE_CAT_DESC, "") or "").strip()
        if cod and desc and cod not in mapa:
            mapa[cod] = desc
    return mapa


def _mapa_categorias_cadastro() -> dict[str, str]:
    """
    (v1.9.0) FALLBACK do de-para a partir de `omie_categorias` (cadastro), usado
    quando o DRE não está disponível/vazio. Colunas de código e descrição
    auto-detectadas (o nome exato pode variar entre destinos). {} se não der.
    """
    rows = _fetch_csv(TBL_CATEGORIAS)
    if not rows:
        return {}
    header = list(rows[0].keys())
    col_cod  = _detecta_coluna(header, [COL_CATEG_CODIGO, *CATEG_COD_CAND])
    col_desc = _detecta_coluna(header, [COL_CATEG_DESC, *CATEG_DESC_CAND])
    if not col_cod or not col_desc:
        return {}
    mapa: dict[str, str] = {}
    for r in rows:
        cod = _norm_cod(r.get(col_cod))
        desc = str(r.get(col_desc, "") or "").strip()
        if cod and desc and cod not in mapa:
            mapa[cod] = desc
    return mapa


def _mapa_clientes() -> dict[str, str]:
    """
    (v1.10.0) De-para {codigo_cliente: nome} a partir de `omie_clientes`, para o
    top_clientes mostrar NOME em vez do código. Colunas (chave/nome) auto-detectadas.
    {} se não der — nesse caso o ranking cai para o código.
    """
    rows = _fetch_csv(TBL_CLIENTES)
    if not rows:
        return {}
    header = list(rows[0].keys())
    col_cod  = _detecta_coluna(header, [COL_CLIENTE_COD, *CLIENTE_COD_CAND])
    col_nome = _detecta_coluna(header, [COL_CLIENTE_NOME, *CLIENTE_NOME_CAND])
    if not col_cod or not col_nome:
        return {}
    mapa: dict[str, str] = {}
    for r in rows:
        cod = _norm_cod(r.get(col_cod))
        nome = str(r.get(col_nome, "") or "").strip()
        if cod and nome and cod not in mapa:
            mapa[cod] = nome
    return mapa


# ----------------------------------------------------------------------------
# 4.2) SUB-BLOCOS DE NEGÓCIO
# ----------------------------------------------------------------------------
def _resumir_titulos(tabela_main: str, tabela_cat: str, cat_map: dict[str, str]) -> dict[str, Any]:
    """
    Títulos a pagar/receber: valor_total (exclui CANCELADO), valor_em_aberto e
    top_categorias (via tabela-filha *_categorias), com a DESCRIÇÃO resolvida
    pelo de-para (DRE como primário, omie_categorias como fallback).
    """
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
        if _esta_em_aberto(r):
            valor_aberto += v
            qtd_aberto += 1

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
                "descricao": cat_map.get(cod) or "(sem descrição)",
                "valor": round(v, 2),
            }
            for cod, v in top5
        ],
    }


def _faturamento_mes(dre_rows: list[dict[str, str]], competencia: str | None = None) -> dict[str, Any]:
    """Receita de um mês a partir do DRE (`valor` já vem COM SINAL)."""
    alvo = competencia or DRE_COMPETENCIA or _agora().strftime("%Y-%m")
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
        "fonte_faturamento": "DRE (tabela_dre_omie)",
        "competencia": alvo,
        "receita_bruta": round(bruta, 2),
        "deducoes": round(deducoes, 2),
        "receita_liquida": round(bruta + deducoes, 2),
        "linhas_consideradas": linhas,
        "criterio": f"descricaodre contém '{DRE_RECEITA_MARCADOR}' (Receita Líquida Operacional)",
    }


def _faturamento_nfse(competencia: str | None = None) -> dict[str, Any]:
    """
    (v1.9.0) FALLBACK de faturamento via NFS-e (`omie_servicos_nfse`). Soma as
    notas emitidas na competência (exclui canceladas). Colunas auto-detectadas;
    se faltar valor ou data, devolve 'indisponivel' com as colunas disponíveis.
    """
    alvo = competencia or DRE_COMPETENCIA or _agora().strftime("%Y-%m")
    rows = _fetch_csv(TBL_NFSE)
    if not rows:
        return {"status": "indisponivel", "competencia": alvo, "erro": f"{TBL_NFSE} sem linhas."}
    header = list(rows[0].keys())
    col_liq = _detecta_coluna(header, [COL_NFSE_VLIQ, *NFSE_VLIQ_CAND])
    col_bru = _detecta_coluna(header, [COL_NFSE_VBRUTO, *NFSE_VBRUTO_CAND])
    col_dat = _detecta_coluna(header, [COL_NFSE_DATA, *NFSE_DATA_CAND])
    col_st  = _detecta_coluna(header, [COL_NFSE_STATUS, *NFSE_STATUS_CAND])
    if not col_dat or not (col_liq or col_bru):
        return {
            "status": "indisponivel",
            "competencia": alvo,
            "erro": f"não foi possível identificar colunas de valor/data em {TBL_NFSE}.",
            "colunas_disponiveis": header,
            "dica": "configure KONDADO_COL_NFSE_VLIQ / KONDADO_COL_NFSE_DATA.",
        }

    cancel = _set_env(NFSE_STATUS_CANCELADO)
    bruta = liquida = 0.0
    linhas = 0
    for r in rows:
        if _competencia_de(r.get(col_dat)) != alvo:
            continue
        if col_st:
            st = str(r.get(col_st, "") or "").strip().upper()
            if st in cancel:
                continue
        if col_bru:
            bruta += _to_float(r.get(col_bru))
        if col_liq:
            liquida += _to_float(r.get(col_liq))
        linhas += 1

    if not col_liq:
        liquida = bruta
    if not col_bru:
        bruta = liquida

    return {
        "status": "ok",
        "fonte_faturamento": "NFS-e (omie_servicos_nfse)",
        "competencia": alvo,
        "receita_bruta": round(bruta, 2),
        "deducoes": round(liquida - bruta, 2),
        "receita_liquida": round(liquida, 2),
        "linhas_consideradas": linhas,
        "criterio": "soma das NFS-e de serviço emitidas no mês (exclui canceladas)",
    }


def _resolve_faturamento(dre_rows: list[dict[str, str]] | None,
                         competencia: str | None) -> dict[str, Any]:
    """(v1.9.0) Tenta o DRE; se faltar ou sem linhas na competência, cai p/ NFS-e."""
    if dre_rows is not None:
        fat = _safe("faturamento_mes", lambda: _faturamento_mes(dre_rows, competencia))
        if fat.get("status") == "ok" and fat.get("linhas_consideradas", 0) > 0:
            return fat
    alt = _safe("faturamento_nfse", lambda: _faturamento_nfse(competencia))
    if alt.get("status") == "ok" and alt.get("linhas_consideradas", 0) > 0:
        return alt
    if dre_rows is not None:
        return _safe("faturamento_mes", lambda: _faturamento_mes(dre_rows, competencia))
    return alt


def _dre_resultado(dre_rows: list[dict[str, str]], ano: int | None = None,
                   competencia: str | None = None) -> dict[str, Any]:
    """Resultado Operacional do DRE (soma de `valor`) separando REALIZADO de PROJETADO (derivado da data)."""
    ref = _agora().strftime("%Y-%m")
    ano_alvo = ano or _agora().year
    por_mes: dict[str, float] = {}
    por_n1: dict[str, float] = {}
    for r in dre_rows:
        comp = _competencia_de(r.get(COL_DRE_DATA))
        if not comp:
            continue
        if competencia:
            if comp != competencia:
                continue
        elif not comp.startswith(f"{ano_alvo:04d}-"):
            continue
        v = _to_float(r.get(COL_DRE_VALOR))
        por_mes[comp] = por_mes.get(comp, 0.0) + v
        if comp <= ref:
            n1 = str(r.get(COL_DRE_N1, "") or "").strip() or "(sem n1)"
            por_n1[n1] = por_n1.get(n1, 0.0) + v

    realizado = round(sum(v for c, v in por_mes.items() if c <= ref), 2)
    projetado = round(sum(v for c, v in por_mes.items() if c >  ref), 2)
    return {
        "status": "ok",
        "escopo": competencia if competencia else f"ano {ano_alvo}",
        "mes_corrente": ref,
        "criterio": "realizado = competências <= mês corrente; projetado = futuras (derivado da data)",
        "resultado_realizado": realizado,
        "resultado_projetado": projetado,
        "resultado_total": round(realizado + projetado, 2),
        "por_mes": [
            {"competencia": c, "resultado": round(v, 2),
             "tipo": "realizado" if c <= ref else "projetado"}
            for c, v in sorted(por_mes.items())
        ],
        "linhas_n1_realizado": [
            {"linha": k, "valor": round(v, 2)}
            for k, v in sorted(por_n1.items(), key=lambda x: abs(x[1]), reverse=True)
        ],
    }


def _dre_resultado_titulos(ano: int | None = None, competencia: str | None = None) -> dict[str, Any]:
    """
    (v1.10.0) FALLBACK do Resultado quando a tabela_dre_omie não existe: aproxima
    por TÍTULOS (contas a receber como +, contas a pagar como -), por competência
    (data_emissao), separando realizado (<= mês corrente) de projetado.

    ⚠️ APROXIMAÇÃO: usa títulos brutos (inclui não-operacionais — empréstimos,
    CAPEX, transferências). NÃO é o Resultado Operacional oficial do DRE.
    """
    ref = _agora().strftime("%Y-%m")
    ano_alvo = ano or _agora().year
    cancel = _set_env(STATUS_CANCELADO)
    por_mes: dict[str, float] = {}

    def _acumula(tabela: str, sinal: int) -> None:
        for r in _fetch_csv(tabela):
            st = str(r.get(COL_STATUS, "") or "").strip().upper()
            if st in cancel:
                continue
            comp = _competencia_de(r.get(COL_TITULO_DATA))
            if not comp:
                continue
            if competencia:
                if comp != competencia:
                    continue
            elif not comp.startswith(f"{ano_alvo:04d}-"):
                continue
            por_mes[comp] = por_mes.get(comp, 0.0) + sinal * _to_float(r.get(COL_VALOR_DOC))

    _acumula(TBL_RECEBER, +1)
    _acumula(TBL_PAGAR, -1)

    realizado = round(sum(v for c, v in por_mes.items() if c <= ref), 2)
    projetado = round(sum(v for c, v in por_mes.items() if c >  ref), 2)
    return {
        "status": "ok",
        "fonte_resultado": "aproximado (títulos: contas a receber − contas a pagar)",
        "aviso": "APROXIMAÇÃO por competência sobre títulos brutos (inclui não-operacionais "
                 "como empréstimos/CAPEX). Para o Resultado Operacional oficial, reconstrua a tabela_dre_omie.",
        "escopo": competencia if competencia else f"ano {ano_alvo}",
        "mes_corrente": ref,
        "resultado_realizado": realizado,
        "resultado_projetado": projetado,
        "resultado_total": round(realizado + projetado, 2),
        "por_mes": [
            {"competencia": c, "resultado": round(v, 2),
             "tipo": "realizado" if c <= ref else "projetado"}
            for c, v in sorted(por_mes.items())
        ],
    }


def _bloco_financeiro(competencia: str | None = None) -> dict[str, Any]:
    """
    Sem token -> indisponível. Com token: busca tabela_dre_omie uma vez; se faltar/
    vazia, usa omie_categorias (de-para) e NFS-e (faturamento). Cada sub-bloco isolado.
    """
    if not KONDADO_TOKEN:
        return {
            "status": "indisponivel",
            "fonte": KONDADO_BASE_URL,
            "erro": "KONDADO_TOKEN não configurado nas variáveis de ambiente.",
            "observacao": "Resumo entregue apenas com base cadastral. "
                          "Verifique token/instabilidade do conector Kondado.",
        }

    try:
        dre_rows = _fetch_csv(TBL_DRE)
    except Exception as exc:
        logger.warning("Falha ao buscar DRE: %s", exc)
        dre_rows = None

    cat_map = _mapa_categorias(dre_rows)
    fonte_categoria = "DRE"
    if not cat_map:
        cat_map = _safe_map("mapa_categorias_cadastro", _mapa_categorias_cadastro)
        fonte_categoria = "omie_categorias" if cat_map else "indisponivel"

    faturamento = _resolve_faturamento(dre_rows, competencia)

    return {
        "status": "ok",
        "fonte": KONDADO_BASE_URL,
        "fonte_categoria": fonte_categoria,
        "faturamento_mes":  faturamento,
        "contas_a_pagar":   _safe("contas_a_pagar",   lambda: _resumir_titulos(TBL_PAGAR, TBL_PAGAR_CAT, cat_map)),
        "contas_a_receber": _safe("contas_a_receber", lambda: _resumir_titulos(TBL_RECEBER, TBL_RECEBER_CAT, cat_map)),
    }


# ----------------------------------------------------------------------------
# 4.3) FLUXO DE CAIXA (caixa hoje + janelas de vencimento + projeção)
# ----------------------------------------------------------------------------
def _caixa_hoje() -> dict[str, Any]:
    """
    Posição de caixa = último saldo por conta corrente com data <= HOJE.
    A tabela de saldo é uma série DIÁRIA que inclui dias FUTUROS (saldos projetados);
    pegar o maior data_saldo sem teto fazia o data_saldo_base voltar no futuro e o
    'saldo atual' refletir projeção. Por isso ignoramos linhas com data futura.
    """
    hoje = _agora().date()
    ultimo: dict[str, dict[str, Any]] = {}
    futuras_ignoradas = 0
    for row in _fetch_csv(TBL_SALDO):
        cc = _norm_cod(row.get(COL_SALDO_CONTA))
        d = _parse_date(row.get(COL_SALDO_DATA))
        if not cc or d is None:
            continue
        if d > hoje:                       # saldo de dia futuro (projeção) -> ignora
            futuras_ignoradas += 1
            continue
        if cc not in ultimo or d > ultimo[cc]["_d"]:
            ultimo[cc] = {
                "_d": d,
                "conta": row.get(COL_SALDO_DESC) or cc,
                "atual": _to_float(row.get(COL_SALDO_ATUAL)),
                "disp":  _to_float(row.get(COL_SALDO_DISP)),
            }

    por_conta, tot_atual, tot_disp, base = [], 0.0, 0.0, None
    for v in ultimo.values():
        tot_atual += v["atual"]
        tot_disp  += v["disp"]
        base = v["_d"] if (base is None or v["_d"] > base) else base
        por_conta.append({
            "conta": v["conta"],
            "saldo_atual": round(v["atual"], 2),
            "saldo_disponivel": round(v["disp"], 2),
            "data_saldo": v["_d"].isoformat(),
        })
    por_conta.sort(key=lambda x: x["saldo_atual"], reverse=True)
    return {
        "status": "ok",
        "saldo_atual_total": round(tot_atual, 2),
        "saldo_disponivel_total": round(tot_disp, 2),
        "data_saldo_base": base.isoformat() if base else None,
        "linhas_futuras_ignoradas": futuras_ignoradas,
        "por_conta": por_conta,
    }


def _janelas_vencimento(tabela: str) -> dict[str, Any]:
    """Faixas de vencimento (vencido/7/15/30/30+) dos títulos em aberto. total_aberto casa com o resumo."""
    hoje = _agora().date()
    b = {"vencido": 0.0, "ate_7d": 0.0, "ate_15d": 0.0, "ate_30d": 0.0, "acima_30d": 0.0}
    total = 0.0
    for row in _fetch_csv(tabela):
        if not _esta_em_aberto(row):
            continue
        valor = _to_float(row.get(COL_VALOR_DOC))
        total += valor
        venc = _parse_date(row.get(COL_VENCIMENTO))
        dias = (venc - hoje).days if venc else 9999
        if   dias < 0:   b["vencido"]   += valor
        elif dias <= 7:  b["ate_7d"]    += valor
        elif dias <= 15: b["ate_15d"]   += valor
        elif dias <= 30: b["ate_30d"]   += valor
        else:            b["acima_30d"] += valor
    b = {k: round(v, 2) for k, v in b.items()}
    b["status"] = "ok"
    b["total_aberto"] = round(total, 2)
    return b


# ----------------------------------------------------------------------------
# 4.4) TOP CLIENTES (ranking por contas a receber)
# ----------------------------------------------------------------------------
def _top_clientes(limite: int) -> dict[str, Any]:
    """Ranking de clientes por contas a receber (total + em aberto). Coluna de cliente auto-detectada."""
    rows = _fetch_csv(TBL_RECEBER)
    if not rows:
        return {"status": "ok", "limite": limite, "qtd_clientes": 0, "clientes": [],
                "observacao": f"{TBL_RECEBER} sem linhas."}

    col = _detecta_coluna(list(rows[0].keys()), [COL_RECEBER_CLIENTE, *CLIENTE_CANDIDATOS])
    if not col:
        return {
            "status": "indisponivel",
            "erro": f"não foi possível identificar a coluna de cliente em {TBL_RECEBER}.",
            "colunas_disponiveis": list(rows[0].keys()),
            "dica": "defina a env var KONDADO_COL_RECEBER_CLIENTE com o nome correto.",
        }

    nome_map = _safe_map("mapa_clientes", _mapa_clientes)
    cancelados = _set_env(STATUS_CANCELADO)
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        st = str(r.get(COL_STATUS, "") or "").strip().upper()
        if st in cancelados:
            continue
        cod = _norm_cod(r.get(col)) or "(sem cliente)"
        v = _to_float(r.get(COL_VALOR_DOC))
        a = agg.setdefault(cod, {"valor_total": 0.0, "valor_em_aberto": 0.0, "qtd_titulos": 0})
        a["valor_total"] += v
        a["qtd_titulos"] += 1
        if _esta_em_aberto(r):
            a["valor_em_aberto"] += v

    ranking = sorted(agg.items(), key=lambda x: x[1]["valor_total"], reverse=True)[:limite]
    return {
        "status": "ok",
        "coluna_cliente": col,
        "fonte_nome": "omie_clientes" if nome_map else "indisponivel (exibindo código)",
        "limite": limite,
        "qtd_clientes": len(agg),
        "clientes": [
            {
                "cliente": nome_map.get(cod) or cod,
                "codigo": cod,
                "valor_total": round(a["valor_total"], 2),
                "valor_em_aberto": round(a["valor_em_aberto"], 2),
                "qtd_titulos": a["qtd_titulos"],
            }
            for cod, a in ranking
        ],
    }


# ----------------------------------------------------------------------------
# 4.5) COLETAS / ORDENS DE SERVIÇO (operação)
# ----------------------------------------------------------------------------
def _coletas(competencia: str | None, limite: int) -> dict[str, Any]:
    """
    (v1.11.0) Operação a partir das Ordens de Serviço (cada OS = locação/coleta de
    caçamba). Total e valor (exclui CANCELADA), faturadas x não faturadas, e quebras
    por etapa, centro de custo, cliente (NOME via omie_clientes) e mês; tipos de
    serviço (cdescserv) vêm da tabela-filha. competencia 'AAAA-MM' filtra pela data
    de previsão (fallback: inclusão). Colunas auto-detectadas; degradação graciosa.
    """
    rows = _fetch_csv(TBL_OS)
    if not rows:
        return {"status": "ok", "escopo": competencia or "todas", "total_os": 0,
                "observacao": f"{TBL_OS} sem linhas."}

    h = list(rows[0].keys())
    c_id    = _detecta_coluna(h, [COL_OS_ID, "cabecalho_ncodos", "ncodos"])
    c_cli   = _detecta_coluna(h, [COL_OS_CLIENTE, "cabecalho_ncodcli", "ncodcli"])
    c_etapa = _detecta_coluna(h, [COL_OS_ETAPA, "cabecalho_cetapa", "cetapa"])
    c_val   = _detecta_coluna(h, [COL_OS_VALOR, "cabecalho_nvalortotal", "nvalortotal"])
    c_prev  = _detecta_coluna(h, [COL_OS_DT_PREV, "cabecalho_ddtprevisao"])
    c_inc   = _detecta_coluna(h, [COL_OS_DT_INC, "infocadastro_ddtinc"])
    c_canc  = _detecta_coluna(h, [COL_OS_CANC, "infocadastro_ccancelada"])
    c_fat   = _detecta_coluna(h, [COL_OS_FAT, "infocadastro_cfaturada"])
    c_cc    = _detecta_coluna(h, [COL_OS_CC, "informacoesadicionais_ncodcc"])

    nome_map = _safe_map("mapa_clientes", _mapa_clientes)

    def _comp(r: dict[str, str]) -> str:
        return _competencia_de(r.get(c_prev) if c_prev else None) \
            or _competencia_de(r.get(c_inc) if c_inc else None)

    def _bump(d: dict[str, dict[str, Any]], k: str, v: float) -> None:
        a = d.setdefault(k, {"qtd": 0, "valor": 0.0})
        a["qtd"] += 1
        a["valor"] += v

    total_os = fat_qtd = canc_qtd = 0
    valor_total = valor_faturado = canc_valor = 0.0
    por_etapa: dict[str, dict[str, Any]] = {}
    por_cc: dict[str, dict[str, Any]] = {}
    por_cli: dict[str, dict[str, Any]] = {}
    por_mes: dict[str, dict[str, Any]] = {}
    ids_escopo: set[str] = set()

    for r in rows:
        comp = _comp(r)
        if competencia and comp != competencia:
            continue
        valor = _to_float(r.get(c_val)) if c_val else 0.0
        cancelada = bool(c_canc) and str(r.get(c_canc, "") or "").strip().upper().startswith("S")
        if cancelada:
            canc_qtd += 1
            canc_valor += valor
            continue
        total_os += 1
        valor_total += valor
        if c_fat and str(r.get(c_fat, "") or "").strip().upper().startswith("S"):
            fat_qtd += 1
            valor_faturado += valor
        if c_id:
            ids_escopo.add(_norm_cod(r.get(c_id)))
        etapa = (str(r.get(c_etapa, "") or "").strip() if c_etapa else "") or "(sem etapa)"
        _bump(por_etapa, etapa, valor)
        cc = (_norm_cod(r.get(c_cc)) if c_cc else "") or "(sem centro de custo)"
        _bump(por_cc, cc, valor)
        cod_cli = (_norm_cod(r.get(c_cli)) if c_cli else "") or "(sem cliente)"
        _bump(por_cli, cod_cli, valor)
        if comp:
            _bump(por_mes, comp, valor)

    # Tipos de serviço (tabela-filha), restritos às OS em escopo quando há competência.
    por_serv: dict[str, dict[str, Any]] = {}
    try:
        srows = _fetch_csv(TBL_OS_SERV)
    except Exception as exc:
        logger.warning("Falha em servicosprestados: %s", exc)
        srows = []
    if srows:
        sh = list(srows[0].keys())
        s_id   = _detecta_coluna(sh, [COL_OSSERV_ID, "cabecalho_ncodos"])
        s_desc = _detecta_coluna(sh, [COL_OSSERV_DESC, "servicosprestados_cdescserv"])
        s_qtd  = _detecta_coluna(sh, [COL_OSSERV_QTD, "servicosprestados_nqtde"])
        for sr in srows:
            if competencia and s_id and _norm_cod(sr.get(s_id)) not in ids_escopo:
                continue
            desc = (str(sr.get(s_desc, "") or "").strip() if s_desc else "") or "(sem descrição)"
            a = por_serv.setdefault(desc, {"itens": 0, "quantidade": 0.0})
            a["itens"] += 1
            a["quantidade"] += _to_float(sr.get(s_qtd)) if s_qtd else 0.0

    def _top(d: dict[str, dict[str, Any]], chave: str) -> list[dict[str, Any]]:
        out = []
        for k, a in sorted(d.items(), key=lambda x: x[1]["valor"], reverse=True)[:limite]:
            item: dict[str, Any] = {chave: k, "qtd_os": a["qtd"], "valor": round(a["valor"], 2)}
            if chave == "codigo_cliente":
                item = {"cliente": nome_map.get(k) or k, "codigo": k,
                        "qtd_os": a["qtd"], "valor": round(a["valor"], 2)}
            out.append(item)
        return out

    return {
        "status": "ok",
        "fonte": TBL_OS,
        "escopo": competencia or "todas as competências",
        "fonte_nome_cliente": "omie_clientes" if nome_map else "indisponivel (exibindo código)",
        "total_os": total_os,
        "valor_total": round(valor_total, 2),
        "faturadas": fat_qtd,
        "nao_faturadas": total_os - fat_qtd,
        "valor_faturado": round(valor_faturado, 2),
        "canceladas_excluidas": {"qtd": canc_qtd, "valor": round(canc_valor, 2)},
        "por_etapa": [
            {"etapa": k, "qtd_os": a["qtd"], "valor": round(a["valor"], 2)}
            for k, a in sorted(por_etapa.items(), key=lambda x: x[1]["valor"], reverse=True)
        ],
        "por_centro_custo": _top(por_cc, "centro_custo"),
        "top_clientes": _top(por_cli, "codigo_cliente"),
        "top_tipos_servico": [
            {"servico": k, "itens": a["itens"], "quantidade": round(a["quantidade"], 2)}
            for k, a in sorted(por_serv.items(), key=lambda x: x[1]["itens"], reverse=True)[:limite]
        ],
        "por_mes": [
            {"competencia": c, "qtd_os": a["qtd"], "valor": round(a["valor"], 2)}
            for c, a in sorted(por_mes.items())
        ],
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
def resumo_locanorte(competencia: str | None = None) -> dict:
    """
    Resumo gerencial da Locanorte (JSON): base cadastral + financeiro ao vivo.

    competencia: mês do faturamento 'AAAA-MM' (ex.: '2026-03'). Vazio = mês corrente.
      Afeta APENAS faturamento_mes; os títulos refletem a posição ATUAL.
    """
    try:
        comp = _valida_competencia(competencia)
    except ValueError as exc:
        return {"status": "erro", "erro": str(exc)}
    return {
        "contrato_versao": CONTRATO_VERSAO,
        "data_referencia": _agora().isoformat(timespec="seconds"),
        "competencia_faturamento": comp or _agora().strftime("%Y-%m"),
        "empresa": CADASTRO,
        "financeiro": _bloco_financeiro(comp),
    }


@mcp.tool()
def faturamento(competencia: str | None = None) -> dict:
    """
    Faturamento (receita) de UM mês. Usa tabela_dre_omie; se faltar/sem linhas,
    cai para a NFS-e (omie_servicos_nfse). competencia: 'AAAA-MM'. Vazio = mês corrente.
    """
    try:
        comp = _valida_competencia(competencia)
    except ValueError as exc:
        return {"status": "erro", "erro": str(exc)}
    if not KONDADO_TOKEN:
        return {
            "status": "indisponivel",
            "competencia": comp or _agora().strftime("%Y-%m"),
            "erro": "KONDADO_TOKEN não configurado nas variáveis de ambiente.",
        }
    try:
        dre_rows = _fetch_csv(TBL_DRE)
    except Exception as exc:
        logger.warning("Falha ao buscar DRE (faturamento): %s", exc)
        dre_rows = None
    bloco = _resolve_faturamento(dre_rows, comp)
    return {
        "contrato_versao": CONTRATO_VERSAO,
        "data_referencia": _agora().isoformat(timespec="seconds"),
        **bloco,
    }


@mcp.tool()
def fluxo_caixa() -> dict:
    """Posição de caixa hoje + vencimentos por janela + projeção curta (7/15/30 dias)."""
    caixa   = _safe("caixa_hoje",         _caixa_hoje)
    pagar   = _safe("a_pagar_janelas",    lambda: _janelas_vencimento(TBL_PAGAR))
    receber = _safe("a_receber_janelas",  lambda: _janelas_vencimento(TBL_RECEBER))

    projecao: dict[str, Any] = {"status": "indisponivel"}
    if all(x.get("status") == "ok" for x in (caixa, pagar, receber)):
        s = caixa["saldo_atual_total"]
        em7  = round(s    + receber["ate_7d"]  - (pagar["vencido"] + pagar["ate_7d"]), 2)
        em15 = round(em7  + receber["ate_15d"] -  pagar["ate_15d"], 2)
        em30 = round(em15 + receber["ate_30d"] -  pagar["ate_30d"], 2)
        projecao = {"status": "ok", "saldo_hoje": s, "em_7d": em7, "em_15d": em15, "em_30d": em30}

    return {
        "status": "ok",
        "contrato_versao": CONTRATO_VERSAO,
        "data_referencia": _agora().isoformat(timespec="seconds"),
        "caixa_hoje": caixa,
        "a_pagar": pagar,
        "a_receber": receber,
        "projecao": projecao,
    }


@mcp.tool()
def dre_resultado(ano: int | None = None, competencia: str | None = None) -> dict:
    """
    Resultado Operacional do DRE separando REALIZADO de PROJETADO.
    - ano: filtra um ano (ex.: 2026). Vazio = ano corrente.
    - competencia: 'AAAA-MM' para um único mês (sobrepõe `ano`).
    """
    try:
        comp = _valida_competencia(competencia)
    except ValueError as exc:
        return {"status": "erro", "erro": str(exc)}
    if ano is not None:
        try:
            ano = int(ano)
        except (TypeError, ValueError):
            return {"status": "erro", "erro": f"ano inválido: '{ano}'. Use um inteiro, ex.: 2026."}
    if not KONDADO_TOKEN:
        return {"status": "indisponivel", "erro": "KONDADO_TOKEN não configurado nas variáveis de ambiente."}
    # Fonte primária: DRE (tabela_dre_omie). Se faltar/erro, cai p/ aproximação por títulos.
    try:
        dre_rows = _fetch_csv(TBL_DRE)
    except Exception as exc:
        logger.warning("Falha ao buscar DRE (dre_resultado): %s", exc)
        dre_rows = None
    if dre_rows is not None:
        bloco = _safe("dre_resultado", lambda: _dre_resultado(dre_rows, ano, comp))
        if bloco.get("status") == "ok":
            bloco.setdefault("fonte_resultado", "DRE (tabela_dre_omie)")
            return {
                "contrato_versao": CONTRATO_VERSAO,
                "data_referencia": _agora().isoformat(timespec="seconds"),
                **bloco,
            }
    bloco = _safe("dre_resultado_titulos", lambda: _dre_resultado_titulos(ano, comp))
    return {
        "contrato_versao": CONTRATO_VERSAO,
        "data_referencia": _agora().isoformat(timespec="seconds"),
        **bloco,
    }


@mcp.tool()
def top_clientes(limite: int = 10) -> dict:
    """
    Maiores clientes por contas a receber: valor_total (exclui CANCELADO) e
    valor_em_aberto. limite: quantos no ranking (default 10; mínimo 1).
    """
    try:
        limite = int(limite)
    except (TypeError, ValueError):
        return {"status": "erro", "erro": f"limite inválido: '{limite}'. Use um inteiro, ex.: 10."}
    if limite < 1:
        limite = 10
    if not KONDADO_TOKEN:
        return {"status": "indisponivel", "erro": "KONDADO_TOKEN não configurado nas variáveis de ambiente."}
    bloco = _safe("top_clientes", lambda: _top_clientes(limite))
    return {
        "contrato_versao": CONTRATO_VERSAO,
        "data_referencia": _agora().isoformat(timespec="seconds"),
        **bloco,
    }


@mcp.tool()
def coletas(competencia: str | None = None, limite: int = 10) -> dict:
    """
    Operação de coletas/locações a partir das Ordens de Serviço (Omie). Cada OS é
    uma locação/coleta de caçamba. Retorna total e valor (exclui CANCELADA),
    faturadas x não faturadas e quebras por etapa, centro de custo (qual caminhão),
    cliente (NOME), tipo de serviço e mês.
    - competencia: 'AAAA-MM' filtra pela data de previsão da OS (vazio = todas).
    - limite: tamanho dos rankings (default 10; mínimo 1).
    OBS: reflete o último sync do Kondado (a OS não é "tempo real").
    """
    try:
        comp = _valida_competencia(competencia)
    except ValueError as exc:
        return {"status": "erro", "erro": str(exc)}
    try:
        limite = int(limite)
    except (TypeError, ValueError):
        return {"status": "erro", "erro": f"limite inválido: '{limite}'. Use um inteiro, ex.: 10."}
    if limite < 1:
        limite = 10
    if not KONDADO_TOKEN:
        return {"status": "indisponivel", "erro": "KONDADO_TOKEN não configurado nas variáveis de ambiente."}
    bloco = _safe("coletas", lambda: _coletas(comp, limite))
    return {
        "contrato_versao": CONTRATO_VERSAO,
        "data_referencia": _agora().isoformat(timespec="seconds"),
        **bloco,
    }


# ----------------------------------------------------------------------------
# 6) BOOTSTRAP
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
