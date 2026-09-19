"""Context handed to a plugin during its lifetime."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.config.schema import PluginSlot
from core.events.bus import EventBus, Subscription
from core.events.event import Event
from core.events.types import EventHandler

if TYPE_CHECKING:
    from core.contracts.capability import Capability
    from core.plugins.registry import PluginRegistry


class PluginContext:
    """Services a plugin can use: configuration, events and capabilities.

    The context is deliberately narrow — plugins get exactly what they need and
    no more, which keeps the core's extension surface small and stable.
    """

    def __init__(
        self,
        *,
        plugin_id: str,
        config: PluginSlot,
        events: EventBus,
        registry: PluginRegistry,
    ) -> None:
        self._plugin_id = plugin_id
        self._config = config
        self._events = events
        self._registry = registry

    @property
    def plugin_id(self) -> str:
        return self._plugin_id

    @property
    def config(self) -> PluginSlot:
        """The plugin's configuration slot (enabled flag + settings)."""
        return self._config

    @property
    def settings(self) -> dict[str, Any]:
        """Free-form settings declared for this plugin."""
        return self._config.settings

    def get_setting(self, name: str, default: Any = None) -> Any:
        """Return a setting value, falling back to ``default``."""
        return self._config.settings.get(name, default)

    def register_capability(self, capability: Capability) -> Capability:
        """Register a capability dynamically (alternative to ``declare_capabilities``).

        Prefer the declarative :meth:`Plugin.declare_capabilities` hook; this is
        for providers that can only be built once settings are known.
        """
        return self._registry.register_capability(capability)

    def publish(self, event: Event[Any]) -> None:
        """Publish an event to the core event bus."""
        self._events.publish(event)

    def subscribe(self, event_type: str, handler: EventHandler) -> Subscription:
        """Subscribe to an event type and return the subscription handle."""
        return self._events.subscribe(event_type, handler)