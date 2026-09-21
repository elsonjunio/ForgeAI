from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from code_agent_plugin_llm_planner import LLMPlannerPlugin
from core import (
    Capability,
    CoreContainer,
    LLMChunkCallback,
    LLMProvider,
    LLMResponse,
    Message,
    Plugin,
    Tool,
    ToolContract,
    ToolResult,
    build_core,
)
from forge_cli.commands import handle_command
from forge_cli.session import ChatSession


class _EchoLLM(LLMProvider):
    @property
    def name(self) -> str:
        return "echo"

    def complete(
        self,
        messages: Sequence[Message],
        *,
        on_chunk: LLMChunkCallback | None = None,
        **options: Any,
    ) -> LLMResponse:
        return LLMResponse(message=Message(role="assistant", content="echo"))


class _FakePlugin(Plugin):
    id = "fake"
    version = "1.0.0"
    description = "fake plugin"

    def declare_capabilities(self) -> list[Capability]:
        return [_EchoLLM()]


def _core() -> CoreContainer:
    return build_core(plugins=[_FakePlugin()], discoverers=[])


def test_help_and_exit() -> None:
    core = _core()
    try:
        session = ChatSession(_EchoLLM(), stream=False)
        help_result = handle_command("/help", core=core, session=session)
        assert help_result is not None
        assert help_result.output
        assert help_result.should_exit is False

        exit_result = handle_command("/exit", core=core, session=session)
        assert exit_result is not None
        assert exit_result.should_exit is True
    finally:
        core.shutdown()


def test_capabilities_and_plugins_commands() -> None:
    core = _core()
    try:
        capabilities = handle_command("/capabilities", core=core, session=None)
        assert capabilities is not None
        assert any("llm:echo" in line for line in capabilities.output)

        plugins = handle_command("/plugins", core=core, session=None)
        assert plugins is not None
        assert any("fake" in line for line in plugins.output)

        providers = handle_command("/providers", core=core, session=None)
        assert providers is not None
        assert any("echo" in line for line in providers.output)
    finally:
        core.shutdown()


def test_non_command_returns_none() -> None:
    core = _core()
    try:
        assert handle_command("olá", core=core, session=None) is None
    finally:
        core.shutdown()


def test_chat_commands_without_session() -> None:
    core = _core()
    try:
        result = handle_command("/clear", core=core, session=None)
        assert result is not None
        assert "sem sessão" in result.output[0]
    finally:
        core.shutdown()


def test_plan_without_planner() -> None:
    core = _core()
    try:
        result = handle_command("/plan fazer algo", core=core, session=None)
        assert result is not None
        assert any("Planner" in line for line in result.output)
    finally:
        core.shutdown()


class _PlanLLM(LLMProvider):
    @property
    def name(self) -> str:
        return "plan-llm"

    def complete(
        self,
        messages: Sequence[Message],
        *,
        on_chunk: LLMChunkCallback | None = None,
        **options: Any,
    ) -> LLMResponse:
        content = (
            '{"nodes":[{"id":"n1","capability":"tool:echo",'
            '"description":"echo"}],"edges":[]}'
        )
        return LLMResponse(message=Message(role="assistant", content=content))


class _EchoTool(Tool):
    @property
    def contract(self) -> ToolContract:
        return ToolContract(name="echo", description="echo")

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        return ToolResult(output="ok")


class _RunFakesPlugin(Plugin):
    id = "run-fakes"

    def declare_capabilities(self) -> list[Capability]:
        return [_PlanLLM(), _EchoTool()]


def test_run_executes_plan_end_to_end() -> None:
    core = build_core(plugins=[_RunFakesPlugin(), LLMPlannerPlugin()], discoverers=[])
    try:
        result = handle_command("/run fazer algo", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "status: completed" in text
        assert "n1: ok" in text
    finally:
        core.shutdown()
