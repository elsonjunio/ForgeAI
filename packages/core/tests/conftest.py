from __future__ import annotations

import pytest

from core.agent.state import AgentState
from core.events.bus import EventBus


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def empty_state() -> AgentState:
    return AgentState(task="do nothing")