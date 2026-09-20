"""Base contract for capabilities contributed by plugins.

A *capability* is a named extension point that the core can look up without
knowing any concrete implementation. ``LLMProvider``, ``Tool``, ``CodeAnalyzer``,
``Validator``, ``Discoverer`` and ``Planner`` are the capability contracts shipped
by the core; third parties may define further subclasses.

``CapabilityDescriptor`` separates the *description* of a capability (what a
planner needs) from its implementation object.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field


class CapabilityDescriptor(BaseModel):
    """Descriptive information about a capability, for planning/selection.

    Carries only what a consumer (for example a planner) needs to reason about a
    capability, without receiving the implementation object.

    Args:
        id: stable identifier, by convention ``"<kind>:<name>"``.
        name: the capability name.
        kind: the capability kind (``"llm"``, ``"tool"``, ...).
        description: human-readable description.
        groups: free-form labels for grouping/filtering.
        parameters: parameters/schema relevant to invoking the capability.
        metadata: any additional descriptive data.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    description: str = ""
    groups: tuple[str, ...] = ()
    parameters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


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

    def describe(self) -> CapabilityDescriptor:
        """Return the descriptor used to advertise this capability.

        Subclasses may override to expose richer information (for example a
        tool's JSON-schema ``parameters``).
        """
        return CapabilityDescriptor(
            id=f"{self.kind}:{self.name}", name=self.name, kind=self.kind
        )
