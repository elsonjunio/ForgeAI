# ForgeAI

**ForgeAI** é um monorepo para construir **Code Agents** extensíveis em Python. O
núcleo é o pacote **`core-agent`**, que é **provedor-neutro**: não conhece nenhum
LLM provider, não implementa filesystem/Git/shell/MCP e não contém nenhuma
ferramenta concreta. Tudo isso é contribuído incrementalmente por *plugins*. Com
**zero plugins instalados** o framework continua construído e executável.

Repositório: <https://github.com/elsonjunio/ForgeAI> · Licença: MIT.

> Guia de integração em entrypoints (CLI, automação, jobs): [`docs/using-the-core.md`](docs/using-the-core.md).
> Guia para criar um plugin de LLM: [`docs/creating-an-llm-plugin.md`](docs/creating-an-llm-plugin.md).
> Guia para criar os demais plugins (tools, validators, analyzers, discoverers, nós): [`docs/creating-plugins.md`](docs/creating-plugins.md).

## Monorepo

Este repositório é um monorepo: cada projeto é um pacote Python independente.

```
packages/core/            core-agent   (contratos + runtime + orquestração)
packages/plugins/<plugin> plugins      (ex.: code-agent-plugin-openai, ...)
apps/cli/                 aplicação de linha de comando (entrypoint)
docs/                     guias
scripts/build_packages.py empacotamento (wheel + sdist -> zip)
pyproject.toml            tooling compartilhado (ruff/mypy/pytest), não é pacote
```

- **Dependência:** `plugin → core-agent` e `app → core-agent` (+ plugins que o app
  embarcar). O core nunca depende de plugin.
- **Descoberta:** plugins instalados no mesmo ambiente são encontrados por entry
  point (grupo `core_agent.plugins`); `build_core()` cuida disso.
- **Distribuição:** sem PyPI. O release gera um **zip por pacote** (wheel + sdist)
  e anexa aos artifacts/release.

## Fundamentos

- **Python moderno** — anotações de tipos (3.10+), `dataclass`, `TypedDict`,
  perfil `strict` no mypy, lint com `ruff`.
- **Pydantic v2** para modelos de domínio e configuração.
- **LangChain / LangGraph** como dependências do core — o `AgentRuntime`
  encapsula o `StateGraph`; o restante do código nunca vê o grafo.

## Camadas

Princípio central:

```
CORE   = contratos + runtime + orquestração
PLUGIN = capacidades (LLM, tools, validators, analyzers, discoverers)
```

```
                     +------------------------------+
                     |   core (API pública estável) |
                     +------------------------------+
                                  |
        +-------------+-----------+-----------+
        |                         |           |
   Domain                  Runtime          Infra
   (contratos,            (execução,        (config loading,
    modelos puros)         orquestração)     composition root)
```

**Regra de dependência:** `core.agent.*` e `core.runtime.*` dependem de
`core.contracts` — e **nunca** de plugins concretos. A orquestração resolve
capacidades via `CapabilitySource` (interface); `PluginRegistry` é uma
implementação dela. Qualquer pacote externo que forneça `LLMProvider`, `Tool`,
`Validator` ou `Discoverer` é aceito sem alterar o core.

| Camada | Pacotes | Responsabilidade |
|---|---|---|
| **Domínio** | `core.contracts`, `core.agent.state`, `core.events.event`, `core.config.schema` | Modelos puros e contratos (Pydantic), sem I/O e sem LangGraph. |
| **Runtime** | `core.agent.runtime`, `core.agent.graph`, `core.plugins`, `core.events.bus` | Orquestração. `AgentRuntime`/`GraphBuilder`/`PlanExecutor` encapsulam LangGraph; `PluginRegistry` administra ciclo de vida, capabilities e grupos. |
| **Infraestrutura** | `core.config.loader`, `core.runtime` | Carregamento de configuração (dict/JSON) e composition root (`build_core`). |

### Estrutura

```
packages/core/src/core/
  agent/        AgentState, Message, AgentRuntime; GraphBuilder, PlanExecutor
                (runtime.py e graph.py são as únicas importações de LangGraph)
  contracts/    Capability, CapabilityDescriptor, CapabilitySource, Group,
                LLMProvider, Tool, CodeAnalyzer, Validator, Discoverer, Planner,
                ComplexityEvaluator, ExecutionPlan/PlanNode/PlanEdge,
                ExecutionContext, NodeResult, ExecutionControl, callbacks,
                InteractionProvider, PluginMetadata, NodeContract, NodeContribution
  plugins/      Plugin, PluginContext, PluginRegistry, EntryPointDiscoverer
  events/       Event, EventBus, CoreEvents, EventHandler
  config/       CoreConfig, LangGraphOptions, PluginSlot
  runtime/      build_core, CoreContainer  (composition root)
packages/core/tests/    testes (inclui tests/integration com plugin externo)
```

## Componentes centrais

1. **`AgentState`** — o único objeto que flui pelo grafo. Modelo Pydantic puro:
   `task`, `system_prompt`, `messages`, `output`, `status`, `metadata`,
   `updated_at`. Campos desconhecidos são rejeitados; dados livres vão em
   `metadata`.

2. **`AgentRuntime`** — encapsula o `StateGraph` do LangGraph. Consome
   contribuições de nós (`NodeContribution`) e as envolve como nós do grafo com
   estrutura `init → n1 → … → nn → END`. Expõe `run()` e `arun()`. Com zero
   contribuições o grafo se reduz à inicialização do estado.

3. **`Plugin`** — base de extensão. Ciclo de vida
   (`load` → `initialize` → `shutdown`; `initialize`/`shutdown` delegam para
   `activate`/`deactivate` por compatibilidade) e contribuições
   (`declare_capabilities`, `declare_tools`, `declare_nodes`,
   `event_handlers`). Identidade/versão/metadata via `PluginMetadata`. O
   contrato default é vazio — um plugin sem nenhuma contribuição funciona.

4. **`PluginContext`** — os serviços que um plugin recebe: sua fatia de
   configuração (`config`, `settings`, `get_setting`) e interação com eventos
   (`publish`, `subscribe`).

5. **`PluginRegistry`** — registro, validação (id não vazio e único) e ciclo de
   vida (`activate_all`, `deactivate_all`, ordem reversa no shutdown). Coleta
   as contribuições (`collect_nodes`, `collect_tools`).

6. **Configuração** — `CoreConfig` (app, ambiente, slots por plugin,
   opções do grafo). Carregável de `None`, mapping ou arquivo JSON via
   `load_config`. Slots de plugins não listados ficam habilitados por padrão,
   mantendo o cenário zero-configuração funcional.

7. **Eventos** — `Event` (Pydantic, genérico, tipado por string em `type`) e
   `EventBus` síncrono in-process com inscrição/desinscrição. O core emite
   `agent.started`, `agent.finished`, `agent.node.started`,
   `agent.node.finished`, `plugin.activated`, `plugin.deactivated`.

8. **Capabilities e execução** — contratos puros (`Capability` + `LLMProvider`,
   `Tool`, `CodeAnalyzer`, `Validator`, `Discoverer`, `Planner`) e modelos de
   execução/planejamento (`CapabilityDescriptor`, `ExecutionPlan`, `PlanNode`,
   `PlanEdge`, `ExecutionContext`, `NodeResult`, `ExecutionControl`, callbacks,
   `InteractionProvider`), implementados/produzidos por plugins. O
   `PluginRegistry` registra e consulta providers e resolve o provider default
   sem conhecer nenhuma implementação. Ver a seção *Capabilities e descoberta
   dinâmica*.

9. **Grupos e planners** — `Group` (many-to-many declarativo) e `Planner`
   (`kind="planner"`, global ou especializado por grupo). O core só descobre,
   registra e agrupa; a composição é do host/plugin. Ver *Grupos, planners e
   escopos*.

10. **Execução dinâmica** — `GraphBuilder`/`PlanExecutor` transformam um
    `ExecutionPlan` (produzido por um `Planner` plugin) em um grafo LangGraph
    executável, resolvendo capabilities pelo registry. Sem pipeline fixa e sem
    ReAct loop no core. Ver *Execução dinâmica*.

## Uso mínimo (zero plugins)

```python
from core import build_core

container = build_core()
final = container.runtime.run(task="refatore este arquivo")
print(final.status)   # completed
print(final.output)   # None  (nenhum plugin contribuiu ainda)
container.shutdown()
```

## Escrevendo um plugin

```python
from core import AgentState, NodeContract, NodeContribution, Plugin, ToolContract


class MeuPlugin(Plugin):
    id = "meu-plugin"
    version = "0.1.0"

    def declare_tools(self) -> list[ToolContract]:
        return [ToolContract(name="rm", description="Remove um arquivo.", parameters={...})]

    def declare_nodes(self) -> list[NodeContribution]:
        def node(state: AgentState) -> AgentState:
            return state.model_copy(update={"output": state.task.upper()})

        return [NodeContribution(contract=NodeContract(id="uppercase"), node=node)]

    def event_handlers(self) -> dict[str, EventHandler]:
        return {"agent.started": self._on_started}

    def _on_started(self, event: Event) -> None:
        print("runa iniciada com a tarefa:", event.payload)
```

```python
from core import CoreConfig, build_core

config = CoreConfig.model_validate({"plugins": {"meu-plugin": {"settings": {"dry_run": True}}}})
container = build_core(config=config, plugins=[MeuPlugin()])
```

Plugins desabilitados (slot `enabled: false`) são simplesmente ignorados.

## Capabilities e descoberta dinâmica

O core define contratos de capability que plugins implementam — nenhum deles vem
com implementação:

| Contrato | `kind` | Papel |
|---|---|---|
| `LLMProvider` | `llm` | backend de LLM (`complete` → `LLMResponse`, com `on_chunk` opcional) |
| `Tool` | `tool` | ferramenta executável (`contract` + `invoke`) |
| `CodeAnalyzer` | `analyzer` | análise de código (`analyze`) |
| `Validator` | `validator` | validação pós-execução (`validate`) |
| `Discoverer` | `discoverer` | descoberta de plugins (`discover`) |
| `Planner` | `planner` | produz um `ExecutionPlan` a partir de `PlanningRequest` |

Além das capabilities, o core define modelos de execução/planejamento
(`CapabilityDescriptor`, `ExecutionPlan`/`PlanNode`/`PlanEdge`,
`ExecutionContext`, `NodeResult`, `ExecutionControl`) e contratos de
observabilidade/interação (callbacks, `InteractionProvider`) — todos puros, sem
implementação.

Um plugin declara providers por `declare_capabilities()` ou, dinamicamente, por
`context.register_capability(...)` durante `initialize`:

```python
from core import LLMProvider, Plugin


class MeuProvider(LLMProvider):
    default = True  # selecionado como default do kind "llm"

    @property
    def name(self) -> str:
        return "meu-llm"

    def complete(self, messages, **options):
        ...


class MeuPlugin(Plugin):
    id = "meu-plugin"

    def declare_capabilities(self):
        return [MeuProvider()]
```

O `PluginRegistry` consulta por tipo de contrato ou por `kind`:
`capabilities(LLMProvider)`, `capability("llm", "meu-llm")`,
`has_capability("llm")`, `capability_names(LLMProvider)` e
`default_capability(LLMProvider)`.

Provider default, sem acoplar o core a implementações, em ordem:
`CoreConfig.defaults` (`{"llm": "meu-llm"}`, aceita o `kind` ou o nome da
classe) → `default = True` → único provider registrado; caso contrário
`AmbiguousCapabilityError`. Zero providers retorna `None`.

### Ciclo de vida

`register()` chama `load()`; `activate_all()` chama `initialize(context)` e
registra as capabilities; `deactivate_all()` chama `shutdown()` na ordem
reversa. Por compatibilidade, `initialize` delega para `activate` e `shutdown`
para `deactivate`.

### Descoberta

`build_core()` descobre plugins instalados via entry points do grupo
`core_agent.plugins` por padrão. Para declarar um plugin instalável:

```toml
[project.entry-points."core_agent.plugins"]
meu-plugin = "meu_pacote:MeuPlugin"
```

O entry point pode resolver para uma instância, uma subclasse de `Plugin` ou uma
factory sem argumentos. Passe `discoverers=[]` para desligar a descoberta, ou
outro `Discoverer` para usar um mecanismo alternativo:

```python
core = build_core(discoverers=[MeuDiscoverer()])
```

## Grupos, planners e escopos

**Grupos** são áreas de domínio declarativas e many-to-many. Capabilities e
plugins referenciam grupos por id; um item pode estar em vários grupos.

```python
from core import Capability, Group, Plugin


class GitCommit(Capability):
    kind = "tool"
    groups = ("code", "version-control")
    ...


class GitPlugin(Plugin):
    id = "code-agent-plugin-git"
    groups = ("project",)                     # grupo explícito do plugin

    def declare_groups(self):
        return [Group(id="version-control", name="Version Control")]

    def declare_capabilities(self):
        return [GitCommit()]
```

Consultas no registry: `groups()`, `group(id)`, `group_ids()`,
`capabilities_in_group(id)`, `capability_descriptors_in_group(id)`,
`plugin_ids_in_group(id)`, `plugin_groups(plugin_id)`. Dois plugins declarando o
mesmo `group.id` levantam `DuplicateGroupError`.

**Planners** são capabilities (`kind="planner"`). Sem grupos = global; com grupos
= especializado. O core **só descobre, registra e agrupa**:

```python
from core import ExecutionContext, Planner, PlanningRequest, PlanningResult


class CodePlanner(Planner):
    groups = ("code",)

    @property
    def name(self) -> str:
        return "code-planner"

    def plan(self, request: PlanningRequest) -> PlanningResult:
        ...   # devolve um ExecutionPlan; não conhece LangGraph
```

```python
registry.planners()                      # todos os planners
registry.planners(group="code")          # só os do grupo "code"
registry.planner_descriptors(group="code")
```

O planner global recebe os **descriptors** dos especializados em
`PlanningRequest.planners`; compor (main → grupo) é responsabilidade do
host/plugin. O planner **não executa capabilities**: ele devolve um
`ExecutionPlan`, e o `PlanExecutor` executa.

**ComplexityEvaluator** (`kind="complexity"`) é só contrato: permite à
aplicação/planner decidir entre execução direta, plano simples, grafo complexo ou
estratégia iterativa — sem heurística no core.

**InteractionProvider** (fornecido pelo host, nunca uma capability) chega aos
plugins por `PluginContext.interaction` e às capabilities em execução por
`NodeExecutionRequest.interaction`:

```python
core = build_core(interaction=meu_provider)
```

## Execução dinâmica (ExecutionPlan → LangGraph)

O núcleo também executa **planos** produzidos por plugins, sem pipeline fixa:

```
Request → Planner (plugin) → ExecutionPlan → GraphBuilder → LangGraph → PlanExecutor → ExecutionResult
```

- `Planner` (capability `kind="planner"`) produz um `ExecutionPlan` e **não
  conhece LangGraph**.
- `container.executor` (um `PlanExecutor`) valida o plano, monta o grafo e executa.
- Cada `PlanNode` referencia uma capability por id `"<kind>:<name>"`, resolvida
  pelo registry. A execução usa o protocolo `Executable`
  (`execute(request) -> NodeResult`) ou o adaptador de `Tool` (`invoke`).
- O grafo é **dinâmico**: as arestas do plano viram edges; nós sem entrada ligam
  ao `START` e sem saída ao `END`. Planos diferentes geram grafos diferentes.
- `ExecutionContext` é o contexto conceitual (request, `AgentState`, metadata,
  capabilities e histórico fornecido pelo host) e não depende de LangGraph.

```python
from core import ExecutionContext, ExecutionPlan, PlanNode, build_core

core = build_core()
plan = ExecutionPlan(
    id="p1",
    nodes=(PlanNode(id="step", capability="tool:meu-tool"),),
)
result = core.executor.run(plan, ExecutionContext(request="fazer algo"))
print(result.status, result.results)   # completed { 'step': NodeResult(...) }
core.shutdown()
```

**Validação antes de executar**: ids únicos, edges válidas, nodes com capability,
capabilities disponíveis e executáveis (`InvalidPlanError`,
`MissingCapabilityError`, `UnsupportedCapabilityError`). Erros de uma capability
durante a execução viram `NodeResult.failed` observável.

**Callbacks (opcionais)**: um `ExecutionObserver` recebe eventos
(`execution_start`, `node_start`, `node_complete`, `execution_complete`, `error`,
`capability_*`, ...) e um `ControlCallback` pode solicitar
`CONTINUE`/`PAUSE`/`INTERRUPT`/`RETRY` após cada node. `PAUSE`/`INTERRUPT` param a
execução; **não há checkpoint persistente** ainda (a limitação é documentada, não
simulada).

## Como criar um plugin externo

Um plugin é um pacote Python normal que importa **apenas a API pública** de
`core`. Ele não modifica o core e é descoberto por entry point (grupo
`core_agent.plugins`). Exemplo de um provider de LLM:

```python
# meu_pacote/plugin.py
from collections.abc import Sequence
from typing import Any

from core import LLMProvider, LLMResponse, Message, Plugin


class MeuLLM(LLMProvider):
    default = True                      # vira o provider default do kind "llm"

    @property
    def name(self) -> str:              # único dentro do kind
        return "meu-llm"

    def complete(self, messages: Sequence[Message], **options: Any) -> LLMResponse:
        ...                             # chame seu backend e devolva LLMResponse(message=...)


class MeuPlugin(Plugin):
    id = "code-agent-plugin-meu"
    version = "1.0.0"

    def declare_capabilities(self):
        return [MeuLLM()]
```

Registre o entry point no `pyproject.toml` do seu pacote:

```toml
[project.entry-points."core_agent.plugins"]
code-agent-plugin-meu = "meu_pacote.plugin:MeuPlugin"
```

Instalado (`pip install -e .`), o plugin é descoberto automaticamente:

```python
from core import ExecutionContext, ExecutionPlan, PlanNode, build_core

core = build_core()                    # descobre por entry points
plan = ExecutionPlan(id="p", nodes=(PlanNode(id="n", capability="tool:meu-tool"),))
core.executor.run(plan, ExecutionContext(request="..."))
core.shutdown()
```

Regras a respeitar:

- **Importe só a API pública** (`from core import ...`); nunca importe
  `langgraph`/`langchain_core` nem módulos internos.
- **Não conheça outros plugins**: receba os serviços pelo registry/contexto.
- **Forneça capacidades, não fluxo**: `LLMProvider`, `Tool`, `Validator`,
  `Discoverer`, `CodeAnalyzer` (ou um subtipo próprio de `Capability`).
- **Identidade única**: `Plugin.id` e cada `(kind, name)` de capability.
- Desative com `CoreConfig.plugins[<id>].enabled = false`.
- Default de provider: flag `default = True`, ou `CoreConfig.defaults`
  (`{"llm": "meu-llm"}`), ou provider único.

Um exemplo executável está em `packages/core/tests/integration/fake_plugin/` (usa
somente a API pública) e é exercitado por
`packages/core/tests/integration/test_external_plugin.py`, inclusive via
descoberta por entry point.

## Desenvolvimento

A partir da raiz do repositório:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e "packages/core[dev]"
```

```bash
pytest          # executa a suíte de testes (config na raiz)
ruff check .    # lint
mypy            # type checking (strict)
```

### Release (zips, sem PyPI)

```bash
pip install build
python scripts/build_packages.py --tag v0.1.0
# gera dist/<pacote>-v0.1.0.zip (wheel + sdist de cada pacote)
```

O workflow `.github/workflows/release.yml` faz o mesmo em CI: dispara em tag `v*`
ou manualmente (`workflow_dispatch`) e anexa os zips aos artifacts/release. O
workflow de CI (`ci.yml`) roda lint, type checking e testes em Python 3.10–3.12.

## Escopo atual vs. próximo passo

Este pacote é a **fundação**: contratos, ciclo de vida, eventos, configuração e
o runtime encapsulando LangGraph. O *fluxo completo* do Code Agent (loop de
agente com LLM, seleção/execução de ferramentas, memória, etc.) **não está
implementado**; ele será construído sobre estes contratos, contribuído por
plugins e orquestrado pelo `AgentRuntime` — sem expor LangGraph aos plugins.