"""Plugin discovery contract.

The core does not know which plugins exist. A :class:`Discoverer` is any object
able to produce :class:`Plugin` instances; the built-in entry-point discoverer
lives in :mod:`core.plugins.discovery`, and alternative mechanisms can be added
without touching the core.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable
from typing import TYPE_CHECKING

from core.contracts.capability import Capability

if TYPE_CHECKING:
    from core.plugins.base import Plugin


class Discoverer(Capability):
    """Produces plugin instances from some source (entry points, paths, ...)."""

    kind = "discoverer"

    @property
    def name(self) -> str:
        """Default to the class name; subclasses may override."""
        return type(self).__name__

    @abstractmethod
    def discover(self) -> Iterable[Plugin]:
        """Return the plugins found by this discoverer."""
        raise NotImplementedError
