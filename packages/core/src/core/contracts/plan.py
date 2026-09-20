"""Execution plan contracts: a LangGraph-independent executable plan.

A plan is a directed graph of :class:`PlanNode` units connected by
:class:`PlanEdge` dependencies. It is intentionally engine-agnostic: the core
does not execute it yet, and no LangGraph type appears here. A plan node
references a capability by its stable id (see
:class:`~core.contracts.capability.CapabilityDescriptor`) and carries the
parameters needed to run it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlanNode(BaseModel):
    """A single unit of execution in a plan.

    Args:
        id: unique identifier of the node within the plan.
        capability: stable id of the capability this node runs, if any.
        description: human-readable description of the step.
        parameters: values/schema the capability needs to run.
        metadata: free-form data carried with the node.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    capability: str | None = None
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanEdge(BaseModel):
    """A dependency between two nodes (``source`` runs before ``target``)."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    """A LangGraph-independent plan produced by a planner.

    Args:
        id: unique identifier of the plan.
        nodes: execution units.
        edges: dependencies/ordering between nodes.
        metadata: free-form data (planner info, rationale, ...).

    The graph can represent sequential steps, dependencies and future
    parallelism. Cycles are not validated or interpreted: if the execution
    engine does not support them, neither should a plan use them.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    nodes: tuple[PlanNode, ...] = ()
    edges: tuple[PlanEdge, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def node_ids(self) -> tuple[str, ...]:
        """Ids of all nodes, in declaration order."""
        return tuple(node.id for node in self.nodes)

    def node(self, node_id: str) -> PlanNode | None:
        """Return the node with ``node_id``, if present."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def outgoing(self, node_id: str) -> tuple[PlanEdge, ...]:
        """Edges leaving ``node_id``."""
        return tuple(edge for edge in self.edges if edge.source == node_id)

    def incoming(self, node_id: str) -> tuple[PlanEdge, ...]:
        """Edges entering ``node_id``."""
        return tuple(edge for edge in self.edges if edge.target == node_id)
