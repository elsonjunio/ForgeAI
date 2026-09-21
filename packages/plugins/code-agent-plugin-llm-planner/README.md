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
  "nodes": [
    {"id": "n1", "capability": "tool:read_file", "description": "...", "parameters": {"path": "a.py"}}
  ],
  "edges": [{"source": "n1", "target": "n2"}]
}
```

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
- `LLMPlannerError` — resposta sem JSON, JSON inválido ou plano inválido.

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
