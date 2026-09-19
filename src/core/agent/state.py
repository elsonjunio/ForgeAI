"""Domain model for the agent state.

The state is a plain Pydantic model: it does not depend on LangGraph or on any
LLM provider. It is the only unit of information that flows through the agent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["system", "user", "assistant", "tool"]
AgentStatus = Literal["idle", "running", "completed", "failed"]


def now_utc() -> datetime:
    """Return the current UTC timestamp (timezone-aware)."""
    return datetime.now(timezone.utc)


class Message(BaseModel):
    """A single message in the agent conversation."""

    model_config = ConfigDict(extra="forbid")

    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None


class AgentState(BaseModel):
    """The evolving state of an agent run.

    Plugins contribute transformations of this state; the runtime is responsible
    for executing them. Unknown fields are rejected so wiring mistakes surface
    early; store free-form data in ``metadata`` instead.
    """

    model_config = ConfigDict(extra="forbid")

    task: str | None = None
    system_prompt: str = ""
    messages: list[Message] = Field(default_factory=list)
    output: str | None = None
    status: AgentStatus = "idle"
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=now_utc)

    def add_message(self, message: Message | str, *, role: Role | None = None) -> Message:
        """Append a message (string or ``Message``) and stamp the state.

        Args:
            message: message body or already-built :class:`Message`.
            role: role to use when ``message`` is a ``str`` (defaults to "user").
        """
        if isinstance(message, str):
            message = Message(role=role or "user", content=message)
        self.messages.append(message)
        self.touch()
        return message

    def touch(self) -> None:
        """Refresh the ``updated_at`` timestamp."""
        self.updated_at = now_utc()