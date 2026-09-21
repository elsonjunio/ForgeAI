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

Flags: `--config ARQ` (JSON), `--system TEXTO`, `--no-stream`, `--no-discover`,
`--plugin MODULE:ATTR` (repetível), `--once PROMPT`, `--version`.

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
| `/run <request>` | planeja e executa (planner + executor) |

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
- Histórico só na sessão (sem memória persistente); síncrono.
- O CLI é **host**: não adiciona comportamento de domínio ao core.
