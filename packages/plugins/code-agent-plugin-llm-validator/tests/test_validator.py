from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import pytest

from code_agent_plugin_llm_validator import LLMValidator, LLMValidatorError
from core import (
    Capability,
    CoreConfig,
    EventBus,
    LLMChunkCallback,
    LLMProvider,
    LLMResponse,
    LLMUsage,
    Message,
    MissingCapabilityError,
    Observation,
    Plugin,
    Tool,
    ToolContract,
    ToolResult,
    ValidationInput,
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
            usage=LLMUsage(prompt_tokens=4, completion_tokens=5, total_tokens=9),
        )


class _FakeTool(Tool):
    @property
    def contract(self) -> ToolContract:
        return ToolContract(name="echo", description="fake tool")

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


def _data(**overrides: Any) -> ValidationInput:
    base: dict[str, Any] = {
        "request": "resuma os docs",
        "observations": (Observation(node_id="n1", output="a.txt"),),
    }
    base.update(overrides)
    return ValidationInput(**base)


def test_validator_passes() -> None:
    llm = _FakeLLM('{"passed": true, "issues": []}')
    validator = LLMValidator(source=_registry(llm, _FakeTool()))

    result = validator.validate(_data(success=True))

    assert result.passed is True
    assert result.messages == ()
    assert result.metadata["provider"] == "scripted"
    prompt = llm.calls[0][-1].content
    assert "resuma os docs" in prompt
    assert "Run completed without a fatal failure: True" in prompt


def test_validator_reports_issues() -> None:
    llm = _FakeLLM('{"passed": false, "issues": ["faltou o README", "sem testes"]}')
    result = LLMValidator(source=_registry(llm, _FakeTool())).validate(_data())

    assert result.passed is False
    assert result.messages == ("faltou o README", "sem testes")


def test_validator_handles_fenced_json() -> None:
    llm = _FakeLLM('```json\n{"passed": true, "issues": []}\n```')
    result = LLMValidator(source=_registry(llm, _FakeTool())).validate(_data())
    assert result.passed is True


def test_validator_includes_checkpoint_and_scratchpad() -> None:
    llm = _FakeLLM('{"passed": true}')
    validator = LLMValidator(source=_registry(llm, _FakeTool()))

    validator.validate(_data(checkpoint="resumo anterior", scratchpad="- tool:x -> ok"))

    prompt = llm.calls[0][-1].content
    assert "resumo anterior" in prompt
    assert "- tool:x -> ok" in prompt


def test_validator_invalid_json_raises() -> None:
    with pytest.raises(LLMValidatorError):
        LLMValidator(source=_registry(_FakeLLM("not json"))).validate(_data())


def test_validator_rejects_bad_issues_type() -> None:
    with pytest.raises(LLMValidatorError):
        LLMValidator(
            source=_registry(_FakeLLM('{"passed": false, "issues": "nope"}'))
        ).validate(_data())


def test_validator_missing_llm_raises() -> None:
    with pytest.raises(MissingCapabilityError):
        LLMValidator(source=_registry(_FakeTool())).validate(_data())


def test_validator_reports_usage() -> None:
    result = LLMValidator(source=_registry(_UsageLLM('{"passed": true}'))).validate(
        _data()
    )
    assert result.usage == LLMUsage(
        prompt_tokens=4, completion_tokens=5, total_tokens=9
    )


def test_validator_rejects_invalid_max_observation_chars() -> None:
    with pytest.raises(ValueError):
        LLMValidator(source=_registry(), max_observation_chars=0)
