# plugins

Pacotes de plugin do monorepo. Cada plugin é um pacote Python independente que
depende de `core-agent` e declara um entry point no grupo `core_agent.plugins`
(assim é descoberto automaticamente por `build_core()`).

## Plugins existentes

| Pacote | Tipo | Descrição |
|---|---|---|
| [`code-agent-plugin-opencode-go`](code-agent-plugin-opencode-go/) | `LLMProvider` | API OpenCode Go (OpenAI-compatible) |
| [`code-agent-plugin-llm-planner`](code-agent-plugin-llm-planner/) | `Planner` | gera `ExecutionPlan` via LLM |

## Criando um plugin

Cada plugin é um pacote com `pyproject.toml` (com `[build-system]` e `[project]`)
e `src/<pacote>/`. Guias:

- [`docs/creating-an-llm-plugin.md`](../../docs/creating-an-llm-plugin.md)
- [`docs/creating-plugins.md`](../../docs/creating-plugins.md)

## Empacotamento

O workflow de release ([`.github/workflows/release.yml`](../../.github/workflows/release.yml))
descobre e empacota automaticamente qualquer diretório sob `packages/plugins/`
que tenha um `pyproject.toml` com `[build-system]` e `[project]`.

> Os testes do monorepo importam os plugins via `pythonpath` (sem instalá-los),
> para que a descoberta por entry point não torne os testes do core
> não-determinísticos.
