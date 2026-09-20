# Criando plugins: tools, validators, analyzers, discoverers e nós

Este guia cobre os **outros tipos de plugin** além do provider de LLM. O
provider de LLM tem um guia próprio
([`creating-an-llm-plugin.md`](creating-an-llm-plugin.md)); aqui estão as demais
capacidades e extensões.

Relembrando o princípio: **CORE = contratos + runtime + orquestração**;
**PLUGIN = capacidades**. Tudo que é específico (uma ferramenta, uma regra de
validação, um analisador, uma fonte de plugins) vive no seu pacote.

## Como o core usa cada tipo

| Tipo | `kind` | Registro | O que o core faz |
|---|---|---|---|
| `Tool` | `tool` | `declare_capabilities` | A etapa `execution` lista os nomes no prompt; disponível via registry. *Tool-calling real ainda não está no workflow base.* |
| `Validator` | `validator` | `declare_capabilities` | A etapa `validation` executa **todos**; todos precisam passar. Sem validators, nada a validar. |
| `CodeAnalyzer` | `analyzer` | `declare_capabilities` | O workflow base **não** chama analyzers; ficam disponíveis para plugins/consumidores. |
| `Discoverer` | `discoverer` | `declare_capabilities` | A etapa `discovery` chama `discover()`. Também pode ser usado como mecanismo em `build_core(discoverers=...)`. |
| `NodeContribution` | — | `declare_nodes` | Alimenta o **runtime genérico** (`container.runtime`), não o workflow. |
| Event handler | — | `event_handlers` | Assinado na ativação, removido no shutdown. |

## Esqueleto comum

Todo plugin é uma subclasse de `Plugin` com identidade/versão e um ou mais hooks
de contribuição. O empacotamento (entry point `core_agent.plugins`), settings e
ciclo de vida são iguais aos do guia de LLM — não vou repetir aqui.

```python
from core import Capability, EventHandler, NodeContribution, Plugin


class MeuPlugin(Plugin):
    id = "code-agent-plugin-meu"
    version = "0.1.0"
    description = "Contribui uma ferramenta e um validador."

    def declare_capabilities(self) -> list[Capability]:
        return [MinhaTool(), MeuValidator()]

    def declare_nodes(self) -> list[NodeContribution]:
        return []

    def event_handlers(self) -> dict[str, EventHandler]:
        return {}
```

Registre capacidades de duas formas:

- **declarativa** — `declare_capabilities()` (preferida);
- **dinâmica** — `context.register_capability(...)` dentro de `initialize`, quando
  o provider só pode ser construído depois de ler os settings.

## 1. `Tool` — ferramenta executável

Um `Tool` descreve-se com um `ToolContract` (JSON-Schema dos argumentos) e
executa via `invoke`. O `name` vem do contrato.

```python
from collections.abc import Mapping
from typing import Any

from core import Tool, ToolContract, ToolResult


class WordCountTool(Tool):
    @property
    def contract(self) -> ToolContract:
        return ToolContract(
            name="word_count",
            description="Conta palavras em um texto.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        text = str(arguments.get("text", ""))
        words = text.split()
        return ToolResult(output=str(len(words)), metadata={"words": len(words)})
```

- `ToolContract.name` é único dentro do kind `tool` (chave `("tool", "word_count")`).
- `ToolResult(output, is_error=False, metadata={})`: use `is_error=True` para
  falhas de execução sem levantar exceção.
- `parameters` é o JSON-Schema que será oferecido ao modelo quando o tool-calling
  for implementado. Mantenha-o fiel ao que `invoke` espera.

> Estado atual: o workflow base **não invoca** tools — ele informa os nomes
> disponíveis no prompt de `execution`. Um plugin pode invocar tools
> programaticamente via `container.registry.capabilities(Tool)`.

## 2. `Validator` — regra de validação

Validators rodam na etapa `validation`, depois de `execution`. Se **qualquer**
validator reprovar, o workflow não conclui como `completed` (e tenta retry
conforme `workflow.max_attempts`).

```python
from core import ValidationInput, ValidationResult, Validator


class NonEmptyOutputValidator(Validator):
    @property
    def name(self) -> str:
        return "non-empty-output"

    def validate(self, data: ValidationInput) -> ValidationResult:
        if (data.output or "").strip():
            return ValidationResult(passed=True)
        return ValidationResult(passed=False, messages=("output vazio",))
```

- Entrada: `ValidationInput(request, task, output)`.
- Saída: `ValidationResult(passed, messages=(), metadata={})`. `messages` aparece
  em `WorkflowState.validations` e no prompt de `review`.
- Sem validators registrados, a etapa é um no-op (nada a validar).

## 3. `CodeAnalyzer` — análise de código

Analisadores são capacidades reutilizáveis (linters, contagem, índice de
símbolos). O workflow base não os executa; outros plugins/consumidores podem
usar. O padrão comum é expor um analyzer **e** um validator que o consome.

```python
from core import AnalysisResult, CodeAnalyzer


class TodoAnalyzer(CodeAnalyzer):
    @property
    def name(self) -> str:
        return "todo-scan"

    def analyze(self, source: str, *, path: str | None = None) -> AnalysisResult:
        label = path or "<source>"
        findings = tuple(
            f"{label}:{i}: {line.strip()}"
            for i, line in enumerate(source.splitlines(), start=1)
            if "TODO" in line
        )
        return AnalysisResult(findings=findings, metadata={"count": len(findings)})
```

- Entrada: `source` (texto) + `path` opcional. O core não faz I/O; quem lê o
  arquivo é o seu plugin (ex.: um plugin de filesystem).
- Saída: `AnalysisResult(findings=(), metadata={})`.

## 4. `Discoverer` — fonte de plugins

O `Discoverer` tem **dois papéis**:

1. **Mecanismo de descoberta no build** — passado a
   `build_core(discoverers=[...])`; substitui/complementa o
   `EntryPointDiscoverer` padrão.
2. **Capability registrada** — consultada pela etapa `discovery` do workflow.

```python
from collections.abc import Iterable

from core import Discoverer, Plugin


class StaticDiscoverer(Discoverer):
    def __init__(self, plugins: Iterable[Plugin] = ()) -> None:
        self._plugins = list(plugins)

    def discover(self) -> Iterable[Plugin]:
        return list(self._plugins)
```

Uso como capability (a etapa `discovery` grava os metadados em
`state.context.plugins`):

```python
from core import Capability, Plugin


class DiscoveryPlugin(Plugin):
    id = "code-agent-plugin-discovery"

    def declare_capabilities(self) -> list[Capability]:
        return [StaticDiscoverer([OutroPlugin()])]
```

Uso como mecanismo de build:

```python
core = build_core(discoverers=[StaticDiscoverer([MeuPlugin()])])
```

`discover()` pode levantar `DiscoveryError`; a etapa `discovery` captura
`CoreError` e segue com o contexto parcial.

## 5. Nós para o runtime genérico

Além do workflow, o core tem um grafo genérico
(`START → __core_init__ → n1 → … → nn → END`) montado a partir de
`NodeContribution`. Cada nó é uma transformação pura de `AgentState`.

```python
from core import AgentState, NodeContract, NodeContribution, Plugin


class UppercaseNodePlugin(Plugin):
    id = "code-agent-plugin-uppercase"

    def declare_nodes(self) -> list[NodeContribution]:
        def node(state: AgentState) -> AgentState:
            return state.model_copy(update={"output": (state.task or "").upper()})

        return [
            NodeContribution(
                contract=NodeContract(id="uppercase", description="Task em maiúsculas."),
                node=node,
            )
        ]
```

```python
core = build_core(plugins=[UppercaseNodePlugin()])
final = core.runtime.run(task="hello")
assert final.output == "HELLO"
```

Regras:

- `NodeContract.id` é único **globally** (entre todos os plugins); duplicado →
  `InvalidGraphError`.
- Ordem: `NodeContract.after="<id>"` define dependência (ordenação topológica);
  ciclos/inconsistências falham na construção.
- `__core_init__` é reservado.
- `AgentState` usa `extra="forbid"`; dados livres vão em `metadata`.
- O workflow do Code Agent **não** usa esses nós.

## 6. Event handlers — observabilidade

`event_handlers()` assina handlers na ativação e os remove no shutdown. Serve
para logging, métricas e reação a eventos do core.

```python
from typing import Any

from core import Event, EventHandler, Plugin


class LoggingPlugin(Plugin):
    id = "code-agent-plugin-logging"

    def __init__(self) -> None:
        self.seen: list[str] = []

    def event_handlers(self) -> dict[str, EventHandler]:
        return {"workflow.stage.finished": self._on_event}

    def _on_event(self, event: Event[Any]) -> None:
        self.seen.append(event.source)
```

Eventos úteis: `workflow.started`, `workflow.stage.started/finished`,
`workflow.retry`, `workflow.completed`, `workflow.failed`; e `agent.*` /
`plugin.*` do runtime genérico (`CoreEvents`, `WorkflowEvents`).

> Handlers rodam de forma síncrona no fluxo de publicação — não bloqueie.

## 7. Capability customizada (novo `kind`)

Se precisa de um tipo que o core não conhece, crie um subtipo de `Capability`.
Ele é registrado e consultável como qualquer outra capability; o workflow base
ignora kinds desconhecidos, mas plugins e consumidores podem usá-lo.

```python
from abc import abstractmethod

from core import Capability


class Formatter(Capability):
    kind = "formatter"

    @abstractmethod
    def format(self, text: str) -> str: ...


class UpperFormatter(Formatter):
    @property
    def name(self) -> str:
        return "upper"

    def format(self, text: str) -> str:
        return text.upper()
```

```python
core.registry.capabilities(Formatter)        # por tipo
core.registry.capability("formatter", "upper")
```

## 8. Um plugin com várias capacidades

```python
from core import Capability, Plugin


class ToolkitPlugin(Plugin):
    id = "code-agent-plugin-toolkit"
    version = "0.1.0"
    description = "Ferramenta, validador, analyzer, discoverer e formatter."

    def declare_capabilities(self) -> list[Capability]:
        return [
            WordCountTool(),
            NonEmptyOutputValidator(),
            TodoAnalyzer(),
            StaticDiscoverer([UppercaseNodePlugin()]),
            UpperFormatter(),
        ]
```

As chaves `(kind, name)` precisam ser únicas. Dois plugins podem fornecer o
mesmo `kind` com nomes diferentes (ex.: vários validators).

## 9. Testando

Teste cada peça isoladamente e depois via `build_core`:

```python
from core import CodeAnalyzer, ValidationInput, build_core

from code_agent_plugin_toolkit import NonEmptyOutputValidator, ToolkitPlugin, WordCountTool


def test_tool_invoke() -> None:
    assert WordCountTool().invoke({"text": "a b c"}).output == "3"


def test_validator() -> None:
    validator = NonEmptyOutputValidator()
    assert validator.validate(ValidationInput(request="r", output="ok")).passed
    assert not validator.validate(ValidationInput(request="r", output="  ")).passed


def test_registry_queries() -> None:
    core = build_core(plugins=[ToolkitPlugin()], discoverers=[])
    try:
        assert core.registry.capability("tool", "word_count") is not None
        assert core.registry.capability("validator", "non-empty-output") is not None
        assert core.registry.capabilities(CodeAnalyzer)
    finally:
        core.shutdown()
```

Para testar o **workflow ponta a ponta** de forma estável, use um provider de LLM
roteirizado (veja `packages/core/tests/support/workflow.py` do core) em vez de
depender do texto dos prompts internos.

## 10. Checklist

- [ ] `Plugin` com `id` único, `version` e metadata.
- [ ] Cada capability com `name` único dentro do seu `kind`.
- [ ] Tools: `contract.name`/`parameters` coerentes com `invoke`; use `is_error`.
- [ ] Validators: `passed=False` não deve levantar exceção; use `messages`.
- [ ] Discoverers: `discover()` pode levantar `DiscoveryError`.
- [ ] Nós: `id` único, `after` sem ciclos, `AgentState` com `metadata`.
- [ ] Handlers de evento leves e sem bloqueio.
- [ ] Entry point no grupo `core_agent.plugins`.
- [ ] Nenhum import de `langgraph`/`langchain_core` nem de módulos internos do core.

Veja também: [`using-the-core.md`](using-the-core.md) (integrar em um entrypoint) e
[`creating-an-llm-plugin.md`](creating-an-llm-plugin.md) (provider de LLM).
