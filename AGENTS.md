# AGENTS.md

`core-agent` is the provider-neutral core of an extensible Python framework for
code agents. It ships no LLM provider, no concrete tool, and no
filesystem/Git/shell integration — everything is contributed by plugins. With
zero plugins installed the framework still builds and runs.

## Commands

```bash
python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"

.venv/bin/pytest                       # full suite (fast)
.venv/bin/pytest tests/test_runtime.py::test_zero_plugins_runs_end_to_end   # single test
.venv/bin/ruff check src tests         # lint
.venv/bin/mypy src tests               # strict type check
```

Run all three before finishing; they must be clean. There is **no CI and no
pre-commit**, so these commands are the only gates.

Target is Python **3.10+** (`requires-python`, ruff `target-version`, mypy
`python_version`) even though the local venv may be 3.11. Ruff line length is 100.

## Layout

- `src/core/` — the shipped package. Import as `core.*`, never `src.core.*`
  (pytest `pythonpath = ["src"]`, mypy `mypy_path = ["src"]`).
- `tests/` — pytest suite. `tests/support/plugins.py` holds stub plugins used
  only by tests and is excluded from mypy.
- `pyproject.toml` — single source of truth for deps, ruff, mypy, pytest config.

## Architecture constraints (easy to violate)

- **LangGraph is quarantined.** Only `src/core/agent/runtime.py` may import
  `langgraph` / `langchain_core`. Plugins and every other module work with plain
  `AgentState` and must never touch `StateGraph`.
- **Provider-neutral core.** `LLMProvider`, `Tool`, `CodeAnalyzer` and
  `Discoverer` are contracts only (`core/contracts/`) — the core ships no
  implementation and never executes a tool. Add capability as a `Plugin`
  instead. `ToolContract` is a declarative descriptor; executable tools
  implement the `Tool` contract.
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
- **Code-agent workflow.** `WorkflowRuntime` (in `core/agent/runtime.py`, the
  only module allowed to import LangGraph) builds the fixed pipeline
  `initialize → discovery → planning → execution → validation → review`. Stage
  logic lives in `core/agent/workflow.py` and must **not** import `langgraph`
  or concrete plugins. `build_core` always exposes `container.workflow`.
- **Workflow capabilities.** `planning`/`execution`/`review` need the default
  `LLMProvider`; when absent, `WorkflowContext.llm()` raises
  `MissingCapabilityError`. `discovery` runs registered `Discoverer`s
  (none is fine), `execution` reads `Tool`s, `validation` runs registered
  `Validator`s (none means nothing to validate). No tools/discoverers/
  validators → the workflow still runs; build never requires an LLM.
- **Workflow retry/status.** `CoreConfig.workflow.max_attempts` caps execution
  passes. `review` ends `completed` only if approved **and** all validations
  passed; otherwise it retries `execution` while `attempts < max_attempts`, else
  ends `failed`. `run`/`arun` emit `workflow.failed` and re-raise `CoreError`
  (e.g. `MissingCapabilityError`). Events live in `WorkflowEvents`
  (`core/events/types.py`).
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
- `AgentRuntime._finalize` unconditionally sets `status="completed"` on the
  returned state, regardless of what a node set.
- `load_config` accepts only `None`, a mapping, or a path to a JSON file — no
  TOML/YAML.
- Plugins absent from `CoreConfig.plugins` are **enabled by default**
  (`is_enabled`), so zero-configuration works.

## Docs

`README.md` (Portuguese) covers layers, the public API, and a plugin example.
Trust the code when docs and config disagree.
