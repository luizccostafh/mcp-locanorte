# HANDOFF — Construção do MCP Locanorte

Documento de transferência de contexto. Resume o que foi construído e decidido na criação/deploy
do servidor MCP da Locanorte, para que o trabalho continue no Claude Code sem perder histórico.

> **Atualizado em 2026-07-07** — reconciliação GitHub/Render/Kondado (ver seção 6.1) corrige
> a suposição de que a `tabela_dre_omie` estava vazia (não está mais) e atualiza as datas de
> sync das tabelas operacionais. Texto anterior (2026-06-19) descrevia o `server.py` v1.12.0,
> 8 tools, financeiro + operacional `coletas` e `centro_custo` (rentabilidade por caminhão) —
> isso permanece válido, só os pontos acima foram corrigidos.

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
Tools (9): status_locanorte, resumo_locanorte, faturamento, fluxo_caixa,
           dre_resultado, top_clientes, coletas, centro_custo, lancamentos (dados reais)
```

**Destinos Via Kondado:** **40059** = VIVO (o `server.py` lê via `KONDADO_TOKEN`);
**39010** = MORTO (`SCHEMA_NOT_FOUND`). Integrações no conector Omie **39483 → destino 40059**.

> **Atualização 2026-07-17:** o conector **MCP do Kondado** (`run_query` KSQL) disponível no Claude Code
> agora aponta para um **destino VIVO** com todas as tabelas reais — dá para amostrar os dados do servidor
> por ele (antes caía no 39010 morto). Confirmado via `list_tables`/`run_query`: `tabela_dre_omie`
> **populada** (1.371 linhas) e nova tabela curada `locanorte_kondado_mcp` (2.203 linhas, pagar+receber
> unificados com `valor_dre` rateado por categoria). ⚠️ Inspecionada em 2026-07-17: NÃO tem centro de
> custo/`ncodcc` e a soma de `valor_dre` NÃO é o Resultado Operacional oficial — ver seção 8, item 8.

Relação com o **Kondado** (decisão do usuário): o Kondado continua sendo a camada de
**ETL/integração** (Omie → data warehouse → Power BI **e** este MCP). O MCP é a camada de
**acesso via IA**. As duas convivem; o Kondado só será substituído mais adiante.

---

## 3. server.py atual (v1.16.0 — no ar)

> **v1.16.0 — `centro_custo` DESTRAVADO (rentabilidade por caminhão):** usa o RATEIO financeiro
> (tabelas-filhas `omie_lancamentos_contas_{pagar,receber}_distribuicao`, `distribuicao_ccoddep` +
> `distribuicao_nvaldep`), juntando ao título-pai por `codigo_lancamento_omie` p/ excluir CANCELADO e
> filtrar competência. NOME do caminhão via `omie_departamentos` (placas `2.x CAM-...`). Substitui a
> v1.12.0 (que buscava `ncodcc` no título — não existe lá; a receita das OS não era por caminhão).
> ⚠️ A receita costuma vir rateada por OPERAÇÃO (4.x) e o custo por CAMINHÃO (2.x)/ÁREA — para margem por
> caminhão/serviço, alinhar o rateio no Omie (campo `aviso` na saída).

> **v1.15.0 — `dre_resultado` ganha o DEMONSTRATIVO (DRE linha a linha):** `demonstrativo_realizado`
> traz a DRE realizada por `descricaodre_n3` (ordenada pelo código), com subtotais por grupo n1 e o
> Resultado Operacional — o P&L completo (como no Power BI), da hierarquia JÁ classificada da
> `tabela_dre_omie` (sem casamento por nome, sem arquivo que envelhece). Validado com os 5 arquivos do
> contador (categorias_atual, .pbix, modelo v23, FECHAMENTO_202606_V5, plano de contas): TODAS as
> categorias não-classificadas são intencionalmente fora da DRE (empréstimos, PIS/COFINS s/ faturamento
> = guias a recolher, adiantamentos, retenções, distribuição de lucros) → o Resultado Operacional
> +591.420,03 já é o correto e um motor de classificação por categoria seria redundante.

> **v1.14.0 — `dre_resultado` = RESULTADO OPERACIONAL correto:** soma só os grupos operacionais do DRE
> (n1 (1) Lucro Bruto + (2) Despesas, via `KONDADO_DRE_N1_RESULTADO`) e EXCLUI (3) Investimentos/CAPEX
> e os lançamentos SEM classificação no DRE (não-operacionais: distribuição de lucros, transferência
> entre contas, retenções/guias descontadas em folha), reportados à parte em `excluidos`. Antes somava
> TUDO (misturava CAPEX/não-operacionais). Alinhado à DRE gerencial do Power BI (`GER Resultado Liquido`
> = EBIT + Res. Financeiro; CAPEX/empréstimos só no DFC) e ao modelo de categorias v23. jan–jun/2026:
> **+R$ 591.420,03** (excluídos: CAPEX −80.510,06 e não-classificado +302.001,40). Para o oficial fechar
> 100%: importar no Omie o modelo de plano de contas/categorias v23 (mapeia as categorias restantes).

> **v1.13.0 — NOVA TOOL `lancamentos`:** razão UNIFICADO de contas a pagar + a receber a partir da
> tabela curada `locanorte_kondado_mcp` (1 linha = lançamento × categoria rateada; `valor_dre` já
> assinado). Quebras por categoria (descrição), cliente/fornecedor (NOME) e mês; separa realizado x
> projetado; exclui CANCELADO. ⚠️ `resultado_liquido_dre` = NET de todos os títulos (inclui
> não-operacionais) — NÃO é o Resultado Operacional oficial (use `dre_resultado`). A tabela foi
> inspecionada ao vivo (2026-07-17): está no destino 40059 e NÃO carrega centro de custo/`ncodcc`.

> **Evolução v1.6.0 → v1.12.0 (resumo):** parâmetros tipados (`competencia`/`ano`/`limite`);
> tools `faturamento`, `dre_resultado`, `top_clientes`, `coletas`, `centro_custo`; FALLBACKS quando a
> `tabela_dre_omie` (kubo) está vazia — faturamento via **NFS-e**, de-para de categoria via
> **omie_categorias**, Resultado via **títulos** (aproximação), e NOME do cliente via **omie_clientes**.
> `coletas` (v1.11.0) é a 1ª tool operacional: lê as **Ordens de Serviço** (cada OS = locação/coleta
> de caçamba) e agrega por etapa, centro de custo, cliente, tipo de serviço e mês.
> `centro_custo` (v1.12.0) cruza a RECEITA das OS (por `ncodcc`) com o CUSTO das contas a pagar do mesmo
> centro de custo → **rentabilidade por caminhão** (receita − custo, margem %, ranking). A coluna de
> centro de custo das contas a pagar é auto-detectada; se não for achada, o custo volta `indisponivel`
> com as colunas disponíveis e a receita por CC ainda sai.
> **Fix v1.11.1:** `_caixa_hoje` ignora linhas de saldo com data FUTURA (série diária com dias projetados);
> só considera `data_saldo <= hoje` (corrige o `data_saldo_base` que voltava no futuro).

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
    **(v1.11.1)** `_caixa_hoje` ignora saldo de data futura (`data_saldo <= hoje`; expõe
    `linhas_futuras_ignoradas`).
  - `faturamento()` / `dre_resultado()` / `top_clientes()` → ver detalhes no CLAUDE.md (com fallbacks).
  - `coletas(competencia?, limite=10)` → dict **(v1.11.0)**: operação via Ordens de Serviço; quebras por
    etapa, centro de custo, cliente (NOME) e tipo de serviço. Reflete o último sync do Kondado.
  - `centro_custo(competencia?, limite=10)` → dict **(v1.12.0)**: rentabilidade por centro de custo
    (caminhão) = receita das OS (por `informacoesadicionais_ncodcc`) − custo das contas a pagar do mesmo
    centro de custo; `rentabilidade`, `margem_pct`, `totais`, ranqueado. Coluna de CC nas contas a pagar
    auto-detectada (`KONDADO_COL_PAGAR_CC`); se faltar, `custo` volta `indisponivel` (receita ainda sai).
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

### 6.1 Nova verificação (2026-07-07) — GitHub / Render / Kondado

Checagem cruzada dos três lados, feita a partir de uma sessão remota (Claude Code on the web)
cujo proxy de rede **bloqueia** `mcp-locanorte.onrender.com` (egress allowlist não inclui o host) —
por isso não foi possível chamar as tools do MCP Locanorte ao vivo diretamente. A validação usou
GitHub MCP, o MCP nativo do Kondado (`MCP_KONDADO`, reapontado para o destino 40059) e arquivos
que o usuário exportou manualmente (DRE em `.xlsx`, lote de NFS-e em `.zip`).

- **GitHub:** `main` no commit `f83c812` (`server.py` v1.12.0, 1370 linhas, 8 tools). Confirmado.
- **Render:** deploy do commit `f83c812`, status **Live** (log: `Application startup complete`,
  `Uvicorn running on 0.0.0.0:$PORT`, `Your service is live`). Auto-Deploy On Commit funcionando —
  Render está no mesmo HEAD do GitHub. Status page do Render também sem incidentes no período.
- **Kondado (destino 40059):** confirmado ativo — 36 integrações Omie, 53 tabelas no warehouse.
  **Correção importante:** a `tabela_dre_omie` **NÃO está mais vazia** — **1303 linhas**, sync em
  **2026-06-23**. Isso contradiz a suposição registrada na seção 8, item 3 (versão anterior deste
  handoff) de que ela estaria vazia no 40059. Com base na lógica de `_resolve_faturamento()` e
  `dre_resultado()` no `server.py`, a DRE **é a fonte primária de fato** para qualquer competência
  já fechada (ex.: `2026-06`) — o fallback para NFS-e/títulos só entra para o **mês corrente ainda
  em aberto** (sem linha na DRE), que é o comportamento correto/esperado do código.
  - ⚠️ **Achado de código:** `faturamento()` só cai para o fallback se `linhas_consideradas == 0`
    (guarda correta). Já `dre_resultado()` **não tem essa guarda** — se `_fetch_csv(TBL_DRE)` não
    lançar exceção mas devolver zero linhas pra competência pedida, ele retorna `resultado_total: 0`
    como se fosse o resultado oficial, sem cair para `_dre_resultado_titulos` nem sinalizar que o
    mês simplesmente ainda não fechou. Vale considerar adicionar a mesma guarda de `faturamento()`.
  - **Datas de sync divergentes por área:** títulos/DRE/categorias em `2026-06-23`; saldo bancário,
    Ordens de Serviço e NFS-e ainda em `2026-06-17` (mais antigo — atualiza a nota da seção 8, item 2,
    que citava `2026-05-26`). Vale confirmar a cadência do pipeline dessas tabelas operacionais.
  - **Reconciliação DRE × NFS-e (jun/2026), a partir dos arquivos exportados pelo usuário:**
    Receita Líquida Operacional (DRE) = **R$ 275.104,82** vs. valor líquido das NFS-e emitidas no
    mês (73 notas do lote completo, `vLiq`) = **R$ 304.665,88** — gap aparente de **~R$ 29.560**.
    **Explicado (mesmo dia, `FECHAMENTO_202606_V5.xlsx`, aba `Reconciliacao`):** o fechamento contábil
    oficial de junho usa um corte em **notas emitidas 01–25/jun** (68 notas) = **R$ 294.187,45**, que
    **bate exatamente** com a Receita Bruta de Vendas que a DRE registrou para o mês. Ou seja, a maior
    parte do gap é efeito do **corte de fechamento em 25/jun** (o lote completo do usuário tinha 73
    notas até dia 30) — não é inconsistência entre DRE e NFS-e. A mesma planilha também reconcilia
    folha de pagamento, INSS/FGTS/PIS/COFINS/ISS e guias a recolher de jun/2026 com Δ ≈ 0 em quase
    todos os itens — é a fonte de verdade do fechamento mensal, útil pra validar futuras tools de DRE.
  - **Tabela consolidada nova:** modelo Kondado **ID 9926** (`locanorte_kondado_mcp`, fonte
    `lancamentos_omie`) criado em **2026-07-07**, unindo pagar+receber+categorias-rateadas+`valor_dre`
    numa única tabela (colunas: `tipo_lancamento`, `codigo_lancamento_omie`, `codigo_cliente_fornecedor`,
    `codigo_projeto`, `data_competencia`, `data_previsao`, `data_vencimento`, `status_titulo`,
    `codigo_categoria`, `percentual_categoria`, `valor_rateado`, `valor_dre`, `valor_documento`).
    **O `server.py` ainda NÃO lê essa tabela** — continua nas tabelas cruas (`omie_lancamentos_contas_*`,
    `tabela_dre_omie`). Migração em avaliação; pendência: confirmar se `valor_documento` vem repetido
    por linha de rateio de categoria (senão a soma duplica o valor do título) antes de implementar.

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
   `dre_resultado` (v1.7.0), `top_clientes` (v1.8.0), `coletas` (v1.11.0) e `centro_custo` (v1.12.0 —
   rentabilidade por caminhão) entregues e validados. A seguir: detalhe de uma OS, clientes por
   tag/característica. ✅ **Sync RELIGADO (2026-07-17):** o pipeline voltou a rodar — títulos/categorias
   em 2026-06-23, OS/saldo em 2026-06-17, DRE em 2026-07-16 (antes parado em 2026-05-26); `coletas`,
   `centro_custo` e `caixa_hoje` refletem o último sync. ✅ Bug do `caixa_hoje.data_saldo_base` voltar
   no futuro: corrigido na v1.11.1. ⚠️ `centro_custo`: confirmar onde o Omie/Kondado guardam o centro de
   custo nas contas a pagar (pode estar num rateio/filha) — se `custo` voltar `indisponivel`, apontar
   `KONDADO_COL_PAGAR_CC` ou adicionar o join pela filha numa v1.12.1 (a `locanorte_kondado_mcp` já traz
   isso rateado — ver item 8).
3. ✅ **DRE oficial DESTRAVADO (validado 2026-07-17)** — a `tabela_dre_omie` voltou a ter dados (1.371
   linhas, `last_updated` 2026-07-16). `faturamento` e `dre_resultado` usam o DRE oficial, não mais os
   fallbacks. Conferido jan–jun/2026: Receita Líquida R$ 1.982.578,58; Lucro Bruto 1.045.100,91;
   **Resultado Operacional +R$ 591.420,03** (após CAPEX +510.909,97) — no patamar dos ~629 mil da
   referência DAX (gap = base de data `data_emissao` vs competência). ⚠️ Restam R$ 302.001,40 de
   lançamentos SEM classificação no DRE (`niveldre`/`totalizadre` vazios) — categorias a mapear no Omie.
   ⚠️ Pendência herdada (2026-07-07): `dre_resultado()` não tem a mesma guarda de `linhas_consideradas
   > 0` que `faturamento()` — pode reportar `resultado_total: 0` em vez de cair no fallback quando a
   competência pedida ainda não tem linha na DRE.
   🟢 **DUAS VISÕES VÁLIDAS (esclarecido 2026-07-17 com o usuário):** servidor = **+R$ 591.420,03**
   (Resultado pelos **livros do Omie**); `DRE_15_07_CORRIGIDA` (motor v10) = **+R$ 427.889,53** (visão
   **gerencial**). O gap (−163k) é **reclassificação**, não dinheiro novo: o contador reclassifica os
   impostos (ISS/PIS/ISS-retido, ≈ −125.929,81, das NFS-e) como **dedução da receita**; no Omie esses
   impostos já existem como **guias/títulos** (caixa), só destacados de outra forma.
   ⚠️ **DECISÃO CORRIGIDA:** **NÃO lançar** os impostos como novos títulos no Omie — **duplicaria**. O
   `dre_resultado` **fica em 591k** (fiel aos livros); o **ajuste gerencial (−126k → 428k) vive no Power
   BI** (motor v10 do contador). NÃO replicar o cálculo das NFS-e no servidor. Alternativa para expor 428k
   no servidor (não escolhida): contador publica a DRE corrigida como tabela curada no Kondado e aponta-se
   o `dre_resultado` pra ela. (Superada a nota anterior de "corrigir no Omie/re-sync → converge 428k".)
4. ✅ **Parâmetros tipados** — entregue na v1.6.0 (`competencia`/`ano`/`limite`).
5. **Governança / segurança** — religar `enable_dns_rebinding_protection=True` com allowlist
   (`allowed_hosts=["mcp-locanorte.onrender.com", "mcp-locanorte.onrender.com:*"]`,
   `allowed_origins=["https://mcp-locanorte.onrender.com"]`) e auth por token.
   Inclui **rotação periódica do `KONDADO_TOKEN`** — procedimento documentado na seção 10.
6. **Custo** — avaliar downgrade Standard → Starter.
7. **Substituição futura do Kondado** — internalizar o ETL quando houver condições.
8. 🆕 **`locanorte_kondado_mcp` — INSPECIONADA (2026-07-17):** existe no destino **40059** (modelo
   "Kondado MCP Fin Locanorte", ID 9926) → o `server.py` PODE lê-la via hub CSV. Unifica pagar+receber
   por lançamento × categoria rateada; 13 colunas (`tipo_lancamento`, `codigo_lancamento_omie`,
   `codigo_cliente_fornecedor`, `codigo_projeto`, `data_competencia`, `data_vencimento`, `status_titulo`,
   `codigo_categoria`, `percentual_categoria`, `valor_rateado`, `valor_dre`, `valor_documento`).
   ⚠️ **A inspeção derrubou as duas hipóteses:** (a) **NÃO tem centro de custo/`ncodcc`** (só
   `codigo_projeto`) → não destrava o CUSTO do `centro_custo`; (b) somar `valor_dre` **NÃO é** o
   Resultado Operacional oficial — jan–jun/2026 dá net **−33.416** (todos os títulos, inclui
   não-operacionais) vs **+591.420** do `tabela_dre_omie`. Falta-lhe a classificação DRE. Como o DRE
   oficial voltou (item 3), **NÃO** migrar `dre_resultado`/`faturamento` para esta tabela como primária.
   ✅ **DECISÃO (2026-07-17): tool `lancamentos` (v1.13.0) implementada** — razão unificado pagar+receber
   por competência/categoria/cliente, `valor_dre` assinado, `resultado_liquido_dre` rotulado como NET
   (≠ Resultado Operacional oficial). Aditiva, sem tocar no que já funciona. Fallback melhorado do
   `_dre_resultado_titulos` fica como evolução futura de baixa prioridade (DRE oficial já de pé).

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
