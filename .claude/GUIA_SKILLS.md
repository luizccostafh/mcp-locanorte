# Guia de Skills — MCP Locanorte

Como usar as skills/agents disponíveis neste repo. As skills **ativam sozinhas** quando o contexto
casa com a descrição — você não precisa nomeá-las; basta descrever a tarefa. Também dá para chamar
pelo nome ou pelo gatilho (ex.: `/ponytail`).

---

## 🟢 Do projeto Locanorte (financeiro/dados)

| Situação | Skill / agent | Como chamar |
|---|---|---|
| "Qual o resultado / DRE?", "como está o caixa?", "quanto faturamos?", "maiores clientes", "rentabilidade por caminhão", "quanto pagamos de imposto" | **consultar-financeiro** | pergunta natural |
| "Monta a planilha de custos/margem", "custo por caminhão", "rentabilidade da frota" | **planilha-custos** | pedido natural |
| Consultar dados crus do warehouse Kondado (KSQL) para uma pergunta/relatório | **kondado-query** *(agent)* | "usa o kondado-query para..." |

> ⚠️ Ressalva de negócio (embutida na skill `consultar-financeiro`): o `dre_resultado` retorna
> **+591.420,03** (Resultado pelos **livros do Omie**); a DRE **gerencial** do contador mostra
> **+427.889,53** (reclassifica impostos sobre vendas). São **duas visões válidas** — ao reportar,
> deixe claro qual está usando.

---

## 🔵 Fluxo de desenvolvimento (Superpowers)

| Situação | Skill |
|---|---|
| **Antes de** criar feature/componente — explorar o que realmente é preciso | **brainstorming** |
| Tenho spec/requisitos e quero um plano multi-step | **writing-plans** |
| Executar um plano escrito, com checkpoints de review | **executing-plans** |
| Executar plano com tarefas independentes na mesma sessão | **subagent-driven-development** |
| 2+ tarefas independentes ao mesmo tempo | **dispatching-parallel-agents** |
| Implementar feature/bugfix (teste primeiro) | **test-driven-development** |
| Bug, teste falhando, comportamento inesperado | **systematic-debugging** |
| Antes de dizer "está pronto/passa" — provar com evidência | **verification-before-completion** |
| Terminei uma feature e quero revisão | **requesting-code-review** |
| Recebi feedback de review e vou aplicar | **receiving-code-review** |
| Feature que precisa de isolamento do workspace | **using-git-worktrees** |
| Implementação pronta — decidir merge / PR / cleanup | **finishing-a-development-branch** |
| Criar/editar uma skill nova | **writing-skills** |
| "Como acho/uso as skills?" (meta) | **using-superpowers** |

**Fluxo completo de uma feature nova:**
`brainstorming` → `writing-plans` → `test-driven-development` → `verification-before-completion`
→ `requesting-code-review` → `finishing-a-development-branch`.

---

## 🎨 Design de interface (Impeccable)

| Situação | Skill |
|---|---|
| Criar, redesenhar, auditar, polir **qualquer UI** (site, dashboard, form, componente, tipografia, cores, acessibilidade, animação) | **impeccable** |

> ⚠️ É para **frontend/UI**. O `mcp-locanorte` é um servidor Python sem UI — use o impeccable
> quando for mexer em **painel HTML, landing page, relatório web** ou outro front.
> Faz check de atualização em `impeccable.style` (desligável por env).

---

## 🟡 Enxugar / anti-over-engineering (Ponytail)

| Situação | Skill / comando |
|---|---|
| Quero a solução **mais simples que funciona** (modo persistente) | **ponytail** → `/ponytail lite\|full\|ultra` · desliga com "stop ponytail" |
| Revisar **um diff** só procurando over-engineering | **ponytail-review** → `/ponytail-review` |
| Auditar **o repo inteiro** procurando bloat / o que deletar | **ponytail-audit** → `/ponytail-audit` |
| Ver os comandos/modos do ponytail | **ponytail-help** |

> Instaladas **sem hooks** → não auto-injetam; só atuam quando invocadas.

---

## Dicas gerais
- **Não precisa nomear** a skill — descreva a tarefa e o Claude puxa a certa (ex.: "tem um bug no
  cálculo do DRE" → aciona `systematic-debugging`).
- **Controlar as opinativas:** `/ponytail full` liga o modo enxuto; "modo normal" / "stop ponytail" sai.
- **Governança:** as skills de terceiros e suas notas de segurança/transparência estão documentadas no
  commit que as instalou (PR #7). Para remover uma skill, basta apagar a pasta dela em `.claude/skills/`.
