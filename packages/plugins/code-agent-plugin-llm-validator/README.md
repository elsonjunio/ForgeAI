# code-agent-plugin-llm-validator

Plugin de **Validator** para o `core-agent`: usa o `LLMProvider` default para
julgar se **a requisição foi atendida** ao final de um run.

A validação é **do conjunto**, não de cada passo: o "cada passo funcionou?"
já é coberto por `NodeResult.success`/`recoverable` e pelo loop de recuperação do
host. O validador olha o resultado acumulado (observações, checkpoint,
scratchpad) e decide se o pedido foi satisfeito.

Não é `Executable`: não entra em planos. Quem invoca (e o que fazer com a
falha) é o host — o CLI `/run` chama os validators no desfecho e, quando
reprovam, devolve as mensagens ao planner e replaneja (mesmo orçamento/guard).

## Instalação

```bash
pip install -e "packages/plugins/code-agent-plugin-llm-validator"
```

Instalado, é descoberto por `build_core()` (entry point `core_agent.plugins`).
Precisa de um plugin de LLM (ex.: `code-agent-plugin-opencode-go`).

## Verdicto (JSON pedido ao LLM)

```json
{"passed": false, "issues": ["faltou o README", "sem testes para o core"]}
```

`passed: true` → o host segue para a síntese da resposta final.
`passed: false` → `issues` viram uma observação de falha e o planner replaneja.

## Settings

| Setting | Padrão | Descrição |
|---|---|---|
| `provider` | default | nome do `LLMProvider` a usar |
| `system_prompt` | interno | sobrescreve a instrução de verificação |
| `max_observation_chars` | `1500` | truncamento por observação ao montar o prompt |

## Erros

- `MissingCapabilityError` — nenhum `LLMProvider` disponível.
- `LLMValidatorError` — resposta sem JSON, JSON inválido ou `issues` não-lista.

## Limites

- Julga por **evidência textual** (não executa testes/lint). Validação por
  execução real (shell/test runner) é um passo futuro, com sandbox/allowlist.
