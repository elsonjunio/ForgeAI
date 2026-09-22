from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from typing import Any

from core import (
    CapabilityDescriptor,
    ControlAction,
    ControlCallback,
    ExecutionContext,
    ExecutionControl,
    ExecutionEvent,
    ExecutionEventKind,
    ExecutionObserver,
    ExecutionPlan,
    InteractionProvider,
    InteractionRequest,
    InteractionResponse,
    LLMChunk,
    LLMChunkCallback,
    LLMProvider,
    LLMResponse,
    Message,
    NodeExecutionRequest,
    NodeResult,
    Observation,
    Planner,
    PlanningRequest,
    PlanningResult,
    PlanNode,
    Tool,
    ToolContract,
    ToolResult,
    build_core,
)
from core.contracts import plan as plan_module
from tests.support.capabilities import (
    CapabilityPlugin,
    FakeLLMProvider,
    FakeTool,
)

# --- 1. a planner can produce an ExecutionPlan ------------------------------


class _FakePlanner(Planner):
    @property
    def name(self) -> str:
        return "fake-planner"

    def plan(self, request: PlanningRequest) -> PlanningResult:
        node = PlanNode(id="n1", capability="tool:echo", description="echo")
        return PlanningResult(
            plan=ExecutionPlan(id="plan-1", nodes=(node,)),
            rationale="single step",
        )


def test_planner_produces_execution_plan() -> None:
    request = PlanningRequest(
        request="do it",
        context=ExecutionContext(request="do it"),
    )
    result = _FakePlanner().plan(request)

    assert isinstance(result.plan, ExecutionPlan)
    assert result.plan.id == "plan-1"
    assert result.plan.node_ids == ("n1",)
    assert result.plan.node("n1") is not None
    assert result.plan.node("missing") is None


# --- 2. the ExecutionPlan does not depend on LangGraph ----------------------


def test_execution_plan_has_no_langgraph_dependency() -> None:
    source = inspect.getsource(plan_module)
    assert "langgraph" not in source
    assert "langchain" not in source


# --- 3. ExecutionContext accepts externally provided prior context ----------


def test_execution_context_accepts_external_history() -> None:
    history = (
        Message(role="user", content="previous turn"),
        Message(role="assistant", content="ok"),
    )
    context = ExecutionContext(request="next", history=history)
    request = PlanningRequest(request="next", context=context)

    assert context.history == history
    assert request.history == history


def test_planning_request_exposes_descriptors_from_context() -> None:
    descriptor = CapabilityDescriptor(id="tool:echo", name="echo", kind="tool")
    context = ExecutionContext(request="x", capabilities=(descriptor,))
    request = PlanningRequest(request="x", context=context)

    assert request.capabilities == (descriptor,)


# --- 4. callbacks can observe the execution ---------------------------------


class _RecordingObserver:
    def __init__(self) -> None:
        self.events: list[ExecutionEvent] = []

    def on_event(self, event: ExecutionEvent) -> None:
        self.events.append(event)


def test_observer_can_observe_execution() -> None:
    observer = _RecordingObserver()
    assert isinstance(observer, ExecutionObserver)

    observer.on_event(ExecutionEvent(kind=ExecutionEventKind.EXECUTION_START))
    observer.on_event(
        ExecutionEvent(kind=ExecutionEventKind.NODE_COMPLETE, node_id="n1")
    )

    assert [event.kind for event in observer.events] == [
        ExecutionEventKind.EXECUTION_START,
        ExecutionEventKind.NODE_COMPLETE,
    ]
    assert observer.events[1].node_id == "n1"


# --- 5. callbacks can request control ---------------------------------------


class _RetryOnFailure:
    def on_node_complete(
        self, context: ExecutionContext, result: NodeResult
    ) -> ExecutionControl | None:
        if result.success:
            return None
        return ExecutionControl(
            action=ControlAction.RETRY, retry_from=result.node_id, reason="failed"
        )


def test_callback_can_request_control() -> None:
    callback = _RetryOnFailure()
    assert isinstance(callback, ControlCallback)
    context = ExecutionContext(request="x")

    control = callback.on_node_complete(context, NodeResult.failed("n1", "boom"))
    assert control is not None
    assert control.action is ControlAction.RETRY
    assert control.retry_from == "n1"
    assert control.should_continue is False

    assert callback.on_node_complete(context, NodeResult.ok("n1")) is None
    assert ExecutionControl().should_continue is True


# --- 6. InteractionProvider is only a contract ------------------------------


class _FakeInteraction:
    def request(self, request: InteractionRequest) -> InteractionResponse:
        return InteractionResponse(approved=True, value=request.default)


def test_interaction_provider_is_a_contract() -> None:
    provider = _FakeInteraction()
    assert isinstance(provider, InteractionProvider)

    response = provider.request(
        InteractionRequest(kind="confirm", message="Continue?", default="y")
    )
    assert response.approved is True
    assert response.value == "y"


# --- 7. LLMProvider allows a chunk callback ---------------------------------


class _StreamingLLM(LLMProvider):
    @property
    def name(self) -> str:
        return "streaming"

    def complete(
        self,
        messages: Sequence[Message],
        *,
        on_chunk: LLMChunkCallback | None = None,
        **options: Any,
    ) -> LLMResponse:
        parts = ("hel", "lo")
        for index, part in enumerate(parts):
            if on_chunk is not None:
                on_chunk(LLMChunk(content=part, index=index))
        return LLMResponse(message=Message(role="assistant", content="".join(parts)))


def test_llm_provider_streams_chunks_via_callback() -> None:
    chunks: list[LLMChunk] = []
    response = _StreamingLLM().complete(
        [Message(role="user", content="hi")], on_chunk=chunks.append
    )

    assert [chunk.content for chunk in chunks] == ["hel", "lo"]
    assert response.content == "hello"
    assert response.message.role == "assistant"


# --- 8. the core still works with zero plugins ------------------------------


class _ParamTool(Tool):
    @property
    def contract(self) -> ToolContract:
        return ToolContract(
            name="param",
            description="tool with parameters",
            parameters={"type": "object", "properties": {"x": {"type": "string"}}},
        )

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        return ToolResult(output="ok")


def test_core_runs_with_zero_plugins() -> None:
    core = build_core(discoverers=[])
    try:
        assert core.node_ids == ()
        assert core.registry.default_capability(Planner) is None
        assert core.registry.capability_descriptors() == []
    finally:
        core.shutdown()


def test_registry_exposes_capability_descriptors() -> None:
    core = build_core(
        plugins=[CapabilityPlugin([_ParamTool()], plugin_id="caps")], discoverers=[]
    )
    try:
        descriptors = core.registry.capability_descriptors("tool")
    finally:
        core.shutdown()

    assert [descriptor.id for descriptor in descriptors] == ["tool:param"]
    assert descriptors[0].parameters["properties"] == {"x": {"type": "string"}}


def test_executable_capabilities_filter() -> None:
    tool = FakeTool("echo")
    llm = FakeLLMProvider("llm")
    core = build_core(
        plugins=[CapabilityPlugin([tool, llm], plugin_id="caps")], discoverers=[]
    )
    try:
        assert [cap.name for cap in core.registry.executable_capabilities()] == ["echo"]
        assert [
            descriptor.id
            for descriptor in core.registry.executable_capability_descriptors()
        ] == ["tool:echo"]
    finally:
        core.shutdown()


# --- 9. recovery hints travel from tools to observations ---------------------


class _RecoverableTool(Tool):
    @property
    def contract(self) -> ToolContract:
        return ToolContract(name="recoverable", description="fails recoverably")

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        return ToolResult(
            output="FileNotFoundError: missing.txt",
            is_error=True,
            recoverable=True,
        )


def test_tool_result_recoverable_propagates_to_node_result() -> None:
    request = NodeExecutionRequest(
        node=PlanNode(id="n1", capability="tool:recoverable"),
        context=ExecutionContext(request="x"),
    )

    result = _RecoverableTool().execute(request)

    assert result.success is False
    assert result.error == "FileNotFoundError: missing.txt"
    assert result.recoverable is True


def test_observation_defaults_and_parameters() -> None:
    default = Observation(node_id="n1")
    assert default.parameters == {}
    assert default.role == "result"

    carried = Observation(
        node_id="n1",
        capability="tool:fs.read_file",
        success=False,
        output="FileNotFoundError: missing.txt",
        parameters={"path": "missing.txt"},
    )
    assert carried.parameters == {"path": "missing.txt"}


def test_merge_usage_sums_and_ignores_missing() -> None:
    from core import LLMUsage, merge_usage

    assert merge_usage() is None
    assert merge_usage(None, None) is None

    first = LLMUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    second = LLMUsage(prompt_tokens=1, completion_tokens=None, total_tokens=1)

    assert merge_usage(first, second, None) == LLMUsage(
        prompt_tokens=11, completion_tokens=5, total_tokens=16
    )


def test_validation_input_defaults_and_whole_outcome() -> None:
    from core import ValidationInput, ValidationResult

    default = ValidationInput(request="do it")
    assert default.success is True
    assert default.observations == ()
    assert default.checkpoint == ""
    assert default.scratchpad == ""

    carried = ValidationInput(
        request="do it",
        success=False,
        observations=(Observation(node_id="n1", output="ok"),),
        checkpoint="summary",
        scratchpad="- tool:x -> ok",
    )
    assert carried.success is False
    assert carried.observations[0].node_id == "n1"

    result = ValidationResult(passed=False, messages=("faltou X",))
    assert result.messages == ("faltou X",)
    assert result.usage is None
