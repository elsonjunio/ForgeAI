# Usando o core em um entrypoint

Este guia mostra como embutir o `core-agent` em um ponto de entrada — um CLI de
terminal, um script de automação, um job de CI ou qualquer ferramenta que rode
Python. O core é uma **biblioteca**: ele não traz CLI, servidor nem LLM; você
fornece o entrypoint e as capacidades (via plugins).

> Requisitos: Python 3.10+. Instale o core com `pip install -e "packages/core"`
> (a partir da raiz do monorepo) ou como dependência `core-agent`.

## O que o entrypoint precisa fazer

Todo entrypoint segue o mesmo ciclo:

1. **Montar** o core com `build_core(...)`, opcionalmente com configuração e plugins.
2. **Executar** o runtime genérico (`container.runtime`) e/ou o workflow do Code
   Agent (`container.workflow`).
3. **Observar** eventos (logs/telemetria) e tratar `CoreError`.
4. **Encerrar** com `container.shutdown()`.

`build_core` devolve um `CoreContainer` com: `config`, `events`, `registry`,
`runtime` (grafo genérico de nós contribuídos por plugins) e `workflow`
(pipeline do Code Agent).

## Uso mínimo (zero plugins)

```python
from core import build_core

# discoverers=[] desliga a descoberta por entry points.
core = build_core(discoverers=[])
try:
    final = core.runtime.run(task="qualquer coisa")
    print(final.status)   # "completed"
    print(final.output)   # None — nenhum plugin contribuiu com nós
finally:
    core.shutdown()
```

O core sempre monta com zero plugins. O `workflow`, porém, só roda quando há um
`LLMProvider` disponível (caso contrário levanta `MissingCapabilityError`).

## Rodando o workflow do Code Agent

```python
from core import CoreError, build_core

core = build_core()          # discoverers=None => descobre por entry points
try:
    state = core.workflow.run(request="refatore o módulo de pagamento")
except CoreError as exc:
    print(f"falhou ({type(exc).__name__}): {exc}")
    raise
finally:
    core.shutdown()

print(state.status)                 # completed | failed
print(state.plan.summary)           # plano produzido
print([t.output for t in state.completed_tasks])
print(state.review.approved)
```

Para uso assíncrono (útil dentro de frameworks async):

```python
import asyncio
from core import build_core


async def run_once(request: str):
    core = build_core()
    try:
        return await core.workflow.arun(request=request)
    finally:
        core.shutdown()


state = asyncio.run(run_once("revise o Pull Request #42"))
```

## Configurando o core

`CoreConfig` é um modelo Pydantic. O entrypoint pode montá-lo de um mapping ou de
um arquivo JSON via `load_config`:

```python
from core import CoreConfig, build_core, load_config

config = load_config("agent.json")            # ou load_config({...})
core = build_core(config=config)
```

`agent.json`:

```json
{
  "app_name": "meu-code-agent",
  "environment": "production",
  "plugins": {
    "code-agent-plugin-openai": { "enabled": true, "settings": { "model": "gpt-4o" } },
    "code-agent-plugin-git": { "enabled": true }
  },
  "defaults": { "llm": "openai" },
  "langgraph": { "recursion_limit": 25 },
  "workflow": { "max_attempts": 3 }
}
```

Campos principais:

| Campo | Efeito |
|---|---|
| `plugins.<id>.enabled` | `false` faz o plugin nem ser registrado. |
| `plugins.<id>.settings` | Fica disponível ao plugin em `context.settings`. |
| `defaults` | Provider default por `kind` (`{"llm": "openai"}`) ou nome da classe. |
| `workflow.max_attempts` | Limite de passagens de `execution` (retry). |
| `langgraph.recursion_limit` | Orçamento de recursão do grafo genérico. |

## Selecionando plugins explicitamente

Se você não quer depender de entry points (por exemplo, em testes ou em um
bundle), passe as instâncias:

```python
from core import build_core
from meu_pacote import MeuPlugin

core = build_core(plugins=[MeuPlugin()], discoverers=[])
```

> **Atenção à distinção de "discovery":**
> - `build_core(discoverers=...)` é a **descoberta de plugins** no momento do build
>   (por padrão, entry points do grupo `core_agent.plugins`).
> - A etapa `discovery` do workflow consulta os **`Discoverer` registrados como
>   capability** (via `declare_capabilities`/`context.register_capability`).

## Exemplo completo: CLI de terminal

`meu_agente/cli.py`:

```python
"""CLI mínimo sobre o core-agent."""

from __future__ import annotations

import argparse
import sys

from core import CoreConfig, CoreError, build_core, load_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="meu-code-agent")
    parser.add_argument("request", nargs="?", help="pedido do usuário")
    parser.add_argument("--config", metavar="ARQ", help="config JSON")
    parser.add_argument("--json", action="store_true", help="saída JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.request:
        print("erro: informe um pedido", file=sys.stderr)
        return 2

    config = load_config(args.config) if args.config else CoreConfig()
    core = build_core(config=config)
    try:
        state = core.workflow.run(request=args.request)
    except CoreError as exc:
        print(f"erro ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
    finally:
        core.shutdown()

    if args.json:
        print(state.model_dump_json(indent=2))
    else:
        print(f"status: {state.status}")
        for task in state.completed_tasks:
            print(f"- {task.id}: {task.output}")
    return 0 if state.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

No `pyproject.toml` **da sua aplicação** (não do core), registre o script:

```toml
[project.scripts]
meu-code-agent = "meu_agente.cli:main"
```

Depois de `pip install -e .`:

```bash
meu-code-agent "corrija o bug do parser" --config agent.json
meu-code-agent --json "revise o README" > resultado.json
```

## Usando em outra ferramenta de automação

O core é apenas uma biblioteca Python; exponha `run_once` para o seu
orquestrador (task runner, handler HTTP, bot, job agendado):

```python
from core import CoreError, build_core


def run_agent(request: str, config=None) -> dict:
    """Fronteira síncrona reutilizável por qualquer automação."""
    core = build_core(config=config)
    try:
        state = core.workflow.run(request=request)
    except CoreError as exc:
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}
    finally:
        core.shutdown()

    return {
        "ok": state.status == "completed",
        "status": state.status,
        "tasks": [{"id": t.id, "output": t.output} for t in state.completed_tasks],
        "review": state.review.model_dump() if state.review else None,
    }
```

### Observabilidade por eventos

Assine eventos para logging/telemetria. Não é preciso tocar no core:

```python
from core import WorkflowEvents, build_core

core = build_core()
logger = print  # troque pelo seu logger

for event_type in (
    WorkflowEvents.WORKFLOW_STARTED,
    WorkflowEvents.STAGE_STARTED,
    WorkflowEvents.STAGE_FINISHED,
    WorkflowEvents.WORKFLOW_RETRY,
    WorkflowEvents.WORKFLOW_COMPLETED,
    WorkflowEvents.WORKFLOW_FAILED,
):
    core.events.subscribe(event_type, lambda event: logger(f"[{event.type}] {event.source}"))

state = core.workflow.run(request="...")
core.shutdown()
```

O runtime genérico emite `CoreEvents.AGENT_STARTED`/`AGENT_FINISHED` e
`AGENT_NODE_STARTED`/`AGENT_NODE_FINISHED`.

### Reagir a retry/interrupção

O workflow repete `execution` enquanto `attempts < workflow.max_attempts` e
encerra como `failed` quando esgota. O entrypoint decide o que fazer com o
estado final:

```python
state = core.workflow.run(request="...")
if state.status == "failed":
    for err in state.errors:
        print(f"{err.stage}: {err.message}")
    # reenfileirar, notificar, abrir issue, etc.
```

## Tratamento de erros

Capture `CoreError` no entrypoint; os subtipos dão contexto:

| Exceção | Quando ocorre |
|---|---|
| `MissingCapabilityError` | Faltou um provider exigido (ex.: nenhum `LLMProvider`). |
| `AmbiguousCapabilityError` | Vários providers e nenhum default selecionado. |
| `DuplicateCapabilityError` | Dois providers com o mesmo `(kind, name)`. |
| `DuplicatePluginError` / `InvalidPluginError` | Plugin duplicado ou inválido. |
| `DiscoveryError` | Falha ao carregar um entry point de plugin. |
| `ConfigError` | Configuração ausente/ inválida. |
| `InvalidGraphError` | Nós contribuídos não formam um grafo válido. |

Erros de capability ausente são explícitos:

```text
MissingCapabilityError: no LLM provider is registered (capability kind 'llm');
install a plugin that provides an LLMProvider
```

## Executando sem descoberta automática

Útil em CI e ambientes herméticos (evita depender do que está instalado):

```python
core = build_core(
    config=load_config("agent.json"),
    plugins=[MeuPlugin()],
    discoverers=[],   # nenhum entry point é consultado
)
```

## Boas práticas

- Sempre `try/finally` com `core.shutdown()` para liberar recursos dos plugins.
- Reaproveite **uma** instância de `CoreContainer` por processo quando possível;
  crie uma por execução apenas se precisar de isolamento.
- Não importe `langgraph`/`langchain_core` no seu entrypoint; use só a API pública
  de `core`.
- Para CLIs, retorne um código de saída coerente (`0` sucesso, `1` falha do
  workflow, `2` uso incorreto).
- Não hardcode credenciais/config no código: use `load_config` + variáveis de
  ambiente carregadas pelo seu app.

## Referência rápida

```python
from core import (
    build_core,        # build_core(config=None, *, plugins=(), discoverers=None)
    load_config,       # load_config(None | mapping | "arquivo.json")
    CoreConfig, CoreError, MissingCapabilityError,
    CoreEvents, WorkflowEvents,
)

core.config            # CoreConfig resolvido
core.events            # EventBus (subscribe/publish)
core.registry          # PluginRegistry (capabilities)
core.runtime.run(task="...")            # Agente genérico -> AgentState
core.workflow.run(request="...")        # Code Agent -> WorkflowState
core.workflow.arun(request="...")       # variante async
core.shutdown()                         # desativa plugins (ordem reversa)
```

Para entender a arquitetura e como escrever um plugin externo, veja o
[`README.md`](../README.md). Para um provider de LLM, veja
[`creating-an-llm-plugin.md`](creating-an-llm-plugin.md); para tools, validators,
analyzers, discoverers e nós, veja
[`creating-plugins.md`](creating-plugins.md).
