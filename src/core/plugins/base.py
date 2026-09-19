"""The plugin contract: the stable extension point of the framework."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.contracts.node import NodeContribution
from core.contracts.plugin import PluginMetadata
from core.contracts.tool import ToolContract

if TYPE_CHECKING:
    from core.contracts.capability import Capability
    from core.events.types import EventHandler
    from core.plugins.context import PluginContext

__all__ = ["Plugin", "PluginMetadata"]


class Plugin:
    """Base class for every plugin.

    Subclasses must define a non-empty ``id`` and should set ``version``. They
    may override:

    * ``load`` / ``initialize`` / ``shutdown`` — lifecycle hooks driven by the
      registry. ``initialize`` defaults to calling ``activate`` and ``shutdown``
      defaults to calling ``deactivate``, so older plugins keep working.
    * ``declare_capabilities`` — capabilities (LLM, tool, analyzer, discoverer)
      contributed to the registry.
    * ``declare_tools`` — declarative tool descriptors (no implementation).
    * ``declare_nodes`` — state transformations wired into the agent graph.
    * ``event_handlers`` — subscriptions registered when the plugin activates.

    All contribution hooks default to empty collections, so a plugin with no
    extensions still works.
    """

    id: str = ""
    version: str = "0.0.0"
    name: str = ""
    description: str = ""
    author: str = ""
    homepage: str | None = None
    tags: tuple[str, ...] = ()

    def metadata(self) -> PluginMetadata:
        """Return the plugin's identity, version and descriptive metadata."""
        return PluginMetadata(
            id=self.id,
            version=self.version,
            name=self.name or type(self).__name__,
            description=self.description,
            author=self.author,
            homepage=self.homepage,
            tags=self.tags,
        )

    def load(self) -> None:
        """Called once when the plugin is registered, before ``initialize``.

        Use it to validate the environment or read static resources. It runs
        before the plugin receives its context.
        """

    def initialize(self, context: PluginContext) -> None:
        """Called once on activation with the plugin's :class:`PluginContext`.

        The default implementation delegates to :meth:`activate` for backward
        compatibility.
        """
        self.activate(context)

    def shutdown(self) -> None:
        """Called on shutdown, in reverse activation order.

        The default implementation delegates to :meth:`deactivate` for backward
        compatibility.
        """
        self.deactivate()

    def activate(self, context: PluginContext) -> None:
        """Backward-compatible lifecycle hook, invoked by :meth:`initialize`.

        Use it to subscribe to events, validate settings or prepare resources.
        """

    def deactivate(self) -> None:
        """Backward-compatible lifecycle hook, invoked by :meth:`shutdown`."""

    def declare_capabilities(self) -> list[Capability]:
        """Declare the capabilities (providers) this plugin contributes."""
        return []

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
