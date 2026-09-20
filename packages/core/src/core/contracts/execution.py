"""Execution context and result contracts, independent of any engine.

``ExecutionContext`` is the shared bag of information handed between the
runtime, nodes and plugins. ``NodeResult`` and ``ExecutionControl`` standardize
the outcome of running a node and any control request a callback may issue.

The core never fetches conversation history: ``ExecutionContext.history`` is
provided explicitly by the host application.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from core.agent.state import AgentState, Message
from core.contracts.capability import CapabilityDescriptor
from core.contracts.plan import PlanNode


class ControlAction(str, Enum):
    """Actions a callback may request for the running execution."""

    CONTINUE = "continue"
    PAUSE = "pause"
    INTERRUPT = "interrupt"
    RETRY = "retry"


@dataclass(frozen=True)
class ExecutionControl:
    """A control request returned by a callback.

    The core only defines the contract; pause/resume/checkpoint semantics are
    left to the execution engine.

    Args:
        action: requested action.
        reason: human-readable justification.
        retry_from: node id to retry from, when ``action`` is ``RETRY``.
        metadata: free-form data for the engine.
    """

    action: ControlAction = ControlAction.CONTINUE
    reason: str = ""
    retry_from: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def should_continue(self) -> bool:
        return self.action is ControlAction.CONTINUE


class ExecutionContext(BaseModel):
    """Shared execution context passed between runtime, nodes and plugins.

    Args:
        request: the current user request.
        state: the shared (plugin-facing) agent state.
        metadata: free-form execution metadata.
        capabilities: descriptors of the capabilities available for planning.
        history: prior conversation/context, supplied explicitly by the host.
    """

    model_config = ConfigDict(extra="forbid")

    request: str
    state: AgentState = Field(default_factory=AgentState)
    metadata: dict[str, Any] = Field(default_factory=dict)
    capabilities: tuple[CapabilityDescriptor, ...] = ()
    history: tuple[Message, ...] = ()


@dataclass(frozen=True)
class NodeResult:
    """Standardized result of executing a plan node.

    Generic enough for any capability to report success/failure plus data useful
    for observability.

    Args:
        node_id: the plan node this result belongs to.
        success: whether the node succeeded.
        output: generic output payload.
        error: error message when ``success`` is ``False``.
        metadata: free-form data (usage, paths, ...).
        started_at / finished_at: timestamps for duration/observability.
    """

    node_id: str
    success: bool
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def duration_ms(self) -> float | None:
        """Wall-clock duration in milliseconds, when both timestamps exist."""
        if self.started_at is None or self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds() * 1000

    @classmethod
    def ok(cls, node_id: str, output: Any = None, **metadata: Any) -> NodeResult:
        """Build a successful result."""
        return cls(node_id=node_id, success=True, output=output, metadata=dict(metadata))

    @classmethod
    def failed(cls, node_id: str, error: str, **metadata: Any) -> NodeResult:
        """Build a failed result."""
        return cls(node_id=node_id, success=False, error=error, metadata=dict(metadata))


@dataclass(frozen=True)
class NodeExecutionRequest:
    """Input handed to an executable capability for a single plan node.

    Args:
        node: the plan node being executed.
        context: the shared execution context.
        results: results of nodes that already completed (read-only snapshot).
    """

    node: PlanNode
    context: ExecutionContext
    results: dict[str, NodeResult] = field(default_factory=dict)


@runtime_checkable
class Executable(Protocol):
    """Structural contract for a capability that can run as a plan node.

    The core does not require capabilities to inherit from this protocol; a
    capability satisfies it by providing an ``execute`` method.
    """

    def execute(self, request: NodeExecutionRequest) -> NodeResult:
        ...


ExecutionStatus = Literal["completed", "failed", "stopped"]


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of running a whole plan.

    Args:
        success: whether the run completed with every node succeeding.
        status: ``"completed"``, ``"failed"`` or ``"stopped"``.
        results: per-node results, keyed by node id.
        control: the control action that ended the run.
        error: human-readable error summary, when any.
        metadata: free-form data for the host.
    """

    success: bool
    status: ExecutionStatus
    results: dict[str, NodeResult] = field(default_factory=dict)
    control: ExecutionControl = field(default_factory=ExecutionControl)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
