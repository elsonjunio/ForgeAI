# code-agent-plugin-llm-synthesizer

Plugin de **Synthesizer** para o `core-agent`: usa o `LLMProvider` default para
transformar as `Observation`s acumuladas em **texto**, em dois modos:

- `mode="answer"` — resposta final apresentada ao usuário;
- `mode="compact"` — checkpoint comprimido que substitui as observações já
  resumidas, mantendo o contexto do planner limitado.

O sintetizador **não** é `Executable`: ele não entra em planos. Quem decide
quando sintetizar/compactar é o host; o planner apenas **pede** compactação via
`PlanningResult.compaction`.

## Instalação

```bash
pip install -e "packages/plugins/code-agent-plugin-llm-synthesizer"
```

Instalado, é descoberto por `build_core()` (entry point `core_agent.plugins`).
Precisa de um plugin de LLM (ex.: `code-agent-plugin-opencode-go`).

## Como o host usa

```python
from core import Synthesizer, SynthesisRequest

synthesizer = registry.default_capability(Synthesizer)

# síntese final
answer = synthesizer.synthesize(
    SynthesisRequest(request=pedido, observations=observations, checkpoint=checkpoint)
).text

# compactação (quando o planner pede via PlanningResult.compaction)
checkpoint = synthesizer.synthesize(
    SynthesisRequest(
        request=pedido,
        observations=observations_antigas,
        checkpoint=checkpoint,
        mode="compact",
    )
).text
```

O host mantém `keep_last` observações recentes cruas e reenvia
`PlanningRequest.checkpoint` + observações novas na iteração seguinte. O
`Synthesis.usage` reporta o consumo de tokens da chamada.

## Settings

| Setting | Padrão | Descrição |
|---|---|---|
| `provider` | default | nome do `LLMProvider` a usar |
| `system_prompt` | interno | sobrescreve a instrução de síntese |
| `max_observation_chars` | `2000` | truncamento por observação ao montar o prompt |

## Erros

- `MissingCapabilityError` — nenhum `LLMProvider` disponível.
- `LLMSynthesizerError` — o LLM devolveu texto vazio.

## Uso no CLI

Com o plugin instalado, `/run` sintetiza a resposta final e aplica a
compactação pedida pelo planner:

```bash
forgeai
> /run resuma e compare os módulos
```

## Limites

- A compactação é **lossy** por natureza: só o texto do checkpoint sobrevive
  entre iterações.
- O plugin não decide política (limiar, quando compactar); isso é do host.
