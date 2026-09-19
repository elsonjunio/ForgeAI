from __future__ import annotations

import pytest

from core.config.schema import CoreConfig
from core.errors import DuplicatePluginError, InvalidPluginError
from core.events.bus import EventBus
from core.events.event import Event
from core.events.types import CoreEvents
from core.plugins.registry import PluginRegistry
from tests.support.plugins import (
    EchoNodePlugin,
    GreetToolPlugin,
    LifecyclePlugin,
    NoopPlugin,
    make_ordered_node_plugin,
)


@pytest.fixture
def registry(bus: EventBus) -> PluginRegistry:
    return PluginRegistry(config=CoreConfig(), events=bus)


def test_register_and_retrieve(registry: PluginRegistry) -> None:
    plugin = NoopPlugin()
    registry.register(plugin)
    assert registry.get("noop") is plugin
    assert "noop" in registry
    assert len(registry) == 1


def test_duplicate_id_rejected(registry: PluginRegistry) -> None:
    registry.register(NoopPlugin())
    with pytest.raises(DuplicatePluginError):
        registry.register(NoopPlugin())


def test_empty_id_rejected(registry: PluginRegistry) -> None:
    class Broken(NoopPlugin):
        id = ""

    with pytest.raises(InvalidPluginError):
        registry.register(Broken())


def test_extend_registers_all(registry: PluginRegistry) -> None:
    registry.extend([NoopPlugin(), EchoNodePlugin()])
    assert len(registry) == 2
    assert registry.get("echo") is not None


def test_activation_runs_lifecycle_and_publishes(registry: PluginRegistry) -> None:
    plugin = LifecyclePlugin()
    published: list[Event[object]] = []
    registry.events.subscribe("test.plugin.activated", published.append)

    registry.register(plugin)
    registry.activate_all()

    assert plugin.activated == 1
    assert plugin.deactivated == 0
    assert registry.is_active("lifecycle")
    assert len(published) == 1
    assert published[0].source == "lifecycle"
    assert registry.context("lifecycle") is not None


def test_deactivate_runs_hooks(registry: PluginRegistry) -> None:
    plugin = LifecyclePlugin()
    registry.register(plugin)
    registry.activate_all()

    registry.deactivate_all()

    assert plugin.deactivated == 1
    assert plugin.activated == 1
    assert registry.context("lifecycle") is None
    assert registry.is_active("lifecycle") is False


def test_deactivation_publishes_event(registry: PluginRegistry) -> None:
    registry.register(LifecyclePlugin())
    registry.activate_all()

    published: list[Event[object]] = []
    registry.events.subscribe(CoreEvents.PLUGIN_DEACTIVATED, published.append)
    registry.deactivate_all()

    assert len(published) == 1
    assert published[0].type == CoreEvents.PLUGIN_DEACTIVATED


def test_event_handlers_subscribed_on_activate(registry: PluginRegistry) -> None:
    plugin = LifecyclePlugin()
    registry.register(plugin)
    registry.activate_all()

    registry.events.publish(Event[object](type="test.ping", source="tester", payload=None))
    assert len(plugin.handled) == 1
    assert plugin.handled[0].source == "tester"


def test_handlers_unsubscribed_after_deactivate(registry: PluginRegistry) -> None:
    plugin = LifecyclePlugin()
    registry.register(plugin)
    registry.activate_all()
    registry.deactivate_all()

    registry.events.publish(Event[object](type="test.ping", source="tester", payload=None))
    assert plugin.handled == []


def test_context_exposes_settings() -> None:
    config = CoreConfig.model_validate(
        {"plugins": {"lifecycle": {"settings": {"retries": 3}}}}
    )
    registry = PluginRegistry(config=config, events=EventBus())
    registry.register(LifecyclePlugin())
    registry.activate_all()

    context = registry.context("lifecycle")
    assert context is not None
    assert context.plugin_id == "lifecycle"
    assert context.get_setting("retries") == 3
    assert context.get_setting("missing", default="fallback") == "fallback"
    assert context.settings == {"retries": 3}


def test_noop_plugin_contributes_nothing(registry: PluginRegistry) -> None:
    registry.register(NoopPlugin())
    assert registry.collect_nodes() == []
    assert registry.collect_tools() == []


def test_collect_nodes_and_tools(registry: PluginRegistry) -> None:
    registry.extend([EchoNodePlugin(), GreetToolPlugin()])
    nodes = registry.collect_nodes()
    tools = registry.collect_tools()

    assert [node.contract.id for node in nodes] == ["echo"]
    assert [tool.name for tool in tools] == ["greet"]


def test_collect_nodes_preserves_registration_order(registry: PluginRegistry) -> None:
    first = make_ordered_node_plugin("first", 1)()
    second = make_ordered_node_plugin("second", 2, after="first")()

    registry.register(second)
    registry.register(first)
    registry.activate_all()

    collected = registry.collect_nodes()
    assert [node.contract.id for node in collected] == ["second", "first"]