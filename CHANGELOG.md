# Changelog

Todas as mudanças relevantes do monorepo **ForgeAI** são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o
versionamento segue [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

## [0.1.0] - 2026-09-19

Primeiro release do `core-agent`.

### Adicionado

- Core provedor-neutro com contratos puros: `Capability`, `LLMProvider`, `Tool`
  (+ `ToolContract`/`ToolResult`), `CodeAnalyzer`, `Validator`, `Discoverer`,
  `PluginMetadata` e a interface `CapabilitySource`.
- `Plugin` com ciclo de vida (`load` → `initialize` → `shutdown`) e contribuições
  declarativas (`declare_capabilities`, `declare_tools`, `declare_nodes`,
  `event_handlers`); `activate`/`deactivate` mantidos por compatibilidade.
- `PluginRegistry` com capabilities, provider default
  (`CoreConfig.defaults` / `default = True` / provider único) e consultas por
  tipo ou `kind`.
- Descoberta dinâmica de plugins por entry points (grupo `core_agent.plugins`),
  com `Discoverer` plugável.
- `AgentRuntime` (grafo genérico de nós) e `WorkflowRuntime` (pipeline
  `initialize → discovery → planning → execution → validation → review`) com
  retry, interrupção e eventos (`WorkflowEvents`).
- `WorkflowState` tipado (request, contexto, plano, tarefas, validações, review,
  erros, status, tentativas) e `MissingCapabilityError` para capability ausente.
- Core inicializável com **zero plugins**.
- Monorepo: `packages/core`, `packages/plugins`, `apps/cli` e tooling
  compartilhado na raiz.
- Empacotamento sem PyPI: `scripts/build_packages.py` (wheel + sdist → zip por
  pacote) e workflows de CI/release em `.github/workflows/`.
- Documentação: `docs/using-the-core.md`, `docs/creating-an-llm-plugin.md` e
  `docs/creating-plugins.md`, além do `AGENTS.md`.

### Notas

- O fluxo completo do agente (tool-calling real, memória) ainda não está
  implementado; o workflow base é infraestrutura de orquestração.
- Nenhum provider/ferramenta concreto é distribuído: LLM, filesystem, Git, shell
  e MCP virão como plugins externos.

[Não lançado]: https://github.com/elsonjunio/ForgeAI/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/elsonjunio/ForgeAI/releases/tag/v0.1.0
