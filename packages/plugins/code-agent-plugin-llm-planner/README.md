# code-agent-plugin-llm-planner

Plugin de **Planner** para o `core-agent`: usa o `LLMProvider` default para
transformar um `PlanningRequest` em um `ExecutionPlan`.

O planner não conhece LangGraph nem tools concretas: ele lista as capabilities
disponíveis (`request.capabilities`, descriptors) e pede ao LLM um plano em JSON
referenciando **ids de capability** (`"tool:<nome>"`). O core valida e executa.

## Instalação

```bash
pip install -e "packages/plugins/code-agent-plugin-llm-planner"
```

Instalado, é descoberto por `build_core()` (entry point `core_agent.plugins`).
Precisa de um plugin de LLM (ex.: `code-agent-plugin-opencode-go`).

## Formato do plano (JSON pedido ao LLM)

```json
{
  "id": "plan-1",
  "needs_more_info": false,
  "nodes": [
    {"id": "n1", "capability": "tool:read_file", "description": "...", "parameters": {"path": "a.py"}}
  ],
  "edges": [{"source": "n1", "target": "n2"}]
}
```

- `needs_more_info: true` → o plano só **coleta informação**; o host executa e
  volta a planejar com as `Observation`s acumuladas (plan → execute → observe →
  replan), até `needs_more_info: false`.
- `needs_more_info: false` (default) → o plano conclui o pedido.
- O prompt inclui as observações anteriores em "Information already gathered".
- Só ids de capability listados são válidos; se nenhum servir, `"nodes": []`.
- Aceita JSON puro ou cercado por ```` ```json ````.
- `max_nodes` limita a quantidade de nodes.

## Settings

| Setting | Padrão | Descrição |
|---|---|---|
| `provider` | default | nome do `LLMProvider` a usar |
| `max_nodes` | `8` | limite de nodes do plano |
| `system_prompt` | interno | sobrescreve a instrução de planejamento |

## Erros

- `MissingCapabilityError` — nenhum `LLMProvider` disponível.
- `LLMPlannerError` — resposta sem JSON, JSON inválido, plano inválido ou node
  referenciando uma capability **não executável**.

> O planner recebe em `request.capabilities` apenas capabilities **executáveis**
> (o host filtra com `executable_capability_descriptors()`), então o LLM não vê
> `llm:*`/`planner:*` como opção. Ainda assim, o planner valida os ids do plano e
> rejeita escolhas inválidas com `LLMPlannerError`.

## Uso no CLI

```bash
forgeai
> /plan refatore o parser
> /run refatore o parser
```

## Limites

- Planejamento **estático**: um DAG por request; sem loop ReAct e sem tool-calling.
- Sem tools instalados, o plano tende a ser vazio — o trabalho real vem dos
  plugins de tool (filesystem/shell).
