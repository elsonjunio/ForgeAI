from __future__ import annotations

from typing import Any, cast

import pytest

from core.config.schema import CoreConfig
from core.contracts.analyzer import CodeAnalyzer
from core.contracts.capability import Capability
from core.contracts.llm import LLMProvider
from core.contracts.tool import Tool
from core.errors import (
    AmbiguousCapabilityError,
    CapabilityError,
    DiscoveryError,
    DuplicateCapabilityError,
    DuplicatePluginError,
    InvalidPluginError,
)
from core.events.bus import EventBus
from core.plugins.base import Plugin, PluginMetadata
from core.plugins.discovery import (
    DEFAULT_ENTRY_POINT_GROUP,
    EntryPointDiscoverer,
    discover_plugins,
)
from core.plugins.registry import PluginRegistry
from core.runtime.bootstrap import build_core
from tests.support.capabilities import (
    BadCapabilityPlugin,
    CapabilityPlugin,
    DynamicCapabilityPlugin,
    FakeAnalyzer,
    FakeDiscoverer,
    FakeLLMProvider,
    FakeTool,
    RecordingPlugin,
)
from tests.support.plugins import EchoNodePlugin, LifecyclePlugin, NoopPlugin


@pytest.fixture
def registry(bus: EventBus) -> PluginRegistry:
    return PluginRegistry(config=CoreConfig(), events=bus)


# --- zero plugins -----------------------------------------------------------


def test_zero_plugins_has_no_capabilities() -> None:
    core = build_core(discoverers=[])
    assert core.node_ids == ()
    assert core.registry.capabilities(LLMProvider) == []
    assert core.registry.default_capability(LLMProvider) is None
    core.shutdown()


# --- identity / metadata ----------------------------------------------------


def test_plugin_metadata_defaults() -> None:
    metadata = NoopPlugin().metadata()
    assert isinstance(metadata, PluginMetadata)
    assert metadata.id == "noop"
    assert metadata.version == "0.1.0"
    assert metadata.name == "NoopPlugin"


def test_registry_exposes_plugin_metadata(registry: PluginRegistry) -> None:
    registry.register(NoopPlugin())
    metadata = registry.metadata("noop")
    assert metadata is not None
    assert metadata.id == "noop"
    assert registry.metadata("ghost") is None


# --- registration and capability queries ------------------------------------


def test_register_and_query_capabilities(registry: PluginRegistry) -> None:
    provider = FakeLLMProvider("alpha")
    registry.register(CapabilityPlugin([provider]))
    registry.activate_all()

    assert registry.capabilities(LLMProvider) == [provider]
    assert registry.capability(LLMProvider, "alpha") is provider
    assert registry.has_capability("llm")
    assert registry.capability_names("llm") == ["alpha"]


def test_multiple_plugins_same_capability(registry: PluginRegistry) -> None:
    first = FakeLLMProvider("a")
    second = FakeLLMProvider("b")
    registry.extend([
        CapabilityPlugin([first], plugin_id="first"),
        CapabilityPlugin([second], plugin_id="second"),
    ])
    registry.activate_all()

    assert registry.capabilities(LLMProvider) == [first, second]
    assert registry.capability_names(LLMProvider) == ["a", "b"]
    assert registry.capability(LLMProvider, "b") is second


def test_dynamic_capability_registration(registry: PluginRegistry) -> None:
    provider = FakeLLMProvider("dyn")
    registry.register(DynamicCapabilityPlugin(provider))
    registry.activate_all()

    assert registry.capability(LLMProvider, "dyn") is provider


def test_tool_and_analyzer_capabilities(registry: PluginRegistry) -> None:
    tool = FakeTool("echo")
    analyzer = FakeAnalyzer("lint")
    registry.register_capability(tool)
    registry.register_capability(analyzer)

    assert registry.capability(Tool, "echo") is tool
    assert registry.capabilities(CodeAnalyzer) == [analyzer]
    assert tool.invoke({"n": 1}).output == "{'n': 1}"
    assert analyzer.analyze("  x  ", path="a.py").findings == ("x",)


# --- invalid plugins / conflicts --------------------------------------------


def test_non_plugin_rejected(registry: PluginRegistry) -> None:
    with pytest.raises(InvalidPluginError):
        registry.register(cast(Plugin, object()))


def test_empty_id_rejected(registry: PluginRegistry) -> None:
    class Broken(NoopPlugin):
        id = ""

    with pytest.raises(InvalidPluginError):
        registry.register(Broken())


def test_duplicate_plugin_id_rejected(registry: PluginRegistry) -> None:
    registry.register(NoopPlugin())
    with pytest.raises(DuplicatePluginError):
        registry.register(NoopPlugin())


def test_duplicate_capability_rejected(registry: PluginRegistry) -> None:
    registry.register_capability(FakeLLMProvider("dup"))
    with pytest.raises(DuplicateCapabilityError):
        registry.register_capability(FakeLLMProvider("dup"))


def test_non_capability_rejected(registry: PluginRegistry) -> None:
    with pytest.raises(CapabilityError):
        registry.register_capability(cast(Capability, object()))


def test_empty_capability_name_rejected(registry: PluginRegistry) -> None:
    with pytest.raises(CapabilityError):
        registry.register_capability(FakeLLMProvider(""))


def test_invalid_capability_from_plugin_rejected(registry: PluginRegistry) -> None:
    registry.register(BadCapabilityPlugin())
    with pytest.raises(CapabilityError):
        registry.activate_all()


# --- lifecycle --------------------------------------------------------------


def test_lifecycle_load_initialize_shutdown(registry: PluginRegistry) -> None:
    plugin = RecordingPlugin()
    registry.register(plugin)
    assert plugin.events == ["load"]

    registry.activate_all()
    assert plugin.events == ["load", "initialize"]

    registry.deactivate_all()
    assert plugin.events == ["load", "initialize", "shutdown"]


def test_legacy_activate_deactivate_is_preserved(registry: PluginRegistry) -> None:
    plugin = LifecyclePlugin()
    registry.register(plugin)
    registry.activate_all()
    registry.deactivate_all()

    assert plugin.activated == 1
    assert plugin.deactivated == 1


def test_capabilities_removed_on_shutdown(registry: PluginRegistry) -> None:
    registry.register(CapabilityPlugin([FakeLLMProvider("x")]))
    registry.activate_all()
    assert registry.has_capability(LLMProvider)

    registry.deactivate_all()
    assert not registry.has_capability(LLMProvider)
    assert registry.capability_names(LLMProvider) == []


# --- default provider resolution --------------------------------------------


def test_default_single_provider(registry: PluginRegistry) -> None:
    provider = FakeLLMProvider("only")
    registry.register_capability(provider)
    assert registry.default_capability(LLMProvider) is provider


def test_default_flag_selects_provider(registry: PluginRegistry) -> None:
    registry.register_capability(FakeLLMProvider("a"))
    preferred = FakeLLMProvider("b", default=True)
    registry.register_capability(preferred)

    assert registry.default_capability(LLMProvider) is preferred


def test_default_from_config() -> None:
    config = CoreConfig.model_validate({"defaults": {"llm": "b"}})
    registry = PluginRegistry(config=config, events=EventBus())
    registry.register_capability(FakeLLMProvider("a"))
    preferred = FakeLLMProvider("b")
    registry.register_capability(preferred)

    assert registry.default_capability(LLMProvider) is preferred


def test_default_config_by_class_name() -> None:
    config = CoreConfig.model_validate({"defaults": {"LLMProvider": "b"}})
    registry = PluginRegistry(config=config, events=EventBus())
    registry.register_capability(FakeLLMProvider("a"))
    preferred = FakeLLMProvider("b")
    registry.register_capability(preferred)

    assert registry.default_capability(LLMProvider) is preferred


def test_default_config_overrides_flag() -> None:
    config = CoreConfig.model_validate({"defaults": {"llm": "b"}})
    registry = PluginRegistry(config=config, events=EventBus())
    registry.register_capability(FakeLLMProvider("a", default=True))
    preferred = FakeLLMProvider("b")
    registry.register_capability(preferred)

    assert registry.default_capability(LLMProvider) is preferred


def test_ambiguous_default_raises(registry: PluginRegistry) -> None:
    registry.register_capability(FakeLLMProvider("a"))
    registry.register_capability(FakeLLMProvider("b"))

    with pytest.raises(AmbiguousCapabilityError):
        registry.default_capability(LLMProvider)


def test_configured_default_missing_raises(registry: PluginRegistry) -> None:
    registry._config.defaults["llm"] = "ghost"  # noqa: SLF001 - direct fixture setup
    registry.register_capability(FakeLLMProvider("a"))

    with pytest.raises(CapabilityError):
        registry.default_capability(LLMProvider)


# --- discovery --------------------------------------------------------------


class _FakeEntryPoint:
    def __init__(self, name: str, value: Any, error: Exception | None = None) -> None:
        self.name = name
        self._value = value
        self._error = error

    def load(self) -> Any:
        if self._error is not None:
            raise self._error
        return self._value


def test_discover_plugins_aggregates() -> None:
    first = NoopPlugin()
    second = EchoNodePlugin()
    result = discover_plugins([FakeDiscoverer([first]), FakeDiscoverer([second])])
    assert result == [first, second]


def test_build_core_uses_discoverer() -> None:
    plugin = CapabilityPlugin([FakeLLMProvider("discovered")], plugin_id="discovered")
    core = build_core(discoverers=[FakeDiscoverer([plugin])])

    assert core.registry.get("discovered") is plugin
    assert core.registry.capability_names(LLMProvider) == ["discovered"]
    core.shutdown()


def test_build_core_registers_discovered_and_explicit() -> None:
    discovered = CapabilityPlugin([FakeLLMProvider("a")], plugin_id="discovered")
    explicit = CapabilityPlugin([FakeLLMProvider("b")], plugin_id="explicit")
    core = build_core(discoverers=[FakeDiscoverer([discovered])], plugins=[explicit])

    assert core.registry.get("discovered") is discovered
    assert core.registry.get("explicit") is explicit
    core.shutdown()


def test_build_core_rejects_duplicate_between_sources() -> None:
    plugin = CapabilityPlugin([], plugin_id="dup")
    with pytest.raises(DuplicatePluginError):
        build_core(discoverers=[FakeDiscoverer([plugin])], plugins=[plugin])


def test_disabled_plugin_from_discovery_is_skipped() -> None:
    config = CoreConfig.model_validate({"plugins": {"disabled": {"enabled": False}}})
    plugin = CapabilityPlugin([FakeLLMProvider("x")], plugin_id="disabled")
    core = build_core(
        config=config,
        discoverers=[FakeDiscoverer([plugin])],
    )
    assert "disabled" not in core.registry
    core.shutdown()


def test_entry_point_discoverer_resolves_instances_and_factories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = NoopPlugin()
    entry_points = [
        _FakeEntryPoint("instance", instance),
        _FakeEntryPoint("class", EchoNodePlugin),
        _FakeEntryPoint("factory", lambda: LifecyclePlugin()),
    ]

    def fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        assert group == DEFAULT_ENTRY_POINT_GROUP
        return entry_points

    monkeypatch.setattr(
        "core.plugins.discovery.importlib_metadata.entry_points", fake_entry_points
    )

    plugins = EntryPointDiscoverer().discover()
    assert [plugin.id for plugin in plugins] == ["noop", "echo", "lifecycle"]


def test_entry_point_discoverer_rejects_invalid_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        return [_FakeEntryPoint("bad", object())]

    monkeypatch.setattr(
        "core.plugins.discovery.importlib_metadata.entry_points", fake_entry_points
    )

    with pytest.raises(DiscoveryError):
        EntryPointDiscoverer().discover()


def test_entry_point_discoverer_wraps_load_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        return [_FakeEntryPoint("boom", None, RuntimeError("kaboom"))]

    monkeypatch.setattr(
        "core.plugins.discovery.importlib_metadata.entry_points", fake_entry_points
    )

    with pytest.raises(DiscoveryError):
        EntryPointDiscoverer().discover()
