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
from core.contracts import plan as plan_module
from core.contracts import planning as planning_module
from core.contracts.capability import Capability
from core.contracts.group import Group
from core.contracts.planning import Planner
from core.plugins.base import Plugin


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
