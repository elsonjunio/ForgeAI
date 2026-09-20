from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from core.agent.state import AgentState, Message


def test_state_defaults() -> None:
    state = AgentState()
    assert state.task is None
    assert state.system_prompt == ""
    assert state.messages == []
    assert state.output is None
    assert state.status == "idle"
    assert state.metadata == {}
    assert isinstance(state.updated_at, datetime)


def test_state_accepts_extra_freeform_metadata() -> None:
    state = AgentState(task="refactor", metadata={"branch": "feature/x"})
    assert state.metadata["branch"] == "feature/x"


def test_state_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AgentState(totally_unknown="nope")  # type: ignore[call-arg]


def test_add_message_from_string() -> None:
    state = AgentState(task="hello")
    message = state.add_message("hi")
    assert message.role == "user"
    assert message.content == "hi"
    assert len(state.messages) == 1
    assert state.messages[0].role == "user"


def test_add_message_with_explicit_role() -> None:
    state = AgentState()
    message = state.add_message("system note", role="system")
    assert message.role == "system"


def test_add_message_from_object() -> None:
    state = AgentState()
    state.add_message(Message(role="assistant", content="ok"))
    assert state.messages[0].role == "assistant"


def test_add_message_touches_updated_at() -> None:
    state = AgentState()
    before = state.updated_at
    state.add_message("ring")
    assert state.updated_at >= before


def test_message_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        Message(role="robot", content="hi")


def test_status_transitions_are_literals() -> None:
    state = AgentState(status="running")
    assert state.status == "running"
    with pytest.raises(ValidationError):
        AgentState(status="done")


def test_copy_constructs_new_state() -> None:
    original = AgentState(task="t")
    updated = original.model_copy(update={"status": "completed"})
    assert updated.status == "completed"
    assert original.status == "idle"