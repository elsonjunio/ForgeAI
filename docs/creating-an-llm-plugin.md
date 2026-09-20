# Criando um plugin de LLM

Este guia mostra como criar um plugin que fornece um **provider de LLM** ao
`core-agent`. O core é provedor-neutro: ele define o contrato `LLMProvider` e
resolve o provider pelo registry; quem fala com a API (OpenAI, Ollama, LM Studio,
Anthropic, ...) é o **seu** pacote.

Um plugin de LLM é um pacote Python comum que:

1. implementa `LLMProvider` (a capability `kind="llm"`);
2. expõe essa capability via um `Plugin`;
3. é descoberto por entry point (ou passado explicitamente).

O provider é consumido por quem decidir chamar LLM — planners, capabilities ou a
aplicação. O core não impõe etapas de uso.

## 1. O contrato `LLMProvider`

```python
from collections.abc import Sequence
from typing import Any

from core import LLMChunkCallback, LLMProvider, LLMResponse, Message

class MeuProvider(LLMProvider):        # kind = "llm"
    @property
    def name(self) -> str:             # único dentro do kind
        ...

    def complete(
        self,
        messages: Sequence[Message],
        *,
        on_chunk: LLMChunkCallback | None = None,
        **options: Any,
    ) -> LLMResponse:
        ...
```

- `name` — identificador estável do provider (ex.: `"openai"`, `"ollama"`).
- `complete(messages, *, on_chunk=None, **options)` — recebe a conversa e devolve
  um `LLMResponse` **acumulado**. É **síncrono**; `**options` é passado adiante
  por convenção.
- `on_chunk` é **observacional**: se informado, o provider chama com `LLMChunk` a
  cada pedaço recebido. O consumidor **não** reconstrói a resposta a partir dos
  chunks — ele usa o `LLMResponse` retornado.
- `default = True` (atributo de classe) marca o provider como default do kind.

`LLMResponse` (retorno):

| Campo | Tipo | Observação |
|---|---|---|
| `message` | `Message` | a mensagem do assistente (`.content` atalha para `message.content`). |
| `usage` | `LLMUsage \| None` | tokens (prompt/completion/total), quando disponível. |
| `metadata` | `dict` | dados do provider (modelo, finish reason, ...). |

`Message` (contrato do core):

| Campo | Tipo | Observação |
|---|---|---|
| `role` | `"system" \| "user" \| "assistant" \| "tool"` | mapeia direto para os papéis de chat. |
| `content` | `str` | texto da mensagem. |
| `name` | `str \| None` | nome opcional do participante. |
| `tool_call_id` | `str \| None` | para mensagens de papel `tool`. |

> Não acople o provider a prompts específicos de um planner/capability. Implemente
> um `complete` genérico; quem chama decide o que enviar.

## 2. Plugin mínimo

```python
# code_agent_plugin_meu_llm/__init__.py
"""Plugin de LLM determinístico (útil para desenvolvimento e testes)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from core import Capability, LLMProvider, LLMResponse, Message, Plugin, PluginContext


class EchoLLM(LLMProvider):
    default = True

    def __init__(self, model: str = "echo-1") -> None:
        self._model = model

    @property
    def name(self) -> str:
        return "echo"

    def complete(self, messages: Sequence[Message], **options: Any) -> LLMResponse:
        prompt = messages[-1].content if messages else ""
        return LLMResponse(
            message=Message(role="assistant", content=f"[{self._model}] {prompt[:200]}")
        )


class EchoLLMPlugin(Plugin):
    id = "code-agent-plugin-echo-llm"
    version = "0.1.0"
    description = "Provider determinístico para desenvolvimento."

    def __init__(self, model: str = "echo-1") -> None:
        self._model = model

    def declare_capabilities(self) -> list[Capability]:
        return [EchoLLM(self._model)]
```

Com esse plugin registrado, o core passa a ter um provider de LLM. O `EchoLLM` é
um stub determinístico: serve para comprovar a fiação, não para raciocinar de
verdade. Um provider real apenas faz a completion; quem chama interpreta o texto
devolvido.

## 3. Lendo configuração (settings)

Configurações por plugin vivem em `CoreConfig.plugins.<id>.settings` e chegam pelo
`PluginContext` no `initialize`:

```json
{
  "plugins": {
    "code-agent-plugin-meu-llm": {
      "enabled": true,
      "settings": { "model": "gpt-4o-mini", "base_url": "https://api.openai.com/v1" }
    }
  }
}
```

```python
def initialize(self, context: PluginContext) -> None:
    self._model = context.get_setting("model", self._model)
    api_key = context.get_setting("api_key")           # ou
    timeout = context.settings.get("timeout", 60.0)
```

`initialize(context)` roda **antes** de `declare_capabilities()`, então você pode
construir o provider já com os settings aplicados.

## 4. Ciclo de vida e recursos

O registry chama, nesta ordem: `load()` (ao registrar) → `initialize(context)` →
`declare_capabilities()` → … → `shutdown()` (ordem reversa).

Abra clientes/conexões em `initialize` e libere em `shutdown`:

```python
class MeuPlugin(Plugin):
    id = "code-agent-plugin-meu-llm"

    def __init__(self) -> None:
        self._provider: MeuProvider | None = None

    def load(self) -> None:
        ...   # validação barata, sem I/O de rede

    def initialize(self, context: PluginContext) -> None:
        self._provider = MeuProvider(model=context.get_setting("model", "gpt-4o-mini"))

    def declare_capabilities(self) -> list[Capability]:
        assert self._provider is not None
        return [self._provider]

    def shutdown(self) -> None:
        if self._provider is not None:
            self._provider.close()
```

> `initialize`/`shutdown` têm implementações default que delegam para
> `activate`/`deactivate`. Se você sobrescrever `initialize`, `activate` **não**
> roda automaticamente.

## 5. Provider default e múltiplos providers

O core resolve o provider default assim, em ordem:

1. `CoreConfig.defaults` (`{"llm": "meu-llm"}` ou `{"llm": "MeuProvider"}`);
2. provider com `default = True`;
3. o único provider registrado.

Com dois ou mais providers e nenhuma seleção, `default_capability` levanta
`AmbiguousCapabilityError`. Vários providers do mesmo kind convivem sem problema
(basta terem `name` distintos); o usuário escolhe pelos settings/`defaults`.

## 6. Empacotamento e entry point

`pyproject.toml` do **seu** pacote de plugin:

```toml
[project]
name = "code-agent-plugin-meu-llm"
version = "0.1.0"
dependencies = [
    "core-agent",       # o core
    "httpx>=0.27",      # dependência do seu provider (exemplo)
]

[project.entry-points."core_agent.plugins"]
code-agent-plugin-meu-llm = "code_agent_plugin_meu_llm:MeuLLMPlugin"
```

Instale no mesmo ambiente do core:

```bash
pip install -e .
```

Pronto: `build_core()` (sem `discoverers=[]`) passa a descobrir o plugin
automaticamente.

## 7. Verificando localmente

```python
from core import LLMProvider, build_core

core = build_core()                       # descobre por entry points
try:
    provider = core.registry.default_capability(LLMProvider)
    print(provider.name if provider else "sem provider")
finally:
    core.shutdown()
```

Sem instalar, dá para testar passando a instância:

```python
core = build_core(plugins=[EchoLLMPlugin()], discoverers=[])
```

Se não houver nenhum provider de LLM, o core falha de forma explícita:

```text
MissingCapabilityError: no LLM provider is registered (capability kind 'llm');
install a plugin that provides an LLMProvider
```

## 8. Provider real (OpenAI-compatível, Ollama, LM Studio)

Ollama e LM Studio expõem uma API compatível com a da OpenAI em `/v1`; o mesmo
provider serve para os três, mudando `base_url`/`model`.

```python
# code_agent_plugin_meu_llm/provider.py
from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

import httpx

from core import LLMChunk, LLMChunkCallback, LLMProvider, LLMResponse, LLMUsage, Message


class OpenAICompatibleLLM(LLMProvider):
    """Provider para APIs no formato chat/completions da OpenAI."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.Client(timeout=timeout)

    @property
    def name(self) -> str:
        return self._model

    def close(self) -> None:
        self._client.close()

    def complete(
        self,
        messages: Sequence[Message],
        *,
        on_chunk: LLMChunkCallback | None = None,
        **options: Any,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [self._to_wire(m) for m in messages],
            **options,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        response = self._client.post(
            f"{self._base_url}/chat/completions", json=payload, headers=headers
        )
        response.raise_for_status()                 # erros viram exceção observável
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        if on_chunk is not None:                    # chunk observacional (ex.: sem streaming real)
            on_chunk(LLMChunk(content=content))
        usage = data.get("usage") or {}
        return LLMResponse(
            message=Message(role="assistant", content=content),
            usage=LLMUsage(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
            ),
            metadata={"model": data.get("model", self._model)},
        )

    @staticmethod
    def _to_wire(message: Message) -> dict[str, Any]:
        wire: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.name:
            wire["name"] = message.name
        if message.tool_call_id:
            wire["tool_call_id"] = message.tool_call_id
        return wire
```

```python
# code_agent_plugin_meu_llm/__init__.py
from __future__ import annotations

import os

from core import Capability, Plugin, PluginContext

from .provider import OpenAICompatibleLLM


class MeuLLMPlugin(Plugin):
    id = "code-agent-plugin-meu-llm"
    version = "0.1.0"
    description = "Provider OpenAI-compatível (OpenAI, Ollama, LM Studio)."

    def __init__(self) -> None:
        self._provider: OpenAICompatibleLLM | None = None

    def initialize(self, context: PluginContext) -> None:
        self._provider = OpenAICompatibleLLM(
            model=context.get_setting("model", "gpt-4o-mini"),
            base_url=context.get_setting("base_url", "https://api.openai.com/v1"),
            api_key=context.get_setting("api_key", os.environ.get("OPENAI_API_KEY")),
            timeout=float(context.get_setting("timeout", 60.0)),
        )

    def shutdown(self) -> None:
        if self._provider is not None:
            self._provider.close()

    def declare_capabilities(self) -> list[Capability]:
        assert self._provider is not None
        return [self._provider]
```

Configs típicas:

| Backend | `base_url` | `model` |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Ollama | `http://localhost:11434/v1` | `llama3.1` |
| LM Studio | `http://localhost:1234/v1` | o id carregado no app |

### Erros

Se `complete` levantar qualquer exceção, ela é observável na execução
(`NodeResult.failed`/`ExecutionResult.error`). Não é obrigatório herdar de
`CoreError`; mas, se quiser um erro de domínio, herde de `CoreError` para que o
entrypoint possa capturá-lo genericamente.

## 9. Testando o plugin

Teste o provider isolado (sem rede) e o plugin via `build_core`:

```python
# tests/test_provider.py
from core import Message

from code_agent_plugin_meu_llm import EchoLLM


def test_provider_returns_assistant_message() -> None:
    provider = EchoLLM()
    reply = provider.complete([Message(role="user", content="oi")])
    assert reply.message.role == "assistant"
    assert reply.content
```

Providers que suportam streaming emitem chunks pelo callback e ainda devolvem a
resposta acumulada:

```python
def test_provider_streams_chunks() -> None:
    chunks = []
    reply = EchoLLM().complete(
        [Message(role="user", content="oi")], on_chunk=chunks.append
    )
    assert reply.content  # resposta completa, independente dos chunks
```

```python
# tests/test_plugin_integration.py
from core import LLMProvider, build_core

from code_agent_plugin_meu_llm import EchoLLMPlugin


def test_plugin_registers_llm_capability() -> None:
    core = build_core(plugins=[EchoLLMPlugin()], discoverers=[])
    try:
        assert core.registry.get("code-agent-plugin-echo-llm") is not None
        assert core.registry.default_capability(LLMProvider) is not None
    finally:
        core.shutdown()
```

Dica: use um provider determinístico (como `EchoLLM`) para testar a fiação.
Para exercitar planejamento/execução de forma estável, use um provider com
respostas roteirizadas (um `ScriptedLLMProvider`, como em
`packages/core/tests/support/capabilities.py` do próprio core), em vez de depender
de texto específico de prompt. Guarde chamadas de rede para testes marcados como
integração.

## 10. Checklist

- [ ] `LLMProvider` com `name` único e `complete` genérico.
- [ ] `Plugin` com `id` único, `version` e metadata.
- [ ] Capability exposta em `declare_capabilities()` (ou via `context.register_capability`).
- [ ] Settings lidos em `initialize`; recursos liberados em `shutdown`.
- [ ] `default = True` **ou** `CoreConfig.defaults` quando houver mais de um provider.
- [ ] Entry point no grupo `core_agent.plugins`.
- [ ] Testes do provider (unit) e do plugin (integração).
- [ ] Nenhum import de `langgraph`/`langchain_core` nem de módulos internos do core.

Para entender a arquitetura, fronteiras e limites atuais, veja
[`architecture.md`](architecture.md) e **outros tipos de plugin** (tools,
validators, analyzers, discoverers, nós) em
[`creating-plugins.md`](creating-plugins.md). Para integrar o core em um
entrypoint, veja [`using-the-core.md`](using-the-core.md).
