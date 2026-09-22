from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import pytest

from code_agent_plugin_llm_synthesizer import LLMSynthesizer, LLMSynthesizerError
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
    SynthesisRequest,
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
    @property
    def contract(self) -> ToolContract:
        return ToolContract(name="echo", description="fake tool")

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        return ToolResult(output="ok")


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
            usage=LLMUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )


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


def test_synthesizer_returns_answer() -> None:
    llm = _FakeLLM("the answer")
    synthesizer = LLMSynthesizer(source=_registry(llm, _FakeTool()))

    result = synthesizer.synthesize(
        SynthesisRequest(
            request="resuma os docs",
            observations=(Observation(node_id="n1", output="a.txt"),),
        )
    )

    assert result.text == "the answer"
    assert result.metadata["mode"] == "answer"
    prompt = llm.calls[0][-1].content
    assert "Mode: answer" in prompt
    assert "resuma os docs" in prompt
    assert "a.txt" in prompt


def test_synthesizer_compact_mode_includes_checkpoint() -> None:
    llm = _FakeLLM("compressed")
    synthesizer = LLMSynthesizer(source=_registry(llm))

    result = synthesizer.synthesize(
        SynthesisRequest(
            request="do it",
            mode="compact",
            checkpoint="older summary",
            observations=(Observation(node_id="n2", output="step-2"),),
        )
    )

    assert result.text == "compressed"
    assert result.metadata["mode"] == "compact"
    prompt = llm.calls[0][-1].content
    assert "Mode: compact" in prompt
    assert "older summary" in prompt
    assert "step-2" in prompt


def test_synthesizer_truncates_large_observations() -> None:
    llm = _FakeLLM("ok")
    synthesizer = LLMSynthesizer(source=_registry(llm), max_observation_chars=5)

    synthesizer.synthesize(
        SynthesisRequest(
            request="do it",
            observations=(Observation(node_id="n1", output="abcdefghij"),),
        )
    )

    prompt = llm.calls[0][-1].content
    assert "abcde…" in prompt
    assert "abcdefghij" not in prompt


def test_synthesizer_marks_failed_observations() -> None:
    llm = _FakeLLM("ok")
    synthesizer = LLMSynthesizer(source=_registry(llm))

    synthesizer.synthesize(
        SynthesisRequest(
            request="do it",
            observations=(Observation(node_id="n1", success=False, output="boom"),),
        )
    )

    assert "[failed]" in llm.calls[0][-1].content


def test_synthesizer_empty_response_raises() -> None:
    llm = _FakeLLM("   ")
    synthesizer = LLMSynthesizer(source=_registry(llm))
    with pytest.raises(LLMSynthesizerError):
        synthesizer.synthesize(SynthesisRequest(request="do it"))


def test_synthesizer_missing_llm_raises() -> None:
    synthesizer = LLMSynthesizer(source=_registry(_FakeTool()))
    with pytest.raises(MissingCapabilityError):
        synthesizer.synthesize(SynthesisRequest(request="do it"))


def test_synthesizer_selects_named_provider() -> None:
    llm = _FakeLLM("ok")
    registry = _registry(llm)
    assert LLMSynthesizer(source=registry, provider_name="scripted").synthesize(
        SynthesisRequest(request="do it")
    ).text == "ok"
    with pytest.raises(MissingCapabilityError):
        LLMSynthesizer(source=registry, provider_name="missing").synthesize(
            SynthesisRequest(request="do it")
        )


def test_synthesizer_rejects_invalid_max_observation_chars() -> None:
    with pytest.raises(ValueError):
        LLMSynthesizer(source=_registry(), max_observation_chars=0)


def test_synthesizer_reports_usage() -> None:
    result = LLMSynthesizer(source=_registry(_UsageLLM("ok"))).synthesize(
        SynthesisRequest(request="do it")
    )
    assert result.usage == LLMUsage(
        prompt_tokens=1, completion_tokens=2, total_tokens=3
    )
