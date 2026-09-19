"""Well-known event types and handler aliases used across the framework."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeAlias

from core.events.event import Event

EventHandler: TypeAlias = Callable[[Event[Any]], None]


class CoreEvents:
    """Event names emitted by the core runtime (as opposed to plugins)."""

    AGENT_STARTED = "agent.started"
    AGENT_FINISHED = "agent.finished"
    NODE_STARTED = "agent.node.started"
    NODE_FINISHED = "agent.node.finished"
    PLUGIN_ACTIVATED = "plugin.activated"
    PLUGIN_DEACTIVATED = "plugin.deactivated"


class WorkflowEvents:
    """Event names emitted by the code-agent workflow."""

    WORKFLOW_STARTED = "workflow.started"
    STAGE_STARTED = "workflow.stage.started"
    STAGE_FINISHED = "workflow.stage.finished"
    WORKFLOW_RETRY = "workflow.retry"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"