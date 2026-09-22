# forgeai-cli

CLI do ForgeAI. Hoje serve para **chat**; também é um harness para **construir e
testar plugins** antes de instalá-los.

- Depende de `core-agent`.
- Chat via `LLMProvider` (precisa de um plugin de LLM, ex.:
  `code-agent-plugin-opencode-go`).
- Comandos de inspeção funcionam mesmo sem LLM.

## Instalação

```bash
pip install -e "apps/cli"
pip install -e "packages/plugins/code-agent-plugin-opencode-go"   # opcional (chat)
export OPENCODE_API_KEY="..."
forgeai
```

Ou sem instalar: `python -m forge_cli` (com `PYTHONPATH=apps/cli/src`).

## Uso

```bash
forgeai                                  # REPL de chat
forgeai --once "explique o repositório"  # um turno e sai
forgeai --no-discover --plugin meu_pacote.plugin:MeuPlugin
```

Flags: `--config ARQ` (JSON), `--system TEXTO`, `--no-stream`, `--no-progress`,
`--no-discover`, `--plugin MODULE:ATTR` (repetível), `--once PROMPT`, `--version`.

Com um observer anexado, o `/run` mostra progresso por node em tempo real
(`→ node (cap)`, `✓ node`, `✗ node: erro`) no `stderr`; `--no-progress` desliga.

## Comandos

| Comando | Efeito |
|---|---|
| `/help` | ajuda |
| `/exit`, `/quit` | encerra |
| `/clear`, `/history`, `/system <texto>` | chat |
| `/plugins` | plugins registrados |
| `/capabilities [kind]` | capabilities |
| `/groups` | grupos e membros |
| `/planners [group]` | planners |
| `/providers` | LLM providers e default |
| `/config` | configuração resolvida |
| `/interaction <msg>` | testa o `InteractionProvider` |
| `/plan <request>` | planeja e mostra o `ExecutionPlan` |
| `/run <request>` | planeja, executa, observa, compacta, recupera de erros e replaneja; sintetiza a resposta final (com um `Synthesizer`) |

## Desenvolvendo plugins com o CLI

```bash
forgeai --no-discover --plugin meu_pacote.plugin:MeuPlugin
> /capabilities
> /groups
> /planners
```

## Limites

- Chat usa apenas `LLMProvider.complete`. `/plan` e `/run` usam um `Planner`
  (ex.: `code-agent-plugin-llm-planner`); sem tools instalados o plano tende a
  ser vazio.
- Com um `Synthesizer` (ex.: `code-agent-plugin-llm-synthesizer`), `/run` aplica
  a compactação pedida pelo planner (`PlanningResult.compaction`) e imprime uma
  resposta final sintetizada. Sem synthesizer, `/run` mostra as iterações e avisa
  que falta o plugin.
- Com um `Validator` (ex.: `code-agent-plugin-llm-validator`), `/run` valida o
  **conjunto** no desfecho; reprovando, as issues voltam ao planner e ele
  replaneja (mesmo orçamento/guard) antes de responder.
- Erros recuperáveis (ex.: arquivo inexistente) não abortam o `/run`: o host
  devolve a falha ao planner e replaneja, limitado por `_MAX_RECOVERIES` e por um
  guard de não-progresso (mesma `capability` + `parameters` + erro).
- Planos inválidos (edges órfãs, JSON inválido, capability inexistente) também
  são **descartados** e devolvidos ao planner com o erro + extrato do plano
  rejeitado, **preservando o histórico** (`observations`/`checkpoint`) acumulado.
- Orçamentos vêm de `CoreConfig.budgets` (`max_iterations`, `max_recoveries`,
  `max_nodes`, `deadline_seconds`, `max_total_tokens`, `compaction_chars`,
  `compaction_keep_last`, `history_limit`). O `/run` aplica prazo/tokens entre
  iterações, compacta automaticamente acima do limiar e injeta o histórico da
  sessão no planner. O uso de tokens do run é impresso no fim (`uso: ...`).
- Histórico só na sessão (sem memória persistente); síncrono.
- O CLI é **host**: não adiciona comportamento de domínio ao core.
