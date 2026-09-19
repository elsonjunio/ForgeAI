"""Base contract for capabilities contributed by plugins.

A *capability* is a named extension point that the core can look up without
knowing any concrete implementation. ``LLMProvider``, ``Tool``, ``CodeAnalyzer``
and ``Discoverer`` are the capability contracts shipped by the core; third
parties may define further subclasses.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar


class Capability(ABC):
    """A provider of an extension point, contributed by a plugin.

    Args:
        kind: stable identifier of the capability family (for example ``"llm"``).
            Used for lookup and for config-driven default selection.
        name: stable, unique name within the capability kind.
        default: when ``True``, marks this provider as the preferred default for
            its kind (resolved by :meth:`PluginRegistry.default_capability`).
    """

    kind: ClassVar[str] = "generic"
    default: bool = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable name, unique among capabilities of the same ``kind``."""
        raise NotImplementedError
