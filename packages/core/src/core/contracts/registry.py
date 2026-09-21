"""Capability registry contract.

A narrow, structural interface for resolving capabilities. ``PluginRegistry``
implements it; orchestration code (for example the plan executor) depends on
this protocol rather than on the concrete registry, keeping the agent layer
independent of the plugin implementation layer.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.contracts.capability import Capability, CapabilityDescriptor


@runtime_checkable
class CapabilitySource(Protocol):
    """Read-only view over a set of registered capabilities."""

    def capabilities(self, kind: type[Any] | str) -> list[Capability]:
        """Return the registered capabilities of ``kind`` (contract type or name)."""
        ...

    def capability(self, kind: type[Any] | str, name: str) -> Capability | None:
        """Return the capability of ``kind`` named ``name``, if registered."""
        ...

    def default_capability(self, kind: type[Any]) -> Capability | None:
        """Return the default provider of ``kind``, if any."""
        ...

    def executable_capabilities(self) -> list[Capability]:
        """Return the capabilities that can run as plan nodes (``Executable``)."""
        ...

    def executable_capability_descriptors(self) -> list[CapabilityDescriptor]:
        """Descriptors of the capabilities that can run as plan nodes."""
        ...

    def capability_names(self, kind: type[Any] | str) -> list[str]:
        """Names of the registered capabilities of ``kind``."""
        ...

    def capability_kinds(self) -> list[str]:
        """Sorted ``kind`` values of all registered capabilities."""
        ...

    def has_capability(self, kind: type[Any] | str) -> bool:
        """Whether at least one capability of ``kind`` is registered."""
        ...
