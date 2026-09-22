from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from code_agent_plugin_llm_validator import PLUGIN_ID, LLMValidatorPlugin
from core import (
    Capability,
    CoreConfig,
    EventBus,
    LLMChunkCallback,
    LLMProvider,
    LLMResponse,
    Message,
    Plugin,
    PluginSlot,
    ValidationInput,
    Validator,
)
from core.plugins.registry import PluginRegistry


class _FakeLLM(LLMProvider):
    def __init__(self) -> None:
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
        return LLMResponse(
            message=Message(role="assistant", content='{"passed": true, "issues": []}')
        )


class _ProviderPlugin(Plugin):
    id = "llm"

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def declare_capabilities(self) -> list[Capability]:
        return [self._llm]


def _registry(
    llm: LLMProvider, *, settings: dict[str, Any] | None = None
) -> PluginRegistry:
    config = CoreConfig(plugins={PLUGIN_ID: PluginSlot(settings=settings or {})})
    registry = PluginRegistry(config=config, events=EventBus())
    registry.register(_ProviderPlugin(llm))
    registry.register(LLMValidatorPlugin())
    registry.activate_all()
    return registry


def test_plugin_registers_validator() -> None:
    registry = _registry(_FakeLLM())
    try:
        validators = [
            capability
            for capability in registry.capabilities(Validator)
            if isinstance(capability, Validator)
        ]
        assert [validator.name for validator in validators] == ["llm-validator"]

        result = validators[0].validate(ValidationInput(request="do it"))
        assert result.passed is True
    finally:
        registry.deactivate_all()


def test_plugin_reads_system_prompt_setting() -> None:
    llm = _FakeLLM()
    registry = _registry(llm, settings={"system_prompt": "custom verdict"})
    try:
        validators = [
            capability
            for capability in registry.capabilities(Validator)
            if isinstance(capability, Validator)
        ]
        validators[0].validate(ValidationInput(request="do it"))
    finally:
        registry.deactivate_all()

    assert llm.calls[0][0].content == "custom verdict"
