# core-agent

Núcleo do framework de Code Agents — **contratos + runtime + orquestração**.

Este pacote não traz nenhuma capacidade concreta (LLM, filesystem, Git, shell,
MCP); tudo é contribuído por plugins. Com **zero plugins instalados** o framework
continua construído e executável.

Ele faz parte de um monorepo. A documentação completa está no
[README do repositório](../../README.md):

- [Usando o core em um entrypoint](../../docs/using-the-core.md)
- [Criando um plugin de LLM](../../docs/creating-an-llm-plugin.md)
- [Criando os demais plugins](../../docs/creating-plugins.md)

## Desenvolvimento

A partir da raiz do repositório:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e "packages/core[dev]"

pytest          # testes (config na raiz)
ruff check .    # lint
mypy            # type checking (strict)
```
