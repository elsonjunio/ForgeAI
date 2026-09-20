# cli

Aplicação de linha de comando (entrypoint) do monorepo. Ainda não implementada.

Quando criada, será um pacote Python que:

- depende de `core-agent` (e dos plugins que quiser embarcar);
- chama `build_core()` e roda `container.workflow`;
- expõe o binário via `[project.scripts]`.

Esqueleto previsto:

```
apps/cli/
  pyproject.toml          # [project.scripts]
                          # meu-code-agent = "meu_agente.cli:main"
  src/meu_agente/...
```

O workflow de release também empacota qualquer diretório sob `apps/` com
`pyproject.toml`. Para o código do entrypoint, veja
[`docs/using-the-core.md`](../../docs/using-the-core.md).
