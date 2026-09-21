# code-agent-plugin-filesystem

Plugin de **filesystem** para o `core-agent`: expõe tools executáveis que podem
ser referenciadas por planos (`"tool:fs.read_file"`, ...).

| Tool | Params | Efeito |
|---|---|---|
| `fs.read_file` | `path`, `max_bytes?` | lê UTF-8 (truncado em `max_bytes`) |
| `fs.list_dir` | `path?`, `pattern?` | lista entradas (dirs com `/`) |
| `fs.stat` | `path` | `{exists, is_file, is_dir, size}` |
| `fs.write_file` | `path`, `content`, `create_dirs?` | escreve; **pede confirmação** |

Todas pertencem ao grupo `filesystem`.

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
