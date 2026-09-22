"""The LLM synthesizer plugin: exposes :class:`LLMSynthesizer` to the core."""

from __future__ import annotations

from code_agent_plugin_llm_synthesizer.synthesizer import (
    DEFAULT_MAX_OBSERVATION_CHARS,
    LLMSynthesizer,
)
from core import Capability, Plugin, PluginContext
from core.contracts.registry import CapabilitySource

PLUGIN_ID = "code-agent-plugin-llm-synthesizer"


class LLMSynthesizerPlugin(Plugin):
    """Contributes an :class:`LLMSynthesizer`.

    Settings (``CoreConfig.plugins["code-agent-plugin-llm-synthesizer"].settings``):

    * ``provider`` (optional: name of the LLM provider; default = default one)
    * ``system_prompt`` (optional override)
    * ``max_observation_chars`` (default ``2000``)
    """

    id = PLUGIN_ID
    version = "0.1.0"
    description = "LLM-based synthesizer that produces answers and checkpoints."
    author = "ForgeAI"

    def __init__(
        self,
        *,
        provider: str | None = None,
        system_prompt: str | None = None,
        max_observation_chars: int = DEFAULT_MAX_OBSERVATION_CHARS,
    ) -> None:
        self._provider = provider
        self._system_prompt = system_prompt
        self._max_observation_chars = max_observation_chars
        self._source: CapabilitySource | None = None

    def initialize(self, context: PluginContext) -> None:
        self._source = context.capability_source
        self._provider = context.get_setting("provider", self._provider)
        self._system_prompt = context.get_setting("system_prompt", self._system_prompt)
        self._max_observation_chars = int(
            context.get_setting("max_observation_chars", self._max_observation_chars)
        )

    def declare_capabilities(self) -> list[Capability]:
        assert self._source is not None
        return [
            LLMSynthesizer(
                source=self._source,
                provider_name=self._provider,
                system_prompt=self._system_prompt,
                max_observation_chars=self._max_observation_chars,
            )
        ]
