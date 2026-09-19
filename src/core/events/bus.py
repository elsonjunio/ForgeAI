"""In-process, synchronous event bus infrastructure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.events.event import Event
from core.events.types import EventHandler


@dataclass(frozen=True)
class Subscription:
    """Handle returned by :meth:`EventBus.subscribe` for later unsubscribe."""

    event_type: str
    handler: EventHandler


class EventBus:
    """Deliver events to registered handlers, keyed by ``event.type``.

    Handlers are called in subscription order. Handlers must not mutate the
    subscriber list while handling (copies are iterated), so subscribing or
    unsubscribing from within a handler is safe.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_type: str, handler: EventHandler) -> Subscription:
        """Register ``handler`` for ``event_type`` and return a subscription."""
        self._subscribers.setdefault(event_type, []).append(handler)
        return Subscription(event_type=event_type, handler=handler)

    def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a previously returned subscription, if still present."""
        handlers = self._subscribers.get(subscription.event_type)
        if not handlers:
            return
        try:
            handlers.remove(subscription.handler)
        except ValueError:
            return
        if not handlers:
            self._subscribers.pop(subscription.event_type, None)

    def publish(self, event: Event[Any]) -> None:
        """Deliver ``event`` to every handler subscribed to its type."""
        for handler in list(self._subscribers.get(event.type, ())):
            handler(event)

    def subscriber_count(self, event_type: str) -> int:
        return len(self._subscribers.get(event_type, ()))