"""Tool contracts: how plugins describe and execute tools.

``ToolContract`` is a purely declarative descriptor. ``Tool`` is the executable
capability pairing a descriptor with an ``invoke`` entry point. The core ships no
concrete tool and never executes one itself; it only defines the interface so the
execution flow can materialize tools from a plugin.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from core.contracts.capability import Capability, CapabilityDescriptor


class ToolContract(BaseModel):
    """Declarative description of a tool a plugin offers.

    Args:
        name: stable, unique tool name.
        description: natural-language description used to advertise the tool.
        parameters: JSON-schema describing the expected arguments.
    """

    name: str = Field(min_length=1)
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    """Outcome of invoking a :class:`Tool`.

    Args:
        output: textual output of the tool, when any.
        is_error: whether the invocation failed.
        metadata: free-form structured data (exit codes, paths, ...).
    """

    output: str | None = None
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class Tool(Capability):
    """An executable tool contributed by a plugin.

    ``name`` is derived from the underlying :class:`ToolContract`, so
    implementations only provide ``contract`` and ``invoke``.
    """

    kind = "tool"

    @property
    def name(self) -> str:
        """Tool name, taken from the declarative contract."""
        return self.contract.name

    def describe(self) -> CapabilityDescriptor:
        """Expose the tool's description and JSON-schema parameters."""
        return CapabilityDescriptor(
            id=f"{self.kind}:{self.name}",
            name=self.name,
            kind=self.kind,
            description=self.contract.description,
            groups=tuple(self.groups),
            parameters=dict(self.contract.parameters),
        )

    @property
    @abstractmethod
    def contract(self) -> ToolContract:
        """Declarative description advertised to the model."""
        raise NotImplementedError

    @abstractmethod
    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        """Execute the tool with ``arguments`` and return its result."""
        raise NotImplementedError