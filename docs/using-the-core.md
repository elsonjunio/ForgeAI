# Usando o core em um entrypoint

Este guia mostra como embutir o `core-agent` em um ponto de entrada — um CLI de
terminal, um script de automação, um job de CI ou qualquer ferramenta que rode
Python. O core é uma **biblioteca**: ele não traz CLI, servidor, planner nem LLM;
você fornece o entrypoint, os plugins e o host services (histórico, interação).

> Requisitos: Python 3.10+. Instale o core com `pip install -e "packages/core"`
> (a partir da raiz do monorepo) ou como dependência `core-agent`.

## O que o entrypoint precisa fazer

1. **Montar** o core com `build_core(...)` (config, plugins, `interaction`).
2. **Planejar** com um `Planner` plugin → `ExecutionPlan`.
3. **Executar** o plano com `container.executor` (`ExecutionPlan` → LangGraph).
4. **Observar** eventos/callbacks e tratar `CoreError`.
5. **Encerrar** com `container.shutdown()`.

`build_core` devolve um `CoreContainer` com: `config`, `events`, `registry`,
`runtime` (grafo genérico de nós contribuídos por plugins) e `executor`
(execução dinâmica de planos).

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

O core sempre monta com zero plugins. Sem plugins não há planner nem
capabilities, então a execução de planos não tem o que resolver.

## Execução dinâmica (ExecutionPlan → LangGraph)

```
Request → Planner (plugin) → ExecutionPlan → GraphBuilder → LangGraph → PlanExecutor → ExecutionResult
```

- `Planner` (`kind="planner"`) produz um `ExecutionPlan` e **não conhece
  LangGraph**.
- `container.executor` valida o plano, monta o grafo e executa.
- Cada `PlanNode` referencia uma capability por id `"<kind>:<name>"`, resolvida
  pelo registry. A execução usa o protocolo `Executable`
  (`execute(request) -> NodeResult`) ou o adaptador de `Tool` (`invoke`).

```python
from core import ExecutionContext, ExecutionPlan, PlanNode, build_core

core = build_core()
try:
    plan = ExecutionPlan(
        id="p1",
        nodes=(PlanNode(id="step", capability="tool:meu-tool"),),
    )
    result = core.executor.run(plan, ExecutionContext(request="fazer algo"))
    print(result.status, result.results)   # completed { 'step': NodeResult(...) }
finally:
    core.shutdown()
```

Encadeando planejamento e execução:

```python
from core import ExecutionContext, Planner, PlanningRequest, build_core

core = build_core()
try:
    planner = core.registry.default_capability(Planner)
    if planner is None:
        raise RuntimeError("nenhum planner registrado")

    context = ExecutionContext(request="refatore o módulo de pagamento")
    planning = PlanningRequest(
        request="refatore o módulo de pagamento",
        context=context,
        planners=tuple(core.registry.planner_descriptors()),
    )
    plan = planner.plan(planning).plan
    result = core.executor.run(plan, context)
    print(result.status)
finally:
    core.shutdown()
```

**Validação antes de executar**: ids únicos, edges válidas, nodes com capability,
capabilities disponíveis e executáveis (`InvalidPlanError`,
`MissingCapabilityError`, `UnsupportedCapabilityError`). Erros de uma capability
durante a execução viram `NodeResult.failed` observável.

## Grupos e planners

**Grupos** são áreas de domínio declarativas e many-to-many (uma capability/plugin
pode estar em vários). **Planners** sem grupos são globais; com grupos são
especializados. O core só descobre/registra/agrupa:

```python
core.registry.groups()                       # grupos declarados
core.registry.capabilities_in_group("code")  # capabilities do grupo
core.registry.plugin_ids_in_group("code")    # plugins do grupo
core.registry.planners()                     # todos os planners
core.registry.planners(group="code")         # planners do grupo
core.registry.planner_descriptors(group="code")
```

O planner global recebe os **descriptors** dos especializados em
`PlanningRequest.planners`; compor (main → grupo) é responsabilidade do
host/plugin. O planner nunca executa capabilities — ele devolve um
`ExecutionPlan`.

## Configurando o core

`CoreConfig` é um modelo Pydantic; `load_config` aceita mapping ou arquivo JSON:

```python
from core import build_core, load_config

config = load_config("agent.json")   # ou load_config({...})
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
  "langgraph": { "recursion_limit": 25 }
}
```

| Campo | Efeito |
|---|---|
| `plugins.<id>.enabled` | `false` faz o plugin nem ser registrado. |
| `plugins.<id>.settings` | Fica disponível ao plugin em `context.settings`. |
| `defaults` | Provider default por `kind` (`{"llm": "openai"}`) ou nome da classe. |
| `langgraph.recursion_limit` | Orçamento de recursão do grafo genérico. |

## Interação com o host

`InteractionProvider` é fornecido pelo host (nunca é uma capability) e permite a
plugins/capabilities pedir confirmação, informação ou autorização:

```python
from core import InteractionRequest, InteractionResponse, build_core


class TerminalInteraction:
    def request(self, request: InteractionRequest) -> InteractionResponse:
        answer = input(f"{request.message} ")
        return InteractionResponse(value=answer)


core = build_core(interaction=TerminalInteraction())
```

Plugins acessam via `PluginContext.interaction`; capabilities em execução via
`NodeExecutionRequest.interaction`.

## Observabilidade (eventos e callbacks)

```python
from core import ExecutionEvent, ExecutionEventKind, build_core


class LoggingObserver:
    def on_event(self, event: ExecutionEvent) -> None:
        print(f"[{event.kind.value}] node={event.node_id}")


core = build_core()
executor = core.executor  # o executor criado por build_core não tem observer
```

Para observar/controlar, construa um executor próprio com callbacks:

```python
from core import ExecutionContext, PlanExecutor, build_core

core = build_core()
executor = PlanExecutor(registry=core.registry, observer=LoggingObserver())
result = executor.run(plan, ExecutionContext(request="..."))
```

Um `ControlCallback` pode solicitar `CONTINUE`/`PAUSE`/`INTERRUPT`/`RETRY` após
cada node:

```python
from core import ControlAction, ExecutionContext, ExecutionControl, NodeResult


class StopOnFailure:
    def on_node_complete(
        self, context: ExecutionContext, result: NodeResult
    ) -> ExecutionControl | None:
        if result.success:
            return None
        return ExecutionControl(action=ControlAction.INTERRUPT, reason="falhou")
```

`PAUSE`/`INTERRUPT` param a execução; **não há checkpoint persistente** ainda (a
limitação é documentada, não simulada). O runtime genérico emite
`CoreEvents.AGENT_STARTED`/`AGENT_FINISHED` e `AGENT_NODE_STARTED`/`FINISHED`.

## Exemplo completo: CLI de terminal

`meu_agente/cli.py`:

```python
"""CLI mínimo sobre o core-agent (planejamento + execução)."""

from __future__ import annotations

import argparse
import sys

from core import CoreConfig, CoreError, Planner, PlanningRequest, ExecutionContext, build_core, load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meu-code-agent")
    parser.add_argument("request", nargs="?")
    parser.add_argument("--config", metavar="ARQ")
    args = parser.parse_args(argv)
    if not args.request:
        print("erro: informe um pedido", file=sys.stderr)
        return 2

    config = load_config(args.config) if args.config else CoreConfig()
    core = build_core(config=config)
    try:
        planner = core.registry.default_capability(Planner)
        if planner is None:
            print("erro: nenhum planner registrado", file=sys.stderr)
            return 1
        context = ExecutionContext(request=args.request)
        planning = PlanningRequest(
            request=args.request,
            context=context,
            planners=tuple(core.registry.planner_descriptors()),
        )
        plan = planner.plan(planning).plan
        result = core.executor.run(plan, context)
    except CoreError as exc:
        print(f"erro ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
    finally:
        core.shutdown()

    for node_id, node_result in result.results.items():
        print(f"- {node_id}: {'ok' if node_result.success else node_result.error}")
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

No `pyproject.toml` **da sua aplicação** (não do core):

```toml
[project.scripts]
meu-code-agent = "meu_agente.cli:main"
```

## Usando em outra ferramenta de automação

O core é apenas uma biblioteca; exponha uma função para o seu orquestrador:

```python
from core import CoreError, ExecutionContext, Planner, PlanningRequest, build_core


def run_agent(request: str, config=None) -> dict:
    core = build_core(config=config)
    try:
        planner = core.registry.default_capability(Planner)
        if planner is None:
            return {"ok": False, "error": "MissingPlanner"}
        context = ExecutionContext(request=request)
        planning = PlanningRequest(
            request=request,
            context=context,
            planners=tuple(core.registry.planner_descriptors()),
        )
        plan = planner.plan(planning).plan
        result = core.executor.run(plan, context)
    except CoreError as exc:
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}
    finally:
        core.shutdown()

    return {
        "ok": result.status == "completed",
        "status": result.status,
        "nodes": {nid: r.success for nid, r in result.results.items()},
    }
```

## Tratamento de erros

Capture `CoreError` no entrypoint; os subtipos dão contexto:

| Exceção | Quando ocorre |
|---|---|
| `MissingCapabilityError` | Um node referencia capability inexistente (ou nenhum provider exigido). |
| `UnsupportedCapabilityError` | A capability existe mas não é executável como node. |
| `InvalidPlanError` | Plano inválido (ids duplicados, edges soltas, self-loop, node sem capability). |
| `GraphBuildError` | Falha ao compilar o grafo. |
| `AmbiguousCapabilityError` | Vários providers e nenhum default selecionado. |
| `DuplicateCapabilityError` / `DuplicateGroupError` | Conflito de capability/grupo. |
| `DuplicatePluginError` / `InvalidPluginError` | Plugin duplicado ou inválido. |
| `DiscoveryError` | Falha ao carregar um entry point de plugin. |
| `ConfigError` | Configuração ausente/inválida. |
| `InvalidGraphError` | Nós contribuídos não formam um grafo válido. |

## Executando sem descoberta automática

Útil em CI e ambientes herméticos:

```python
core = build_core(
    config=load_config("agent.json"),
    plugins=[MeuPlugin()],
    discoverers=[],   # nenhum entry point é consultado
)
```

## Boas práticas

- Sempre `try/finally` com `core.shutdown()` para liberar recursos dos plugins.
- Não importe `langgraph`/`langchain_core` no seu entrypoint; use só a API
  pública de `core`.
- O histórico de conversa é responsabilidade do host: monte
  `ExecutionContext.history` explicitamente; o core nunca busca histórico.
- Para CLIs, retorne código de saída coerente (`0` sucesso, `1` falha, `2` uso
  incorreto).

## Referência rápida

```python
from core import (
    build_core, load_config, CoreConfig, CoreError,
    Planner, PlanningRequest, ExecutionPlan, PlanNode,
    ExecutionContext, PlanExecutor, InteractionProvider,
    CoreEvents, ExecutionEventKind,
)

core.config        # CoreConfig resolvido
core.events        # EventBus (subscribe/publish)
core.registry      # PluginRegistry (capabilities, groups, planners)
core.runtime.run(task="...")             # grafo genérico -> AgentState
core.executor.run(plan, context)         # plano -> ExecutionResult
core.shutdown()                          # desativa plugins (ordem reversa)
```

Para entender a arquitetura e como escrever um plugin externo, veja o
[`README.md`](../README.md). Para um provider de LLM, veja
[`creating-an-llm-plugin.md`](creating-an-llm-plugin.md); para tools, validators,
analyzers, discoverers, planners e nós, veja
[`creating-plugins.md`](creating-plugins.md).
