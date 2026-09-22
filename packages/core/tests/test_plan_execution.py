from __future__ import annotations

from typing import Any

import pytest

from core import (
    Capability,
    ControlAction,
    CoreConfig,
    EventBus,
    ExecutionContext,
    ExecutionControl,
    ExecutionEvent,
    ExecutionEventKind,
    ExecutionPlan,
    InvalidPlanError,
    MissingCapabilityError,
    NodeExecutionRequest,
    NodeResult,
    PlanEdge,
    PlanExecutor,
    PlanNode,
    UnsupportedCapabilityError,
    build_core,
)
from core.plugins.registry import PluginRegistry
from tests.support.capabilities import CapabilityPlugin

# --- fake capabilities (test-only; never shipped by the core) ---------------


class _RecordingStep(Capability):
    """Executable capability that records its marker into context metadata."""

    kind = "step"

    def __init__(self, name: str, marker: str | None = None) -> None:
        self._name = name
        self._marker = marker or name
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    def execute(self, request: NodeExecutionRequest) -> NodeResult:
        self.calls += 1
        trace = request.context.metadata.setdefault("trace", [])
        assert isinstance(trace, list)
        trace.append(self._marker)
        return NodeResult.ok(request.node.id, output=f"{self._marker}:{request.node.id}")


class _FailingStep(Capability):
    kind = "step"

    @property
    def name(self) -> str:
        return "failing"

    def execute(self, request: NodeExecutionRequest) -> NodeResult:
        raise RuntimeError("kaboom")


class _ReadsPrevious(Capability):
    """Reads the result of node 'a' from the request snapshot."""

    kind = "step"

    @property
    def name(self) -> str:
        return "reader"

    def execute(self, request: NodeExecutionRequest) -> NodeResult:
        previous = request.results.get("a")
        output = previous.output if previous is not None else None
        return NodeResult.ok(request.node.id, output=f"got:{output}")


class _PlainCapability(Capability):
    """A capability that cannot run as a plan node (no execute/invoke)."""

    kind = "plain"

    @property
    def name(self) -> str:
        return "plain"


class _RecordingObserver:
    def __init__(self) -> None:
        self.events: list[ExecutionEvent] = []

    def on_event(self, event: ExecutionEvent) -> None:
        self.events.append(event)


class _InterruptAfterNode:
    def on_node_complete(
        self, context: ExecutionContext, result: NodeResult
    ) -> ExecutionControl | None:
        return ExecutionControl(action=ControlAction.INTERRUPT, reason="stop requested")


class _RetryOnce:
    def __init__(self) -> None:
        self.calls = 0

    def on_node_complete(
        self, context: ExecutionContext, result: NodeResult
    ) -> ExecutionControl | None:
        self.calls += 1
        if self.calls == 1:
            return ExecutionControl(action=ControlAction.RETRY, retry_from=result.node_id)
        return None


# --- helpers ----------------------------------------------------------------


def _make_executor(
    capabilities: list[Capability],
    *,
    observer: Any = None,
    control: Any = None,
    max_node_retries: int = 0,
) -> PlanExecutor:
    registry = PluginRegistry(config=CoreConfig(), events=EventBus())
    registry.register(CapabilityPlugin(capabilities, plugin_id="plan"))
    registry.activate_all()
    return PlanExecutor(
        registry=registry,
        observer=observer,
        control=control,
        max_node_retries=max_node_retries,
    )


def _plan(
    plan_id: str,
    nodes: list[tuple[str, str]],
    edges: list[tuple[str, str]] | None = None,
) -> ExecutionPlan:
    return ExecutionPlan(
        id=plan_id,
        nodes=tuple(
            PlanNode(id=node_id, capability=capability) for node_id, capability in nodes
        ),
        edges=tuple(
            PlanEdge(source=source, target=target) for source, target in (edges or [])
        ),
    )


def _context(request: str = "do it") -> ExecutionContext:
    return ExecutionContext(request=request)


# --- 1. a plan becomes an executable graph ----------------------------------


def test_simple_plan_becomes_executable_graph() -> None:
    step = _RecordingStep("echo")
    executor = _make_executor([step])
    plan = _plan("p1", [("a", "step:echo")])

    compiled = executor.build(plan)
    assert compiled is not None

    result = executor.run(plan, _context())
    assert result.status == "completed"
    assert result.success is True
    assert set(result.results) == {"a"}
    assert result.results["a"].output == "echo:a"


# --- 2. sequential nodes run in order ---------------------------------------


def test_two_sequential_nodes_run_in_order() -> None:
    executor = _make_executor([_RecordingStep("a"), _RecordingStep("b")])
    plan = _plan("p2", [("a", "step:a"), ("b", "step:b")], [("a", "b")])
    context = _context()

    result = executor.run(plan, context)

    assert result.status == "completed"
    assert context.metadata["trace"] == ["a", "b"]


# --- 3. dependencies are respected ------------------------------------------


def test_dependencies_are_respected() -> None:
    executor = _make_executor(
        [_RecordingStep("a"), _RecordingStep("b"), _RecordingStep("c"), _RecordingStep("d")]
    )
    plan = _plan(
        "diamond",
        [("a", "step:a"), ("b", "step:b"), ("c", "step:c"), ("d", "step:d")],
        [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
    )
    context = _context()

    result = executor.run(plan, context)
    trace = context.metadata["trace"]

    assert result.status == "completed"
    assert trace[0] == "a"
    assert trace[-1] == "d"
    assert set(trace[1:3]) == {"b", "c"}


# --- 4. capabilities are resolved through the registry ----------------------


def test_capabilities_are_resolved_through_registry() -> None:
    step = _RecordingStep("echo")
    executor = _make_executor([step])
    plan = _plan("p4", [("a", "step:echo")])

    executor.run(plan, _context())

    assert step.calls == 1
    assert executor.builder is not None


# --- 5. missing capability produces an error --------------------------------


def test_missing_capability_raises() -> None:
    executor = _make_executor([_RecordingStep("echo")])
    plan = _plan("p5", [("a", "step:ghost")])

    with pytest.raises(MissingCapabilityError):
        executor.run(plan, _context())


def test_unsupported_capability_raises() -> None:
    executor = _make_executor([_PlainCapability()])
    plan = _plan("p5b", [("a", "plain:plain")])

    with pytest.raises(UnsupportedCapabilityError):
        executor.validate(plan)


# --- 6. different plans produce different graphs ----------------------------


def test_different_plans_produce_different_graphs() -> None:
    executor = _make_executor([_RecordingStep("a"), _RecordingStep("b")])
    one = executor.build(_plan("g1", [("a", "step:a")])).get_graph()
    two = executor.build(
        _plan("g2", [("a", "step:a"), ("b", "step:b")], [("a", "b")])
    ).get_graph()

    assert set(one.nodes) != set(two.nodes)
    assert "a" in one.nodes
    assert "b" in two.nodes


# --- 7. callbacks are fired -------------------------------------------------


def test_callbacks_are_fired() -> None:
    observer = _RecordingObserver()
    executor = _make_executor([_RecordingStep("a")], observer=observer)
    plan = _plan("p7", [("a", "step:a")])

    executor.run(plan, _context())
    kinds = [event.kind for event in observer.events]

    assert ExecutionEventKind.EXECUTION_START in kinds
    assert ExecutionEventKind.NODE_START in kinds
    assert ExecutionEventKind.CAPABILITY_START in kinds
    assert ExecutionEventKind.CAPABILITY_COMPLETE in kinds
    assert ExecutionEventKind.NODE_COMPLETE in kinds
    assert ExecutionEventKind.EXECUTION_COMPLETE in kinds


# --- 8. a callback can request interruption ---------------------------------


def test_callback_can_request_interruption() -> None:
    executor = _make_executor(
        [_RecordingStep("a"), _RecordingStep("b")],
        control=_InterruptAfterNode(),
    )
    plan = _plan("p8", [("a", "step:a"), ("b", "step:b")], [("a", "b")])
    context = _context()

    result = executor.run(plan, context)

    assert result.status == "stopped"
    assert result.control.action is ControlAction.INTERRUPT
    assert set(result.results) == {"a"}
    assert context.metadata["trace"] == ["a"]


def test_callback_can_request_retry() -> None:
    step = _RecordingStep("a")
    control = _RetryOnce()
    executor = _make_executor([step], control=control, max_node_retries=1)
    plan = _plan("retry", [("a", "step:a")])

    result = executor.run(plan, _context())

    assert result.status == "completed"
    assert step.calls == 2
    assert control.calls == 2


# --- 9. a node result reaches the next node ---------------------------------


def test_node_result_reaches_next_node() -> None:
    executor = _make_executor([_RecordingStep("a", marker="A"), _ReadsPrevious()])
    plan = _plan("p9", [("a", "step:a"), ("b", "step:reader")], [("a", "b")])

    result = executor.run(plan, _context())

    assert result.status == "completed"
    assert result.results["b"].output == "got:A:a"


# --- 10. the core still works without real plugins --------------------------


def test_core_runs_without_plugins() -> None:
    core = build_core(discoverers=[])
    try:
        assert core.executor is not None
        empty = ExecutionPlan(id="empty")
        result = core.executor.run(empty, _context("nothing to do"))
        assert result.status == "completed"
        assert result.results == {}
    finally:
        core.shutdown()


# --- plan validation --------------------------------------------------------


def test_duplicate_node_ids_are_rejected() -> None:
    executor = _make_executor([_RecordingStep("a"), _RecordingStep("b")])
    plan = _plan("dup", [("a", "step:a"), ("a", "step:b")])

    with pytest.raises(InvalidPlanError):
        executor.validate(plan)


def test_unknown_edge_reference_is_rejected() -> None:
    executor = _make_executor([_RecordingStep("a")])
    plan = _plan("dangling", [("a", "step:a")], [("a", "ghost")])

    with pytest.raises(InvalidPlanError):
        executor.validate(plan)


def test_self_loop_is_rejected() -> None:
    executor = _make_executor([_RecordingStep("a")])
    plan = _plan("loop", [("a", "step:a")], [("a", "a")])

    with pytest.raises(InvalidPlanError):
        executor.validate(plan)


def test_node_without_capability_is_rejected() -> None:
    executor = _make_executor([_RecordingStep("a")])
    plan = ExecutionPlan(id="nocap", nodes=(PlanNode(id="a"),))

    with pytest.raises(InvalidPlanError):
        executor.validate(plan)


def test_invalid_capability_id_is_rejected() -> None:
    executor = _make_executor([_RecordingStep("a")])
    plan = _plan("badid", [("a", "not-a-valid-id")])

    with pytest.raises(InvalidPlanError):
        executor.validate(plan)


# --- failing capability becomes an observable failure -----------------------


def test_failing_capability_is_observable() -> None:
    observer = _RecordingObserver()
    executor = _make_executor([_FailingStep()], observer=observer)
    plan = _plan("fail", [("a", "step:failing")])

    result = executor.run(plan, _context())

    assert result.status == "failed"
    assert result.success is False
    assert result.results["a"].success is False
    assert "kaboom" in (result.results["a"].error or "")
    assert ExecutionEventKind.ERROR in [event.kind for event in observer.events]


class _RecoverableStep(Capability):
    kind = "step"

    @property
    def name(self) -> str:
        return "recoverable"

    def execute(self, request: NodeExecutionRequest) -> NodeResult:
        return NodeResult.failed(
            request.node.id, "FileNotFoundError: missing.txt", recoverable=True
        )


def test_recoverable_failure_is_flagged_on_execution() -> None:
    executor = _make_executor([_RecoverableStep()])
    plan = _plan("recoverable", [("a", "step:recoverable")])

    result = executor.run(plan, _context())

    assert result.status == "failed"
    assert result.recoverable is True
    assert result.results["a"].recoverable is True


def test_fatal_failure_is_not_recoverable() -> None:
    executor = _make_executor([_FailingStep()])
    plan = _plan("fatal", [("a", "step:failing")])

    result = executor.run(plan, _context())

    assert result.status == "failed"
    assert result.recoverable is False


def test_build_core_forwards_observer_to_executor() -> None:
    observer = _RecordingObserver()
    core = build_core(
        plugins=[CapabilityPlugin([_RecordingStep("a")], plugin_id="obs")],
        discoverers=[],
        observer=observer,
    )
    try:
        core.executor.run(_plan("obs", [("a", "step:a")]), _context())
    finally:
        core.shutdown()

    kinds = [event.kind for event in observer.events]
    assert ExecutionEventKind.EXECUTION_START in kinds
    assert ExecutionEventKind.NODE_START in kinds
    assert ExecutionEventKind.NODE_COMPLETE in kinds
