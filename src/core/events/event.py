"""Event model and well-known event names."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

Payload = TypeVar("Payload")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Event(BaseModel, Generic[Payload]):
    """A domain event published by the core or by plugins.

    The payload is generic and intentionally untyped at the boundary; concrete
    event contracts can subclass ``Event`` to narrow the payload type.
    """

    type: str
    payload: Payload | None = None
    source: str = "core"
    timestamp: datetime = Field(default_factory=now_utc)