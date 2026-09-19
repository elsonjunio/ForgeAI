"""Plugin registry: registration, lifecycle and contribution collection."""

from __future__ import annotations

from collections.abc import Iterable

from core.config.schema import CoreConfig
from core.contracts.node import NodeContribution
from core.contracts.tool import ToolContract
from core.errors import DuplicatePluginError, InvalidPluginError
from core.events.bus import EventBus, Subscription
from core.events.event import Event
from core.events.types import CoreEvents
from core.plugins.base import Plugin
from core.plugins.context import PluginContext


class PluginRegistry:
    """Holds plugins and drives their lifecycle.

    Responsibilities:

    * ``register``/``extend`` — validate and store plugin instances.
    * ``activate_all``/``deactivate_all`` — run lifecycle hooks and wire the
      event handlers declared by each plugin.
    * ``collect_*`` — aggregate the contributions (tools/nodes) of all plugins.

    The registry itself is agnostic of LangGraph: it only collects declarative
    descriptions, which the runtime materializes.
    """

    def __init__(self, *, config: CoreConfig, events: EventBus) -> None:
        self._config = config
        self._events = events
        self._plugins: dict[str, Plugin] = {}
        self._contexts: dict[str, PluginContext] = {}
        self._subscriptions: dict[str, list[Subscription]] = {}
        self._active_order: list[str] = []

    @property
    def config(self) -> CoreConfig:
        """The configuration this registry operates against."""
        return self._config

    @property
    def events(self) -> EventBus:
        """The event bus plugins publish and subscribe on."""
        return self._events

    def register(self, plugin: Plugin) -> None:
        """Store ``plugin``, rejecting invalid ids and duplicates."""
        if not plugin.id:
            raise InvalidPluginError("plugin.id must be a non-empty string")
        if plugin.id in self._plugins:
            raise DuplicatePluginError(f"a plugin with id {plugin.id!r} is already registered")
        self._plugins[plugin.id] = plugin

    def extend(self, plugins: Iterable[Plugin]) -> None:
        """Register many plugins in order."""
        for plugin in plugins:
            self.register(plugin)

    def get(self, plugin_id: str) -> Plugin | None:
        """Return the registered plugin with ``plugin_id``, if any."""
        return self._plugins.get(plugin_id)

    def context(self, plugin_id: str) -> PluginContext | None:
        """Return the active context for ``plugin_id``, if activated."""
        return self._contexts.get(plugin_id)

    def is_active(self, plugin_id: str) -> bool:
        return plugin_id in self._active_order

    def __contains__(self, plugin_id: object) -> bool:
        return plugin_id in self._plugins

    def __iter__(self) -> Iterable[Plugin]:
        return iter(self._plugins.values())

    def __len__(self) -> int:
        return len(self._plugins)

    def activate_all(self) -> None:
        """Activate every registered plugin in registration order.

        For each plugin, its declared event handlers are subscribed first, then
        ``activate`` runs, then ``plugin.activated`` is published.
        """
        for plugin_id, plugin in self._plugins.items():
            subscriptions = [
                self._events.subscribe(event_type, handler)
                for event_type, handler in plugin.event_handlers().items()
            ]
            self._subscriptions[plugin_id] = subscriptions

            context = PluginContext(
                plugin_id=plugin_id,
                config=self._config.slot(plugin_id),
                events=self._events,
            )
            plugin.activate(context)
            self._contexts[plugin_id] = context
            self._active_order.append(plugin_id)

            self._events.publish(Event[object](
                type=CoreEvents.PLUGIN_ACTIVATED,
                source=plugin_id,
                payload={"version": plugin.version},
            ))

    def deactivate_all(self) -> None:
        """Deactivate plugins in reverse activation order and remove handlers.

        ``deactivate`` hooks run first; the event handlers declared by the
        plugin are unsubscribed afterwards and ``plugin.deactivated`` fires.
        """
        for plugin_id in reversed(self._active_order):
            plugin = self._plugins[plugin_id]
            plugin.deactivate()
            for subscription in self._subscriptions.pop(plugin_id, ()):
                self._events.unsubscribe(subscription)
            self._contexts.pop(plugin_id, None)

            self._events.publish(Event[object](
                type=CoreEvents.PLUGIN_DEACTIVATED,
                source=plugin_id,
                payload={"version": plugin.version},
            ))
        self._active_order.clear()

    def collect_nodes(self) -> list[NodeContribution]:
        """Aggregate the node contributions of every registered plugin."""
        return [
            contribution
            for plugin in self._plugins.values()
            for contribution in plugin.declare_nodes()
        ]

    def collect_tools(self) -> list[ToolContract]:
        """Aggregate the tool contracts of every registered plugin."""
        return [
            contract
            for plugin in self._plugins.values()
            for contract in plugin.declare_tools()
        ]