# code-agent-plugin-opencode-go

Plugin de LLM para o **OpenCode Go** (`core-agent`), servido por uma API
**OpenAI-compatible** de chat completions.

- **Base URL padrão:** `https://opencode.ai/zen/go/v1`
- **Endpoint:** `POST /chat/completions`
- **Auth:** `Authorization: Bearer $OPENCODE_API_KEY`
- **Modelo padrão:** `deepseek-v4.1-flash`

> Apenas modelos servidos por `chat/completions` são suportados. Alguns modelos
> do OpenCode Go usam outros dialetos (`/v1/messages`, `/v1/responses`) e não
> funcionam com este provider.

## Instalação

```bash
pip install -e "packages/plugins/code-agent-plugin-opencode-go"
export OPENCODE_API_KEY="..."
```

Instalado, o plugin é descoberto automaticamente por `build_core()` (entry point
no grupo `core_agent.plugins`).

## Uso

```python
from core import CoreConfig, LLMProvider, build_core

config = CoreConfig.model_validate(
    {
        "plugins": {
            "code-agent-plugin-opencode-go": {
                "settings": {"model": "deepseek-v4.1-flash"}
            }
        },
        "defaults": {"llm": "opencode-go"},
    }
)
core = build_core(config=config)
try:
    provider = core.registry.default_capability(LLMProvider)
    ...
finally:
    core.shutdown()
```

## Settings

| Setting | Padrão | Descrição |
|---|---|---|
| `model` | `deepseek-v4.1-flash` | id do modelo (`GET /v1/models`) |
| `api_key` | `$OPENCODE_API_KEY` | chave da API |
| `base_url` | `https://opencode.ai/zen/go/v1` | base da API |
| `timeout` | `60` | timeout HTTP (s) |
| `session_id` | gerado | enviado como `x-opencode-session` |
| `reasoning_effort` | — | `low` / `high` / `max` |

## Streaming

Se `on_chunk` for informado, o provider usa SSE (`stream: true`) e emite
`LLMChunk` por `delta.content`, devolvendo a resposta acumulada em `LLMResponse`.
O formato SSE é o padrão OpenAI (inferido da stack `@ai-sdk/openai-compatible`).

## Notas

- Sem API key, `build_core()` continua funcionando; o erro claro aparece ao
  chamar `complete` (`OpenCodeGoError`).
- O provider envia `User-Agent` próprio e `x-opencode-session`, como recomendado
  pela documentação do OpenCode Go.
