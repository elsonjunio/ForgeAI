# code-agent-plugin-filesystem

Plugin de **filesystem** para o `core-agent`: expõe tools executáveis que podem
ser referenciadas por planos (`"tool:fs.read_file"`, ...).

| Tool | Params | Efeito |
|---|---|---|
| `fs.read_file` | `path`, `max_bytes?` | lê UTF-8 (truncado em `max_bytes`) |
| `fs.list_dir` | `path?`, `pattern?` | lista entradas (dirs com `/`) |
| `fs.stat` | `path` | `{exists, is_file, is_dir, size}` |
| `fs.write_file` | `path`, `content`, `create_dirs?`, `dry_run?` | escreve; **idempotente** e **pede confirmação** |

Todas pertencem ao grupo `filesystem`.

## Efeitos colaterais

- `fs.write_file` é **idempotente**: escrever conteúdo idêntico é no-op
  (`metadata.skipped=True`, sem confirmação). Com `dry_run: true`, reporta o que
  seria feito (`create`/`update`/`no-op`) **sem** tocar no disco nem pedir
  confirmação. Escritas que mudam o conteúdo seguem pedindo confirmação.

## Orientação e recuperação

As descrições das tools orientam o planner a **verificar antes de agir**
(ex.: confirmar com `fs.stat` ou `fs.list_dir` antes de ler/escrever).

Falhas de caminho (`FileNotFoundError`, `NotADirectoryError`,
`IsADirectoryError`) são marcadas como **recuperáveis**
(`ToolResult.recoverable=True`) e trazem um **hint**: o diretório mais próximo
existente, o que ele contém e, quando há, um `did you mean ...?`. Assim o
planner consegue corrigir o caminho sem uma iteração extra de descoberta.

Erros de permissão e outros `OSError` permanecem **fatais**.

## Instalação

```bash
pip install -e "packages/plugins/code-agent-plugin-filesystem"
```

Descoberto por `build_core()` (entry point `core_agent.plugins`).

## Segurança

- `root` (default: cwd): todos os caminhos são resolvidos **dentro** do root;
  caminhos que escapam (`../`, absolutos fora) levantam `PathSecurityError`.
- `fs.write_file` pede confirmação via `InteractionProvider` quando
  `require_confirmation` é `true` (default). Sem provider configurado, a escrita
  falha com erro claro.
- `fs.read_file` trunca em `max_read_bytes`.

## Settings

| Setting | Padrão | Descrição |
|---|---|---|
| `root` | cwd | diretório base permitido |
| `allow_outside_root` | `false` | desliga a checagem de containment |
| `max_read_bytes` | `1000000` | limite de leitura |
| `require_confirmation` | `true` | confirma escritas via interação |

## Exemplo

```python
from core import CoreConfig, build_core

config = CoreConfig.model_validate(
    {"plugins": {"code-agent-plugin-filesystem": {"settings": {"root": "/meu/projeto"}}}}
)
core = build_core(config=config)
```

## Limites

- Não é sandbox de processo: a proteção é `root` + confirmação, não isolamento.
- Sem permissões por usuário/capability nem auditoria.
