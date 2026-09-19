"""Plugin discovery infrastructure.

The core does not know which plugins exist. Discovery happens through one or
more :class:`~core.contracts.discovery.Discoverer` instances; the built-in
:class:`EntryPointDiscoverer` reads installed Python entry points, and any other
mechanism can be supplied to ``build_core`` without changing the core.
"""

from __future__ import annotations

from collections.abc import Iterable
from importlib import metadata as importlib_metadata
from typing import TYPE_CHECKING, Any

from core.contracts.discovery import Discoverer
from core.errors import DiscoveryError
from core.plugins.base import Plugin

if TYPE_CHECKING:
    from importlib.metadata import EntryPoint

DEFAULT_ENTRY_POINT_GROUP = "core_agent.plugins"


class EntryPointDiscoverer(Discoverer):
    """Discover plugins declared as entry points.

    Each entry point in ``group`` must resolve to a :class:`Plugin` instance, a
    ``Plugin`` subclass, or a zero-argument factory returning one.

    Args:
        group: entry-point group to read. Defaults to
            :data:`DEFAULT_ENTRY_POINT_GROUP`; override to isolate namespaces.
    """

    def __init__(self, group: str = DEFAULT_ENTRY_POINT_GROUP) -> None:
        self._group = group

    @property
    def name(self) -> str:
        return f"entry-points:{self._group}"

    def discover(self) -> list[Plugin]:
        """Load and materialize every plugin in the configured group."""
        return [self._resolve(entry_point) for entry_point in self._entry_points()]

    def _entry_points(self) -> Iterable[EntryPoint]:
        return importlib_metadata.entry_points(group=self._group)

    @staticmethod
    def _resolve(entry_point: EntryPoint) -> Plugin:
        try:
            target: Any = entry_point.load()
        except Exception as exc:  # noqa: BLE001 - surfaced as DiscoveryError
            raise DiscoveryError(
                f"cannot load plugin entry point {entry_point.name!r}: {exc}"
            ) from exc

        if isinstance(target, Plugin):
            return target
        if isinstance(target, type) and issubclass(target, Plugin):
            return target()
        if callable(target):
            plugin = target()
            if isinstance(plugin, Plugin):
                return plugin
            raise DiscoveryError(
                f"entry point {entry_point.name!r} produced "
                f"{type(plugin).__name__}, expected a Plugin"
            )
        raise DiscoveryError(
            f"entry point {entry_point.name!r} resolved to "
            f"{type(target).__name__}, expected a Plugin"
        )


def discover_plugins(discoverers: Iterable[Discoverer]) -> list[Plugin]:
    """Collect plugins from every discoverer, in order."""
    plugins: list[Plugin] = []
    for discoverer in discoverers:
        plugins.extend(discoverer.discover())
    return plugins
