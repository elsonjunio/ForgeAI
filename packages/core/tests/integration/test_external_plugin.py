"""Integration test: an external plugin built without touching the core.

The plugin lives in ``tests/integration/fake_plugin`` and imports only the
public ``core`` API. These tests prove it can be loaded directly and through
entry-point discovery, and that its capabilities are resolved by the dynamic
plan executor.
"""

from __future__ import annotations

from typing import Any

import pytest

from core import (
    ExecutionContext,
    ExecutionPlan,
    LLMProvider,
    PlanNode,
    build_core,
)
from core.plugins.discovery import EntryPointDiscoverer
from tests.integration.fake_plugin import PLUGIN_ID, ExternalFakePlugin, build


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        id="integration-plan",
        nodes=(PlanNode(id="run-tool", capability="tool:noop"),),
    )


def test_external_plugin_runs_plan_end_to_end() -> None:
    core = build_core(plugins=[ExternalFakePlugin()], discoverers=[])

    result = core.executor.run(_plan(), ExecutionContext(request="do something"))
    core.shutdown()

    assert result.status == "completed"
    assert result.results["run-tool"].success is True


def test_external_plugin_registers_capabilities_and_metadata() -> None:
    core = build_core(plugins=[ExternalFakePlugin()], discoverers=[])

    assert PLUGIN_ID in core.registry
    metadata = core.registry.metadata(PLUGIN_ID)
    assert metadata is not None
    assert metadata.version == "0.1.0"
    assert core.registry.default_capability(LLMProvider) is not None
    core.shutdown()


class _FakeEntryPoint:
    name = PLUGIN_ID

    def __init__(self, target: Any) -> None:
        self._target = target

    def load(self) -> Any:
        return self._target


@pytest.mark.parametrize(
    "target",
    [
        ExternalFakePlugin,          # a Plugin subclass
        ExternalFakePlugin(),        # a ready instance
        build,                       # a zero-argument factory
    ],
)
def test_external_plugin_loaded_via_entry_point(
    monkeypatch: pytest.MonkeyPatch,
    target: Any,
) -> None:
    def fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        assert group == "core_agent.plugins"
        return [_FakeEntryPoint(target)]

    monkeypatch.setattr(
        "core.plugins.discovery.importlib_metadata.entry_points", fake_entry_points
    )

    core = build_core()  # default discovery uses the patched entry points
    assert PLUGIN_ID in core.registry

    result = core.executor.run(_plan(), ExecutionContext(request="x"))
    core.shutdown()

    assert result.status == "completed"


def test_entry_point_discoverer_default_group() -> None:
    assert EntryPointDiscoverer().name == "entry-points:core_agent.plugins"
