"""Architectural boundary checks.

These tests make the intended responsibilities explicit so future changes do not
confuse them:

    Planner != GraphBuilder/Runtime
    ExecutionPlan != LangGraph
    Capability != Plugin
    Group != Plugin
    Memory/CLI != Core
    No ReAct loop and no fixed workflow in the core.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import core as core_package
from core.agent import graph as graph_module
from core.agent import runtime as runtime_module
from core.agent.graph import GraphBuilder, NodeRunner, PlanExecutor
from core.config.schema import CoreConfig
from core.contracts import plan as plan_module
from core.contracts import planning as planning_module
from core.contracts import synthesis as synthesis_module
from core.contracts.callbacks import ExecutionEvent
from core.contracts.capability import Capability
from core.contracts.execution import (
    ExecutionContext,
    NodeExecutionRequest,
    NodeResult,
)
from core.contracts.group import Group
from core.contracts.plan import ExecutionPlan, PlanNode
from core.contracts.planning import Planner
from core.contracts.synthesis import Synthesizer
from core.events.bus import EventBus
from core.plugins.base import Plugin
from core.plugins.registry import PluginRegistry
from tests.support.capabilities import CapabilityPlugin


def _core_root() -> Path:
    return Path(core_package.__file__).parent


# --- Planner is not the engine ----------------------------------------------


def test_planner_is_not_graphbuilder_or_runtime() -> None:
    from core.agent.graph import GraphBuilder, PlanExecutor

    assert Planner.__module__ != GraphBuilder.__module__
    assert Planner.__module__ != PlanExecutor.__module__
    assert "langgraph" not in inspect.getsource(planning_module)


def test_planner_contract_has_no_execute() -> None:
    assert not hasattr(Planner, "execute")


# --- Synthesizer is not the engine either -----------------------------------


def test_synthesizer_contract_has_no_langgraph_or_execute() -> None:
    assert "langgraph" not in inspect.getsource(synthesis_module)
    assert not hasattr(Synthesizer, "execute")
    assert Synthesizer.kind == "synthesizer"


# --- ExecutionPlan does not depend on LangGraph -----------------------------


def test_execution_plan_has_no_langgraph() -> None:
    assert "langgraph" not in inspect.getsource(plan_module)
    assert "langchain" not in inspect.getsource(plan_module)


# --- Capability/Group are not Plugin ----------------------------------------


def test_capability_is_not_plugin() -> None:
    assert not issubclass(Plugin, Capability)
    assert not issubclass(Capability, Plugin)


def test_group_is_not_plugin() -> None:
    assert not issubclass(Group, Plugin)
    assert not issubclass(Plugin, Group)


# --- LangGraph is quarantined in the execution modules ----------------------


def test_langgraph_only_in_execution_modules() -> None:
    root = _core_root()
    allowed = {root / "agent" / "graph.py", root / "agent" / "runtime.py"}
    import_pattern = re.compile(
        r"^\s*(?:from|import)\s+(?:langgraph|langchain)", re.MULTILINE
    )
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if path in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        if import_pattern.search(text):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_execution_modules_do_import_langgraph() -> None:
    assert "langgraph" in inspect.getsource(graph_module)
    assert "langgraph" in inspect.getsource(runtime_module)


# --- No domain decisions in the core ----------------------------------------


def test_workflow_removed_from_core() -> None:
    names = {path.name for path in _core_root().rglob("*.py")}
    assert "workflow.py" not in names
    assert "workflow_state.py" not in names
    assert not hasattr(core_package, "WorkflowRuntime")
    assert not hasattr(core_package, "WorkflowState")


def test_no_memory_or_cli_modules_in_core() -> None:
    names = [path.name for path in _core_root().rglob("*.py")]
    assert not any("memory" in name for name in names)
    assert not any(name == "cli.py" or name.startswith("cli_") for name in names)


def test_no_react_loop_in_core() -> None:
    for path in _core_root().rglob("*.py"):
        assert "react" not in path.read_text(encoding="utf-8").lower(), path.name


# --- GraphBuilder (plan -> graph) vs NodeRunner/PlanExecutor (runtime) ------


class _CountingStep(Capability):
    kind = "step"

    def __init__(self) -> None:
        self.calls = 0

    @property
    def name(self) -> str:
        return "count"

    def execute(self, request: NodeExecutionRequest) -> NodeResult:
        self.calls += 1
        return NodeResult.ok(request.node.id)


class _RecordingObserver:
    def __init__(self) -> None:
        self.events: list[ExecutionEvent] = []

    def on_event(self, event: ExecutionEvent) -> None:
        self.events.append(event)


def _make_executor(
    *capabilities: Capability, observer: _RecordingObserver | None = None
) -> PlanExecutor:
    registry = PluginRegistry(config=CoreConfig(), events=EventBus())
    registry.register(CapabilityPlugin(list(capabilities), plugin_id="boundaries"))
    registry.activate_all()
    return PlanExecutor(registry=registry, observer=observer)


def test_graph_builder_does_not_execute_or_emit() -> None:
    step = _CountingStep()
    observer = _RecordingObserver()
    executor = _make_executor(step, observer=observer)
    plan = ExecutionPlan(id="p", nodes=(PlanNode(id="n", capability="step:count"),))

    executor.builder.build(plan)
    assert step.calls == 0
    assert observer.events == []

    executor.run(plan, ExecutionContext(request="x"))
    assert step.calls == 1
    assert observer.events


def test_graph_builder_source_has_no_runtime_concerns() -> None:
    builder_source = inspect.getsource(GraphBuilder)
    runner_source = inspect.getsource(NodeRunner)

    assert "on_node_complete" not in builder_source
    assert "ExecutionEventKind" not in builder_source
    assert "on_node_complete" in runner_source
    assert "ExecutionEventKind" in runner_source


def test_executor_exposes_runner_and_builder() -> None:
    executor = _make_executor(_CountingStep())
    assert isinstance(executor.builder, GraphBuilder)
    assert isinstance(executor.runner, NodeRunner)
