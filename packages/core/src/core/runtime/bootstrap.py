"""Composition root: wire the core services together."""

from __future__ import annotations

from collections.abc import Iterable

from core.agent.graph import PlanExecutor
from core.agent.runtime import AgentRuntime
from core.config.schema import CoreConfig
from core.contracts.callbacks import ExecutionObserver
from core.contracts.discovery import Discoverer
from core.contracts.interaction import InteractionProvider
from core.events.bus import EventBus
from core.plugins.base import Plugin
from core.plugins.discovery import EntryPointDiscoverer, discover_plugins
from core.plugins.registry import PluginRegistry
from core.runtime.container import CoreContainer


def build_core(
    config: CoreConfig | None = None,
    *,
    plugins: Iterable[Plugin] = (),
    discoverers: Iterable[Discoverer] | None = None,
    interaction: InteractionProvider | None = None,
    observer: ExecutionObserver | None = None,
) -> CoreContainer:
    """Assemble a fully wired core instance.

    Args:
        config: configuration; defaults are used when omitted.
        plugins: plugin instances to load explicitly (disabled slots are skipped).
        discoverers: discovery mechanisms to run. ``None`` means "use the
            built-in entry-point discoverer"; pass an empty iterable to disable
            discovery entirely.
        interaction: optional host-provided interaction mechanism, exposed to
            plugins (via their context) and to executable capabilities.
        observer: optional host-provided observer for plan execution events
            (node start/complete, errors), useful for live progress.

    Returns:
        A ready-to-use :class:`CoreContainer`. ``container.runtime`` runs the
        generic plugin-contributed graph; ``container.executor`` runs dynamic
        plans (``ExecutionPlan`` -> LangGraph).

    Discovered and explicit plugins are registered in that order, after
    filtering by ``config.is_enabled``. With zero plugins the framework still
    builds and runs.
    """
    cfg = config or CoreConfig()
    events = EventBus()

    registry = PluginRegistry(config=cfg, events=events, interaction=interaction)

    resolved: Iterable[Discoverer] = (
        [EntryPointDiscoverer()] if discoverers is None else discoverers
    )
    for plugin in [*discover_plugins(resolved), *plugins]:
        if cfg.is_enabled(plugin.id):
            registry.register(plugin)
    registry.activate_all()

    runtime = AgentRuntime(
        nodes=registry.collect_nodes(),
        event_bus=events,
        options=cfg.langgraph,
    )

    executor = PlanExecutor(
        registry=registry, interaction=interaction, observer=observer
    )

    return CoreContainer(
        config=cfg,
        events=events,
        registry=registry,
        runtime=runtime,
        executor=executor,
    )
