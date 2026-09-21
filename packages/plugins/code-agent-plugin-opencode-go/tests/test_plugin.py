from __future__ import annotations

from code_agent_plugin_opencode_go import OpenCodeGoPlugin
from core import CoreConfig, EventBus, LLMProvider
from core.plugins.registry import PluginRegistry


def test_plugin_registers_provider() -> None:
    registry = PluginRegistry(config=CoreConfig(), events=EventBus())
    registry.register(OpenCodeGoPlugin())
    registry.activate_all()
    try:
        provider = registry.default_capability(LLMProvider)
        assert provider is not None
        assert provider.name == "opencode-go"
    finally:
        registry.deactivate_all()


def test_provider_is_in_llm_group() -> None:
    registry = PluginRegistry(config=CoreConfig(), events=EventBus())
    registry.register(OpenCodeGoPlugin())
    registry.activate_all()
    try:
        assert [cap.name for cap in registry.capabilities_in_group("llm")] == [
            "opencode-go"
        ]
    finally:
        registry.deactivate_all()
