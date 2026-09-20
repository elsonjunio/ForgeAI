"""Planning contract: how plugins turn a request into an executable plan.

A planner is a capability (``kind="planner"``) contributed by a plugin. It
receives a :class:`PlanningRequest` — which carries the execution context,
including the history the host explicitly chose to send — and returns a
:class:`PlanningResult` wrapping an engine-agnostic
:class:`~core.contracts.plan.ExecutionPlan`.

A planner knows nothing about LangGraph, and may internally use an LLM, rules,
heuristics, other planners, etc.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core.agent.state import Message
from core.contracts.capability import Capability, CapabilityDescriptor
from core.contracts.execution import ExecutionContext
from core.contracts.plan import ExecutionPlan


class PlanningRequest(BaseModel):
    """Input handed to a :class:`Planner`.

    Args:
        request: the original user request.
        context: the shared execution context (state, history, capabilities).
        planners: descriptors of the planners/groups available for planning.
        metadata: free-form planning metadata.

    ``capabilities`` and ``history`` are exposed as read-only properties backed
    by ``context`` so there is a single source of truth.
    """

    model_config = ConfigDict(extra="forbid")

    request: str
    context: ExecutionContext
    planners: tuple[CapabilityDescriptor, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def capabilities(self) -> tuple[CapabilityDescriptor, ...]:
        """Descriptors of the capabilities available for planning."""
        return self.context.capabilities

    @property
    def history(self) -> tuple[Message, ...]:
        """Prior context supplied by the host through the execution context."""
        return self.context.history


class PlanningResult(BaseModel):
    """Output produced by a :class:`Planner`.

    Args:
        plan: the executable plan.
        rationale: optional explanation for the plan.
        metadata: free-form data about the planning process.
    """

    model_config = ConfigDict(extra="forbid")

    plan: ExecutionPlan
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class Planner(Capability):
    """A capability that produces an :class:`ExecutionPlan`."""

    kind = "planner"

    @abstractmethod
    def plan(self, request: PlanningRequest) -> PlanningResult:
        """Produce a plan for ``request``."""
        raise NotImplementedError
