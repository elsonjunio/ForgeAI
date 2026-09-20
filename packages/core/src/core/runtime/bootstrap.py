"""Composition root: wire the core services together."""

from __future__ import annotations

from collections.abc import Iterable

from core.agent.graph import PlanExecutor
from core.agent.runtime import AgentRuntime, WorkflowRuntime
from core.agent.workflow import WorkflowContext
from core.config.schema import CoreConfig
from core.contracts.discovery import Discoverer
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
) -> CoreContainer:
    """Assemble a fully wired core instance.

    Args:
        config: configuration; defaults are used when omitted.
        plugins: plugin instances to load explicitly (disabled slots are skipped).
        discoverers: discovery mechanisms to run. ``None`` means "use the
            built-in entry-point discoverer"; pass an empty iterable to disable
            discovery entirely.

    Returns:
        A ready-to-use :class:`CoreContainer`. ``container.runtime`` runs the
        generic plugin-contributed graph; ``container.workflow`` runs the
        code-agent workflow.

    Discovered and explicit plugins are registered in that order, after
    filtering by ``config.is_enabled``. With zero plugins the framework still
    builds and runs: the agent graph reduces to state initialization and the
    workflow is built (it only requires an LLM when it actually runs).
    """
    cfg = config or CoreConfig()
    events = EventBus()

    registry = PluginRegistry(config=cfg, events=events)

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

    workflow = WorkflowRuntime(
        context=WorkflowContext(registry=registry, events=events, options=cfg.workflow)
    )

    executor = PlanExecutor(registry=registry)

    return CoreContainer(
        config=cfg,
        events=events,
        registry=registry,
        runtime=runtime,
        workflow=workflow,
        executor=executor,
    )