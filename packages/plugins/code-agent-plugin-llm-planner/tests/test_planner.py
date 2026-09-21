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


def test_planner_limits_nodes() -> None:
    llm = _FakeLLM(
        '{"nodes":[{"id":"n1","capability":"tool:a"},'
        '{"id":"n2","capability":"tool:b"}],"edges":[]}'
    )
    result = LLMPlanner(
        source=_registry(llm, _FakeTool("a"), _FakeTool("b")), max_nodes=1
    ).plan(_request())
    assert result.plan.node_ids == ("n1",)


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
