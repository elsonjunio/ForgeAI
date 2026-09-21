# Resumo das configurações presentes nos arquivos de `docs/`

Arquivos analisados: `architecture.md`, `creating-an-llm-plugin.md`, `creating-plugins.md`, `using-the-core.md`.

## Ambiente e instalação
- Requisito: Python 3.10+.
- Instalação do core: `pip install -e "packages/core"` (a partir da raiz do monorepo) ou como dependência `core-agent`.
- O core é uma biblioteca: não inclui CLI, servidor, planner nem LLM; o entrypoint, os plugins e o host services (histórico, interação) são fornecidos pelo usuário.

## Arquitetura e limites
- Core = contratos + registry + lifecycle + runtimes.
- LangGraph fica restrito a `core/agent/runtime.py` e `core/agent/graph.py`.
- Regra documental: descrever exatamente o que o código faz hoje, sem prometer o que ainda não existe.
- Versão de referência do documento: `core-agent` 0.1.0.

## Plugins
- Princípio: CORE = contratos + runtime + orquestração; PLUGIN = capacidades.
- Descoberta de plugins por entry points (ou passados explicitamente).
- Tipos de plugin cobertos: provider de LLM (`kind="llm"`), tools, validators, analyzers, discoverers e nós.
- Provider de LLM: pacote Python que implementa `LLMProvider` e expõe a capability via um `Plugin`; o core é provedor-neutro (OpenAI, Ollama, LM Studio, Anthropic, etc. ficam no pacote do plugin).