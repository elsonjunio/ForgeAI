"""Explicit, typed state for the code-agent workflow.

The workflow state is a plain Pydantic model: it does not depend on LangGraph
and is the only unit of information flowing through the workflow graph. Keeping
it explicit makes each stage's inputs and outputs auditable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from core.agent.state import now_utc
from core.contracts.plugin import PluginMetadata

WorkflowStatus = Literal["idle", "running", "completed", "failed"]
TaskStatus = Literal["pending", "running", "completed", "failed"]


class Task(BaseModel):
    """A unit of work derived from the plan."""

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    status: TaskStatus = "pending"
    output: str | None = None


class Plan(BaseModel):
    """The plan produced by the planning stage."""

    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    tasks: list[Task] = Field(default_factory=list)


class DiscoveredContext(BaseModel):
    """Context gathered by the discovery stage.

    ``capabilities`` maps a capability ``kind`` to the names of the registered
    providers. ``plugins`` carries the metadata of plugins returned by the
    registered discoverers.
    """

    model_config = ConfigDict(extra="forbid")

    capabilities: dict[str, list[str]] = Field(default_factory=dict)
    plugins: list[PluginMetadata] = Field(default_factory=list)


class ValidationRecord(BaseModel):
    """The result of one validator run against the current task."""

    model_config = ConfigDict(extra="forbid")

    validator: str
    passed: bool
    messages: tuple[str, ...] = ()
    task_id: str | None = None


class ReviewResult(BaseModel):
    """The outcome of the review stage."""

    model_config = ConfigDict(extra="forbid")

    approved: bool
    feedback: str = ""
    summary: str = ""


class WorkflowError(BaseModel):
    """A non-fatal error captured by a stage."""

    model_config = ConfigDict(extra="forbid")

    stage: str
    type: str
    message: str


class WorkflowState(BaseModel):
    """The evolving state of a code-agent workflow run.

    Tracks the user request, the discovered context, the plan, the current and
    completed tasks, validations, the review, errors and the overall status.
    Unknown fields are rejected so wiring mistakes surface early. A single field
    (``metadata``) is available for free-form data.
    """

    model_config = ConfigDict(extra="forbid")

    request: str | None = None
    context: DiscoveredContext = Field(default_factory=DiscoveredContext)
    plan: Plan | None = None
    current_task: Task | None = None
    completed_tasks: list[Task] = Field(default_factory=list)
    validations: list[ValidationRecord] = Field(default_factory=list)
    review: ReviewResult | None = None
    errors: list[WorkflowError] = Field(default_factory=list)
    status: WorkflowStatus = "idle"
    attempts: int = 0
    metadata: dict[str, object] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=now_utc)

    def add_error(self, *, stage: str, error_type: str, message: str) -> None:
        """Append a non-fatal error and stamp the state."""
        self.errors.append(
            WorkflowError(stage=stage, type=error_type, message=message)
        )
        self.touch()

    def touch(self) -> None:
        """Refresh the ``updated_at`` timestamp."""
        self.updated_at = now_utc()
