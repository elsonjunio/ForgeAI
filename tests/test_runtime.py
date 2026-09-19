from __future__ import annotations

import asyncio
from typing import Any

import pytest

from core.agent.runtime import AgentRuntime
from core.agent.state import AgentState
from core.config.schema import CoreConfig
from core.contracts.node import NodeContract, NodeContribution
from core.errors import InvalidGraphError
from core.events.bus import EventBus
from core.events.types import CoreEvents
from core.runtime.bootstrap import build_core
from tests.support.plugins import (
    EchoNodePlugin,
    LifecyclePlugin,
    NoopPlugin,
    make_ordered_node_plugin,
)


def test_zero_plugins_runs_end_to_end() -> None:
    core = build_core()
    assert core.node_ids == ()

    final = core.runtime.run(task="hello")
    assert final.task == "hello"
    assert final.status == "completed"
    assert final.output is None
    assert final.messages == []


def test_zero_plugins_independent_builds() -> None:
    core = build_core()
    core.shutdown()
    assert core.node_ids == ()


def test_noop_plugin_still_runs() -> None:
    core = build_core(plugins=[NoopPlugin()])
    final = core.runtime.run(task="x")
    assert final.status == "completed"


def test_contributed_node_updates_output() -> None:
    core = build_core(plugins=[EchoNodePlugin()])
    assert core.node_ids == ("echo",)

    final = core.runtime.run(task="mirror-me")
    assert final.output == "mirror-me"


def test_node_order_respects_after_constraints() -> None:
    first = make_ordered_node_plugin("first", 1)()
    second = make_ordered_node_plugin("second", 2, after="first")()
    core = build_core(plugins=[second, first])

    final = core.runtime.run(task="order")
    assert final.metadata["trace"] == [1, 2]


def test_multiple_nodes_run_in_declared_order() -> None:
    a = make_ordered_node_plugin("a", "A")()
    b = make_ordered_node_plugin("b", "B")()
    core = build_core(plugins=[a, b])

    final = core.runtime.run(task="seq")
    assert final.metadata["trace"] == ["A", "B"]


def test_state_is_promoted_to_running_then_completed() -> None:
    core = build_core(plugins=[EchoNodePlugin()])
    final = core.runtime.run(task="runme")
    assert final.status == "completed"


def test_runtime_publishes_lifecycle_events() -> None:
    received: dict[str, int] = {}
    bus = EventBus()

    def make_counter(event_type: str) -> Any:
        def count(_: Any) -> None:
            received[event_type] = received.get(event_type, 0) + 1

        return count

    for event_type in (
        CoreEvents.AGENT_STARTED,
        CoreEvents.AGENT_FINISHED,
        CoreEvents.NODE_STARTED,
        CoreEvents.NODE_FINISHED,
    ):
        bus.subscribe(event_type, make_counter(event_type))

    runtime = AgentRuntime(nodes=EchoNodePlugin().declare_nodes(), event_bus=bus)
    runtime.run(task="events")

    assert received[CoreEvents.AGENT_STARTED] == 1
    assert received[CoreEvents.AGENT_FINISHED] == 1
    assert received[CoreEvents.NODE_STARTED] == 1
    assert received[CoreEvents.NODE_FINISHED] == 1


def test_runtime_emits_agent_started_before_node() -> None:
    order: list[str] = []
    bus = EventBus()
    bus.subscribe(CoreEvents.AGENT_STARTED, lambda e: order.append("started"))
    bus.subscribe(CoreEvents.NODE_STARTED, lambda e: order.append("node_started"))
    bus.subscribe(CoreEvents.AGENT_FINISHED, lambda e: order.append("finished"))

    runtime = AgentRuntime(nodes=EchoNodePlugin().declare_nodes(), event_bus=bus)
    runtime.run(task="clock")

    assert order == ["started", "node_started", "finished"]


def test_arun_matches_run_semantics() -> None:
    core = build_core(plugins=[EchoNodePlugin()])

    async def execute() -> AgentState:
        return await core.runtime.arun(task="async-me")

    final = asyncio.run(execute())
    assert final.output == "async-me"
    assert final.status == "completed"


def test_run_accepts_initial_state() -> None:
    core = build_core(plugins=[EchoNodePlugin()])
    initial = AgentState(task="pre-set", messages=[], status="idle")
    final = core.runtime.run(state=initial)
    assert final.task == "pre-set"
    assert final.output == "pre-set"


def test_duplicate_node_id_rejected() -> None:
    contribution = EchoNodePlugin().declare_nodes()[0]
    with pytest.raises(InvalidGraphError):
        AgentRuntime(nodes=[contribution, contribution])


def test_unsatisfiable_ordering_rejected() -> None:
    a = make_ordered_node_plugin("a", 1, after="ghost")()
    with pytest.raises(InvalidGraphError):
        build_core(plugins=[a])


def test_cyclic_ordering_rejected() -> None:
    a = make_ordered_node_plugin("a", 1, after="b")()
    b = make_ordered_node_plugin("b", 2, after="a")()
    with pytest.raises(InvalidGraphError):
        build_core(plugins=[a, b])


def test_disabled_plugin_is_skipped() -> None:
    config = CoreConfig.model_validate({"plugins": {"echo": {"enabled": False}}})
    core = build_core(config=config, plugins=[EchoNodePlugin()])
    assert core.node_ids == ()
    assert "echo" not in core.registry


def test_enabled_plugin_with_settings_receives_context() -> None:
    config = CoreConfig.model_validate(
        {"plugins": {"lifecycle": {"settings": {"timeout": 10}}}}
    )
    core = build_core(config=config, plugins=[LifecyclePlugin()])
    context = core.registry.context("lifecycle")
    assert context is not None
    assert context.get_setting("timeout") == 10


def test_custom_recursion_limit_reaches_graph() -> None:
    config = CoreConfig.model_validate({"langgraph": {"recursion_limit": 5}})
    core = build_core(config=config)
    final = core.runtime.run(task="shallow")
    assert final.status == "completed"


def test_failed_status_set_by_node_is_preserved() -> None:
    def fail(state: AgentState) -> AgentState:
        return state.model_copy(update={"status": "failed"})

    runtime = AgentRuntime(
        nodes=[NodeContribution(contract=NodeContract(id="fail"), node=fail)]
    )
    final = runtime.run(task="x")
    assert final.status == "failed"