# core-agent

`core-agent` é o núcleo de um framework extensível para **Code Agents** em Python.

O núcleo é **provedor-neutro**: não conhece nenhum LLM provider, não implementa
filesystem/Git/shell/MCP e não contém nenhuma ferramenta concreta. Tudo isso é
contribuído incrementalmente por *plugins*. Com **zero plugins instalados** o
framework continua construído e executável.

## Fundamentos

- **Python moderno** — anotações de tipos (3.10+), `dataclass`, `TypedDict`,
  perfil `strict` no mypy, lint com `ruff`.
- **Pydantic v2** para modelos de domínio e configuração.
- **LangChain / LangGraph** como dependências do core — o `AgentRuntime`
  encapsula o `StateGraph`; o restante do código nunca vê o grafo.

## Camadas

```
                     +------------------------------+
                     |   core (API pública estável) |
                     +------------------------------+
                                  |
        +-------------+-----------+-----------+
        |                         |           |
   Domain                  Runtime          Infra
   (contratos,            (execução,        (config loading,
    modelos puros)         extensão)         composition root)
```

| Camada | Pacotes | Responsabilidade |
|---|---|---|
| **Domínio** | `core.contracts`, `core.agent.state`, `core.events.event`, `core.config.schema` | Modelos puros e contratos (Pydantic), sem I/O e sem LangGraph. |
| **Runtime** | `core.agent.runtime`, `core.plugins`, `core.events.bus` | Orquestração. `AgentRuntime` encapsula LangGraph; `PluginRegistry` administra o ciclo de vida dos plugins. |
| **Infraestrutura** | `core.config.loader`, `core.runtime` | Carregamento de configuração (dict/JSON) e composition root (`build_core`). |

### Estrutura

```
src/core/
  agent/        AgentState, Message, AgentRuntime (única importação de LangGraph)
  contracts/    Capability, LLMProvider, Tool, CodeAnalyzer, Discoverer,
                ToolContract, NodeContract, NodeContribution, AgentNode
  plugins/      Plugin, PluginMetadata, PluginContext, PluginRegistry,
                EntryPointDiscoverer
  events/       Event, EventBus, CoreEvents, EventHandler
  config/       CoreConfig, LangGraphOptions, PluginSlot, load_config
  runtime/      build_core, CoreContainer  (composition root)
tests/          testes unitários (há plugins stub apenas para os testes)
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

3. **`Plugin`** — ABC de extensão. Hooks de ciclo de vida
   (`activate`/`deactivate`) e de contribuição (`declare_tools`,
   `declare_nodes`, `event_handlers`). O contrato default é vazio — um plugin
   sem nenhuma contribuição funciona.

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

8. **Capabilities** — contratos puros (`Capability` + `LLMProvider`, `Tool`,
   `CodeAnalyzer`, `Discoverer`) implementados por plugins. O `PluginRegistry`
   registra e consulta providers e resolve o provider default sem conhecer
   nenhuma implementação. Ver a seção *Capabilities e descoberta dinâmica*.

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
| `LLMProvider` | `llm` | backend de LLM (`complete`) |
| `Tool` | `tool` | ferramenta executável (`contract` + `invoke`) |
| `CodeAnalyzer` | `analyzer` | análise de código (`analyze`) |
| `Discoverer` | `discoverer` | descoberta de plugins (`discover`) |

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

## Desenvolvimento

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

```bash
pytest              # executa a suíte de testes
ruff check src tests   # lint
mypy src tests         # type checking (strict)
```

## Escopo atual vs. próximo passo

Este pacote é a **fundação**: contratos, ciclo de vida, eventos, configuração e
o runtime encapsulando LangGraph. O *fluxo completo* do Code Agent (loop de
agente com LLM, seleção/execução de ferramentas, memória, etc.) **não está
implementado**; ele será construído sobre estes contratos, contribuído por
plugins e orquestrado pelo `AgentRuntime` — sem expor LangGraph aos plugins.