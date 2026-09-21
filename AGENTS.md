# AGENTS.md

`core-agent` is the provider-neutral core of the **ForgeAI** monorepo
(`https://github.com/elsonjunio/ForgeAI`), an extensible Python framework for code
agents. It ships no LLM provider, no concrete tool, and no
filesystem/Git/shell integration — everything is contributed by plugins. With
zero plugins installed the framework still builds and runs.

## Commands

```bash
python -m venv .venv && source .venv/bin/activate && pip install -e "packages/core[dev]"

.venv/bin/pytest                       # full suite (fast)
.venv/bin/pytest packages/core/tests/test_runtime.py::test_zero_plugins_runs_end_to_end
.venv/bin/ruff check .                 # lint (ruff reads the root pyproject)
.venv/bin/mypy                         # strict type check (files from root pyproject)
```

Run all three before finishing; they must be clean. CI
(`.github/workflows/ci.yml`) runs the same checks on Python 3.10–3.12; there is
no pre-commit.

Target is Python **3.10+** (`requires-python`, ruff `target-version`, mypy
`python_version`) even though the local venv may be 3.11. Ruff line length is 100.

## Layout

Monorepo — every project is an independent Python package with its own
`pyproject.toml`:

- `packages/core/` — the `core-agent` library.
  - `packages/core/src/core/` — import as `core.*`, never `src.core.*`
    (pytest `pythonpath` and mypy `mypy_path` point here, set at the root).
  - `packages/core/tests/` — pytest suite (co-located). `tests/support/` holds
    stubs used only by tests and is excluded from mypy.
    `tests/integration/fake_plugin/` is an external-style plugin that imports
    only the public `core` API and is exercised through entry-point discovery and
    the dynamic plan executor.
  - `packages/core/examples/` — `hello_core.py`.
- `packages/plugins/<plugin>/` — plugin packages (e.g.
  `code-agent-plugin-opencode-go`, `code-agent-plugin-llm-planner`; see their
  README). Plugin test dirs are **not** packages, so test file basenames must be
  unique across the repo (e.g. `test_planner.py`, `test_llm_planner_plugin.py`).
- `apps/cli/` — the `forgeai-cli` package (chat REPL + plugin inspection).
- `pyproject.toml` (repo root) — shared tooling only (ruff/mypy/pytest), **not**
  an installable package. Run `ruff check .`, `mypy`, `pytest` from the root.
- `scripts/build_packages.py` — builds wheel+sdist and zips every package under
  `packages/` and `apps/` (no PyPI); wired into `.github/workflows/`.

## Architecture constraints (easy to violate)

- **Layering.** `core.agent.*` depends on `core.contracts` (for example
  `CapabilitySource`, `PluginMetadata`) and must **not** import concrete
  `core.plugins.*` types. `PluginRegistry` is just one `CapabilitySource`
  implementation; this is what lets external plugin packages be added without
  touching the core.
- **LangGraph is quarantined.** Only `packages/core/src/core/agent/runtime.py`
  and `packages/core/src/core/agent/graph.py` may import `langgraph` /
  `langchain_core`. Plugins, contracts and every other module work with plain
  models and must never touch `StateGraph`.
- **Provider-neutral core.** `LLMProvider`, `Tool`, `CodeAnalyzer`, `Validator`,
  `Discoverer`, `Planner` and `ComplexityEvaluator` are contracts only
  (`core/contracts/`) — the core ships no implementation and never executes a
  tool. Execution/planning models
  (`CapabilityDescriptor`, `ExecutionPlan`/`PlanNode`/`PlanEdge`,
  `ExecutionContext`, `NodeResult`, `ExecutionControl`), the `Group` model and
  the callback / `InteractionProvider` protocols are also pure contracts. Add
  capability as a `Plugin` instead. `ToolContract` is a declarative descriptor;
  executable tools implement the `Tool` contract. The LLM contract returns an
  accumulated `LLMResponse` and accepts an optional observational `on_chunk`
  callback.
- **Capability registry.** Providers are registered on `activate_all` and
  removed on `deactivate_all`. `(kind, name)` must be unique
  (`DuplicateCapabilityError`); several providers of the same kind with
  different names are allowed. Query via `capabilities`/`capability`/
  `has_capability`/`capability_names`; resolve a default with
  `default_capability`.
- **Default provider resolution** (`default_capability`) is, in order:
  `CoreConfig.defaults` (keyed by `kind` or contract class name) → provider with
  `default = True` → the only registered provider → else
  `AmbiguousCapabilityError`; zero providers returns `None`.
- **Plugin lifecycle.** `register()` calls `load()`; `activate_all()` calls
  `initialize(context)` then registers `declare_capabilities()`;
  `deactivate_all()` calls `shutdown()` in reverse order. `Plugin.initialize`
  delegates to `activate` and `shutdown` to `deactivate` — keep that delegation,
  older plugins rely on it.
- **Discovery.** `build_core()` runs `EntryPointDiscoverer` (group
  `core_agent.plugins`) by default; pass `discoverers=[]` to disable. Explicit
  `plugins=` and discovered plugins are registered together (duplicate ids
  raise `DuplicatePluginError`). Other mechanisms implement the `Discoverer`
  contract.
- **Groups.** `Group` is a declarative, many-to-many area (`code`,
  `filesystem`, `version-control`, ...). `Capability.groups` and `Plugin.groups`
  reference groups by id; a plugin belongs to a group explicitly or via its
  capabilities. `Plugin.declare_groups()` describes groups; two plugins declaring
  the same group id raise `DuplicateGroupError`. Query via
  `registry.groups()/group()/group_ids()/capabilities_in_group()/
  plugin_ids_in_group()`.
- **Planners and scopes.** `Planner` (`kind="planner"`) is a capability: no groups
  means global, groups means specialized. The core only discovers and groups them
  (`registry.planners(group=None)`, `registry.planner_descriptors(...)`);
  composing a global planner with specialized ones is the host/plugin's job.
  Planners never execute capabilities — they return an `ExecutionPlan`.
- **Complexity evaluator.** `ComplexityEvaluator` (`kind="complexity"`) is a
  contract only; no heuristic lives in the core.
- **Interaction.** `InteractionProvider` is host-provided (never a capability): it
  reaches plugins via `PluginContext.interaction` and executable capabilities via
  `NodeExecutionRequest.interaction`. `build_core(interaction=...)` wires it.
- **Dynamic plan execution.** `PlanExecutor`/`NodeRunner`/`GraphBuilder`
  (`core/agent/graph.py`) turn an `ExecutionPlan` into a compiled LangGraph graph
  and run it. `GraphBuilder` only does structural validation + wiring (it does
  **not** execute or emit); `NodeRunner` resolves capabilities via
  `CapabilitySource.capability`, executes through the `Executable` protocol (or
  the `Tool` adapter), handles retry/control and emits node events;
  `PlanExecutor` orchestrates build + invoke + finalize. The core has
  **no fixed pipeline** and **no ReAct loop**: the graph is whatever the plan
  says. Validation runs before building (`InvalidPlanError`,
  `MissingCapabilityError`, `UnsupportedCapabilityError`). No automatic history
  and no memory. `PAUSE`/`INTERRUPT` stop the run; persistent checkpointing is
  not implemented.
- **Two runtimes.** `AgentRuntime` (`core/agent/runtime.py`) is the *generic node
  runtime* (plugin-contributed `NodeContribution`s over `AgentState`).
  `NodeRunner`/`PlanExecutor` (`core/agent/graph.py`) are the *plan runtime*
  (`ExecutionPlan` -> LangGraph). Both know LangGraph; neither knows concrete
  plugins.
- **Graph wiring lives in `AgentRuntime`**: `START -> __core_init__ -> n1 -> ...
  -> nn -> END`. `__core_init__` is reserved; contributing a node with that id
  raises `InvalidGraphError`.
- Node ids are **globally unique across all plugins** (duplicates raise
  `InvalidGraphError`). Ordering uses `NodeContract.after`; cycles or unsatisfied
  `after` constraints fail at construction via stable topological sort.
- Plugin lifecycle: `activate_all` subscribes declared event handlers *before*
  calling `activate`, then publishes `plugin.activated`. `deactivate_all` runs in
  reverse registration order.
- A plugin whose slot is `enabled: false` is never registered (not merely
  deactivated), so it contributes nothing.

## Gotchas

- `AgentState` and `Message` use `extra="forbid"`; put free-form data in
  `metadata`, never by adding fields.
- `AgentRuntime._finalize` preserves a `failed` status set by a node; otherwise
  it marks the run `completed`.
- `load_config` accepts only `None`, a mapping, or a path to a JSON file — no
  TOML/YAML.
- Plugins absent from `CoreConfig.plugins` are **enabled by default**
  (`is_enabled`), so zero-configuration works.
- **Current limits (do not assume they exist):** no persistent checkpoint
  (`PAUSE`/`INTERRUPT` only stop the run), plans are DAGs (no cycles), the plan
  execution state is a shared mutable object, `PlanExecutor.run` is sync (no
  `arun`), the LLM contract has no tool-calls and there is no tool-calling loop,
  no memory/RAG, and `CapabilityDescriptor.constraints` is descriptive only. The
  canonical list is in `docs/architecture.md`.

## Docs

`docs/architecture.md` is the canonical reference for responsibilities, layer
boundaries and current limits — keep it in sync with behavior changes.
`README.md` (Portuguese) covers layers, the public API and a plugin example.
Trust the code when docs and config disagree.
