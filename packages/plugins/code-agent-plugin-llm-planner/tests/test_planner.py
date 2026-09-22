from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import pytest

from code_agent_plugin_llm_planner import LLMPlanner, LLMPlannerError
from core import (
    Capability,
    CoreConfig,
    EventBus,
    ExecutionContext,
    LLMChunkCallback,
    LLMProvider,
    LLMResponse,
    LLMUsage,
    Message,
    MissingCapabilityError,
    Observation,
    PlanningRequest,
    Plugin,
    Tool,
    ToolContract,
    ToolResult,
)
from core.plugins.registry import PluginRegistry


class _FakeLLM(LLMProvider):
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[list[Message]] = []

    @property
    def name(self) -> str:
        return "scripted"

    def complete(
        self,
        messages: Sequence[Message],
        *,
        on_chunk: LLMChunkCallback | None = None,
        **options: Any,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        return LLMResponse(message=Message(role="assistant", content=self._content))


class _UsageLLM(_FakeLLM):
    def __init__(self) -> None:
        super().__init__('{"nodes":[{"id":"n1","capability":"tool:echo"}]}')

    def complete(
        self,
        messages: Sequence[Message],
        *,
        on_chunk: LLMChunkCallback | None = None,
        **options: Any,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        return LLMResponse(
            message=Message(role="assistant", content=self._content),
            usage=LLMUsage(prompt_tokens=3, completion_tokens=4, total_tokens=7),
        )


class _FakeTool(Tool):
    def __init__(self, name: str = "echo") -> None:
        self._name = name

    @property
    def contract(self) -> ToolContract:
        return ToolContract(name=self._name, description="fake tool")

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        return ToolResult(output="ok")


class _FakePlugin(Plugin):
    id = "fakes"

    def __init__(self, capabilities: Iterable[Capability]) -> None:
        self._capabilities = list(capabilities)

    def declare_capabilities(self) -> list[Capability]:
        return list(self._capabilities)


def _registry(*capabilities: Capability) -> PluginRegistry:
    registry = PluginRegistry(config=CoreConfig(), events=EventBus())
    registry.register(_FakePlugin(capabilities))
    registry.activate_all()
    return registry


def _request() -> PlanningRequest:
    return PlanningRequest(request="do it", context=ExecutionContext(request="do it"))


def test_planner_parses_json_plan() -> None:
    llm = _FakeLLM('{"id":"p1","nodes":[{"id":"n1","capability":"tool:echo"}],"edges":[]}')
    planner = LLMPlanner(source=_registry(llm, _FakeTool()))

    result = planner.plan(_request())

    assert result.plan.id == "p1"
    assert result.plan.node_ids == ("n1",)
    node = result.plan.node("n1")
    assert node is not None
    assert node.capability == "tool:echo"


def test_planner_handles_fenced_json() -> None:
    llm = _FakeLLM('```json\n{"nodes":[{"id":"n1","capability":"tool:echo"}]}\n```')
    result = LLMPlanner(source=_registry(llm, _FakeTool())).plan(_request())
    assert result.plan.node_ids == ("n1",)


def test_planner_rejects_too_many_nodes() -> None:
    llm = _FakeLLM(
        '{"nodes":[{"id":"n1","capability":"tool:a"},'
        '{"id":"n2","capability":"tool:b"}],"edges":[]}'
    )
    planner = LLMPlanner(
        source=_registry(llm, _FakeTool("a"), _FakeTool("b")), max_nodes=1
    )
    with pytest.raises(LLMPlannerError):
        planner.plan(_request())


def test_planner_prompt_includes_node_limit() -> None:
    llm = _FakeLLM('{"nodes":[]}')
    LLMPlanner(source=_registry(llm), max_nodes=3).plan(_request())
    assert "Node limit: 3" in llm.calls[0][-1].content


def test_planner_request_max_nodes_overrides_setting() -> None:
    llm = _FakeLLM(
        '{"nodes":[{"id":"n1","capability":"tool:a"},'
        '{"id":"n2","capability":"tool:b"}]}'
    )
    planner = LLMPlanner(
        source=_registry(llm, _FakeTool("a"), _FakeTool("b")), max_nodes=4
    )
    request = PlanningRequest(
        request="x", context=ExecutionContext(request="x"), max_nodes=1
    )
    with pytest.raises(LLMPlannerError):
        planner.plan(request)


def test_planner_prompt_includes_history_and_scratchpad() -> None:
    llm = _FakeLLM('{"nodes":[{"id":"n1","capability":"tool:echo"}]}')
    planner = LLMPlanner(source=_registry(llm, _FakeTool()))
    context = ExecutionContext(
        request="x", history=(Message(role="user", content="turno anterior"),)
    )
    request = PlanningRequest(
        request="x", context=context, scratchpad="- tool:echo -> ok: hi"
    )

    planner.plan(request)

    prompt = llm.calls[0][-1].content
    assert "Conversation history" in prompt
    assert "turno anterior" in prompt
    assert "Progress so far" in prompt
    assert "- tool:echo -> ok: hi" in prompt


def test_planner_reports_usage() -> None:
    result = LLMPlanner(source=_registry(_UsageLLM(), _FakeTool())).plan(_request())
    assert result.usage == LLMUsage(
        prompt_tokens=3, completion_tokens=4, total_tokens=7
    )


def test_planner_empty_plan() -> None:
    llm = _FakeLLM('{"nodes":[]}')
    result = LLMPlanner(source=_registry(llm)).plan(_request())
    assert result.plan.nodes == ()


def test_planner_invalid_json_raises() -> None:
    llm = _FakeLLM("this is not json")
    with pytest.raises(LLMPlannerError):
        LLMPlanner(source=_registry(llm)).plan(_request())


def test_planner_missing_llm_raises() -> None:
    planner = LLMPlanner(source=_registry())
    with pytest.raises(MissingCapabilityError):
        planner.plan(_request())


def test_planner_rejects_non_executable_capability() -> None:
    llm = _FakeLLM('{"nodes":[{"id":"n1","capability":"llm:scripted"}]}')
    planner = LLMPlanner(source=_registry(llm))
    with pytest.raises(LLMPlannerError):
        planner.plan(_request())


def test_planner_parses_needs_more_info() -> None:
    llm = _FakeLLM(
        '{"needs_more_info": true, "nodes":[{"id":"n1","capability":"tool:echo"}]}'
    )
    result = LLMPlanner(source=_registry(llm, _FakeTool())).plan(_request())
    assert result.needs_more_info is True


def test_planner_prompt_includes_observations() -> None:
    llm = _FakeLLM('{"nodes":[{"id":"n1","capability":"tool:echo"}]}')
    planner = LLMPlanner(source=_registry(llm, _FakeTool()))
    request = PlanningRequest(
        request="resuma os docs",
        context=ExecutionContext(request="resuma os docs"),
        observations=(
            Observation(node_id="list", capability="tool:echo", output="a.txt\nb.txt"),
        ),
    )

    planner.plan(request)

    prompt = llm.calls[0][-1].content
    assert "Information already gathered" in prompt
    assert "a.txt" in prompt


def test_planner_parses_compaction_request() -> None:
    llm = _FakeLLM(
        '{"nodes":[{"id":"n1","capability":"tool:echo"}],'
        ' "compaction":{"keep_last":2,"reason":"too many steps"}}'
    )
    result = LLMPlanner(source=_registry(llm, _FakeTool())).plan(_request())

    assert result.compaction is not None
    assert result.compaction.keep_last == 2
    assert result.compaction.reason == "too many steps"


def test_planner_without_compaction_has_none() -> None:
    llm = _FakeLLM('{"nodes":[{"id":"n1","capability":"tool:echo"}]}')
    result = LLMPlanner(source=_registry(llm, _FakeTool())).plan(_request())
    assert result.compaction is None


def test_planner_invalid_compaction_raises() -> None:
    llm = _FakeLLM(
        '{"nodes":[{"id":"n1","capability":"tool:echo"}],'
        ' "compaction":{"keep_last":-1}}'
    )
    with pytest.raises(LLMPlannerError):
        LLMPlanner(source=_registry(llm, _FakeTool())).plan(_request())


def test_planner_prompt_includes_synthesizers_and_checkpoint() -> None:
    from core import CapabilityDescriptor

    llm = _FakeLLM('{"nodes":[{"id":"n1","capability":"tool:echo"}]}')
    planner = LLMPlanner(source=_registry(llm, _FakeTool()))
    request = PlanningRequest(
        request="resuma os docs",
        context=ExecutionContext(request="resuma os docs"),
        synthesizers=(
            CapabilityDescriptor(
                id="synthesizer:llm-synthesizer",
                name="llm-synthesizer",
                kind="synthesizer",
            ),
        ),
        checkpoint="prior summary",
    )

    planner.plan(request)

    prompt = llm.calls[0][-1].content
    assert "Available synthesizers" in prompt
    assert "synthesizer:llm-synthesizer" in prompt
    assert "Previous checkpoint" in prompt
    assert "prior summary" in prompt


def test_planner_marks_failed_observations_with_params() -> None:
    llm = _FakeLLM('{"nodes":[{"id":"n1","capability":"tool:echo"}]}')
    planner = LLMPlanner(source=_registry(llm, _FakeTool()))
    request = PlanningRequest(
        request="resuma os docs",
        context=ExecutionContext(request="resuma os docs"),
        observations=(
            Observation(
                node_id="read",
                capability="tool:fs.read_file",
                success=False,
                output="FileNotFoundError: README.md",
                parameters={"path": "README.md"},
            ),
        ),
    )

    planner.plan(request)

    prompt = llm.calls[0][-1].content
    assert "[FAILED]" in prompt
    assert '"path": "README.md"' in prompt
    assert "FileNotFoundError" in prompt


def test_planner_prompt_includes_execution_context() -> None:
    llm = _FakeLLM('{"nodes":[{"id":"n1","capability":"tool:echo"}]}')
    planner = LLMPlanner(source=_registry(llm, _FakeTool()))
    request = PlanningRequest(
        request="resuma os docs",
        context=ExecutionContext(
            request="resuma os docs",
            metadata={"working_directory": "/repo"},
        ),
    )

    planner.plan(request)

    prompt = llm.calls[0][-1].content
    assert "Execution context" in prompt
    assert "working_directory: /repo" in prompt
