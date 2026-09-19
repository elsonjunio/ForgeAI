"""Composition root: wire the core services together."""

from __future__ import annotations

from collections.abc import Iterable

from core.agent.runtime import AgentRuntime
from core.config.schema import CoreConfig
from core.events.bus import EventBus
from core.plugins.base import Plugin
from core.plugins.registry import PluginRegistry
from core.runtime.container import CoreContainer


def build_core(
    config: CoreConfig | None = None,
    *,
    plugins: Iterable[Plugin] = (),
) -> CoreContainer:
    """Assemble a fully wired core instance.

    Args:
        config: configuration; defaults are used when omitted.
        plugins: plugin instances to load (disabled slots are skipped).

    Returns:
        A ready-to-use :class:`CoreContainer` — ``container.runtime`` is the
        public entry point.

    With zero plugins the framework still builds and runs: the agent graph
    reduces to state initialization.
    """
    cfg = config or CoreConfig()
    events = EventBus()

    registry = PluginRegistry(config=cfg, events=events)
    for plugin in plugins:
        if cfg.is_enabled(plugin.id):
            registry.register(plugin)
    registry.activate_all()

    runtime = AgentRuntime(
        nodes=registry.collect_nodes(),
        event_bus=events,
        options=cfg.langgraph,
    )

    return CoreContainer(config=cfg, events=events, registry=registry, runtime=runtime)