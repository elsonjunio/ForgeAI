"""LLM synthesizer plugin for ``core-agent``."""

from code_agent_plugin_llm_synthesizer.plugin import PLUGIN_ID, LLMSynthesizerPlugin
from code_agent_plugin_llm_synthesizer.synthesizer import (
    DEFAULT_MAX_OBSERVATION_CHARS,
    LLMSynthesizer,
    LLMSynthesizerError,
)

__all__ = [
    "DEFAULT_MAX_OBSERVATION_CHARS",
    "LLMSynthesizer",
    "LLMSynthesizerError",
    "LLMSynthesizerPlugin",
    "PLUGIN_ID",
]
