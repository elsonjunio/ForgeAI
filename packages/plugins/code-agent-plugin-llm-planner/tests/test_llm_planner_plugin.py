from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from code_agent_plugin_llm_planner import LLMPlannerPlugin
from core import (
    Capability,
    CoreConfig,
    EventBus,
    ExecutionContext,
    LLMChunkCallback,
    LLMProvider,
    LLMResponse,
    Message,
    Planner,
    PlanningRequest,
    Plugin,
    Tool,
    ToolContract,
    ToolResult,
)
from core.plugins.registry import PluginRegistry


class _FakeLLM(LLMProvider):
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
        content = '{"nodes":[{"id":"n1","capability":"tool:echo"}]}'
        return LLMResponse(message=Message(role="assistant", content=content))


class _EchoTool(Tool):
    @property
    def contract(self) -> ToolContract:
        return ToolContract(name="echo", description="echo")

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        return ToolResult(output="ok")


class _ProviderPlugin(Plugin):
    id = "llm"

    def declare_capabilities(self) -> list[Capability]:
        return [_FakeLLM(), _EchoTool()]


def test_plugin_registers_planner() -> None:
    registry = PluginRegistry(config=CoreConfig(), events=EventBus())
    registry.register(_ProviderPlugin())
    registry.register(LLMPlannerPlugin())
    registry.activate_all()
    try:
        planner = registry.default_capability(Planner)
        assert isinstance(planner, Planner)
        assert planner.name == "llm-planner"

        result = planner.plan(
            PlanningRequest(request="x", context=ExecutionContext(request="x"))
        )
        assert result.plan.node_ids == ("n1",)
    finally:
        registry.deactivate_all()
