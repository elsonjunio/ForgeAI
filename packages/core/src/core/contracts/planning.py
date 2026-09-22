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
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.agent.state import Message
from core.contracts.capability import Capability, CapabilityDescriptor
from core.contracts.execution import ExecutionContext
from core.contracts.llm import LLMUsage
from core.contracts.plan import ExecutionPlan


class Observation(BaseModel):
    """Information gathered by a previous plan/execute iteration.

    The host accumulates these across iterations and feeds them back to the
    planner, so a planner can decide whether it still needs more information.

    Args:
        node_id: the plan node that produced the observation.
        capability: the capability id that ran, when known.
        success: whether the node succeeded.
        output: textual result (or error message when it failed).
        parameters: the parameters the node ran with, when known, so a planner
            can see exactly what failed and avoid repeating it.
        role: ``"result"`` for a normal node result, ``"checkpoint"`` for a
            compressed summary produced by a synthesizer.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str
    capability: str | None = None
    success: bool = True
    output: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    role: Literal["result", "checkpoint"] = "result"


class PlanningRequest(BaseModel):
    """Input handed to a :class:`Planner`.

    Args:
        request: the original user request.
        context: the shared execution context (state, history, capabilities).
        group: the scope being planned (``None`` means global/whole request).
        planners: descriptors of the planners/groups available for planning.
        synthesizers: descriptors of the synthesizers available, so the planner
            knows it may request compaction.
        observations: information gathered since the last checkpoint.
        checkpoint: compressed summary of earlier iterations, if any, produced
            by a synthesizer and fed back by the host.
        scratchpad: host-maintained, deterministic progress summary (one line
            per executed step). Unlike ``checkpoint`` it is not produced by an
            LLM, so it survives compaction without loss.
        max_nodes: host-imposed node budget for this plan, overriding the
            planner's own limit, when set.
        metadata: free-form planning metadata.

    ``capabilities`` and ``history`` are exposed as read-only properties backed
    by ``context`` so there is a single source of truth.
    """

    model_config = ConfigDict(extra="forbid")

    request: str
    context: ExecutionContext
    group: str | None = None
    planners: tuple[CapabilityDescriptor, ...] = ()
    synthesizers: tuple[CapabilityDescriptor, ...] = ()
    observations: tuple[Observation, ...] = ()
    checkpoint: str | None = None
    scratchpad: str = ""
    max_nodes: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def capabilities(self) -> tuple[CapabilityDescriptor, ...]:
        """Descriptors of the capabilities available for planning."""
        return self.context.capabilities

    @property
    def history(self) -> tuple[Message, ...]:
        """Prior context supplied by the host through the execution context."""
        return self.context.history


class CompactionRequest(BaseModel):
    """A planner's request to compact the accumulated observations.

    The core only carries the request; applying it (calling a synthesizer and
    replacing the folded observations with the resulting checkpoint) is the
    host's responsibility.

    Args:
        enabled: whether compaction was requested.
        keep_last: how many of the most recent observations to keep verbatim
            after the checkpoint (``0`` folds everything).
        reason: human-readable justification.
        metadata: free-form data for the host/synthesizer.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    keep_last: int = Field(default=0, ge=0)
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanningResult(BaseModel):
    """Output produced by a :class:`Planner`.

    Args:
        plan: the executable plan.
        rationale: optional explanation for the plan.
        needs_more_info: when true, the plan gathers information for a next
            planning iteration instead of completing the request.
        compaction: when set, asks the host to fold the accumulated
            observations into a checkpoint before the next iteration.
        usage: token accounting for this planning call, when the planner uses
            an LLM that reports it.
        metadata: free-form data about the planning process.
    """

    model_config = ConfigDict(extra="forbid")

    plan: ExecutionPlan
    rationale: str = ""
    needs_more_info: bool = False
    compaction: CompactionRequest | None = None
    usage: LLMUsage | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Planner(Capability):
    """A capability that produces an :class:`ExecutionPlan`."""

    kind = "planner"

    @abstractmethod
    def plan(self, request: PlanningRequest) -> PlanningResult:
        """Produce a plan for ``request``."""
        raise NotImplementedError
