"""Observability and control callbacks for the execution lifecycle.

Callbacks are **optional**: the core never requires a component to implement
them. An :class:`ExecutionObserver` receives informational events; a
:class:`ControlCallback` can inspect a finished node and request a control
action. Both are structural protocols, so any host object (CLI, Web UI, IDE,
test double) can satisfy them without importing core internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from core.agent.state import now_utc
from core.contracts.execution import ExecutionContext, ExecutionControl, NodeResult


class ExecutionEventKind(str, Enum):
    """Kinds of lifecycle events an observer may receive."""

    EXECUTION_START = "execution.start"
    EXECUTION_COMPLETE = "execution.complete"
    NODE_START = "node.start"
    NODE_COMPLETE = "node.complete"
    ERROR = "error"
    LLM_CHUNK = "llm.chunk"
    LLM_COMPLETE = "llm.complete"
    CAPABILITY_START = "capability.start"
    CAPABILITY_COMPLETE = "capability.complete"


@dataclass(frozen=True)
class ExecutionEvent:
    """A lifecycle event delivered to an :class:`ExecutionObserver`.

    Args:
        kind: the event kind.
        node_id: related plan node, when applicable.
        capability: related capability id, when applicable.
        error: error message for error events.
        data: free-form payload.
        timestamp: when the event was created.
    """

    kind: ExecutionEventKind
    node_id: str | None = None
    capability: str | None = None
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=now_utc)


@runtime_checkable
class ExecutionObserver(Protocol):
    """Receives informational execution events. Optional and side-effect-only."""

    def on_event(self, event: ExecutionEvent) -> None:
        ...


@runtime_checkable
class ControlCallback(Protocol):
    """Inspects a finished node and may request a control action.

    Returning ``None`` means "no request" (equivalent to continue). This lets an
    application observe, compact context, pause, interrupt or request a retry
    without the core knowing what kind of consumer it is.
    """

    def on_node_complete(
        self, context: ExecutionContext, result: NodeResult
    ) -> ExecutionControl | None:
        ...
