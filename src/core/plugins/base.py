"""The plugin contract: the stable extension point of the framework."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.contracts.node import NodeContribution
from core.contracts.tool import ToolContract

if TYPE_CHECKING:
    from core.events.types import EventHandler
    from core.plugins.context import PluginContext


class Plugin:
    """Base class for every plugin.

    Subclasses must define a non-empty ``id`` and should set ``version``. They
    may override:

    * ``activate`` / ``deactivate`` — lifecycle hooks, called by the registry.
    * ``declare_tools`` — declarative tool descriptors (no implementation).
    * ``declare_nodes`` — state transformations wired into the agent graph.
    * ``event_handlers`` — subscriptions registered when the plugin activates.

    All contribution hooks default to empty collections, so a plugin with no
    extensions still works.
    """

    id: str = ""
    version: str = "0.0.0"

    def activate(self, context: PluginContext) -> None:
        """Called once after registration, before the runtime is built.

        Use it to subscribe to events, validate settings or prepare resources.
        """

    def deactivate(self) -> None:
        """Called on shutdown, in reverse activation order.

        Use it to release resources held by the plugin.
        """

    def declare_tools(self) -> list[ToolContract]:
        """Declare the tools this plugin *describes*.

        Returns only declarative contracts; the core ships no concrete tools.
        """
        return []

    def declare_nodes(self) -> list[NodeContribution]:
        """Contribute state-transformation nodes to the agent graph."""
        return []

    def event_handlers(self) -> dict[str, EventHandler]:
        """Event handlers subscribed on activation, keyed by event type."""
        return {}