# plugins

Pacotes de plugin do monorepo. Cada plugin é um pacote Python independente que
depende de `core-agent` e declara um entry point no grupo `core_agent.plugins`
(assim é descoberto automaticamente por `build_core()`).

Estrutura prevista:

```
packages/plugins/
  code-agent-plugin-openai/
    pyproject.toml
    src/code_agent_plugin_openai/...
  code-agent-plugin-git/
  ...
```

Nenhum plugin concreto vive aqui ainda. Para criar um, veja
[`docs/creating-an-llm-plugin.md`](../../docs/creating-an-llm-plugin.md) e
[`docs/creating-plugins.md`](../../docs/creating-plugins.md).

O workflow de release ([`.github/workflows/release.yml`](../../.github/workflows/release.yml))
descobre e empacota automaticamente qualquer diretório sob `packages/plugins/`
que tenha um `pyproject.toml` com `[build-system]` e `[project]`.
