"""Node contribution contract.

A plugin contributes *transformations* on :class:`AgentState`. The core runtime
wraps them as nodes of its internal execution graph; plugins never interact with
the graph engine directly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

from pydantic import BaseModel, Field

from core.agent.state import AgentState

AgentNode: TypeAlias = Callable[[AgentState], AgentState]


class NodeContract(BaseModel):
    """Static metadata for a contributed node.

    Args:
        id: stable, unique node id within the graph.
        description: what the node does.
        after: optional id of another contributed node that must run first;
            used to define ordering among plugins.
    """

    id: str = Field(min_length=1)
    description: str = ""
    after: str | None = None


@dataclass(frozen=True)
class NodeContribution:
    """A node declared by a plugin paired with its executable transformation."""

    contract: NodeContract
    node: AgentNode