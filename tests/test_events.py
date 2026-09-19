from __future__ import annotations

from core.events.bus import EventBus, Subscription
from core.events.event import Event
from core.events.types import CoreEvents


def test_subscribe_and_publish_delivers(bus: EventBus) -> None:
    received: list[Event[object]] = []

    bus.subscribe(CoreEvents.AGENT_STARTED, received.append)
    bus.publish(Event[object](type=CoreEvents.AGENT_STARTED, source="tester", payload={"n": 1}))

    assert len(received) == 1
    assert received[0].type == CoreEvents.AGENT_STARTED
    assert received[0].source == "tester"
    assert received[0].payload == {"n": 1}


def test_publish_without_subscribers_is_noop(bus: EventBus) -> None:
    bus.publish(Event[object](type="ghost.event", payload=None))
    assert bus.subscriber_count("ghost.event") == 0


def test_unsubscribe_stops_delivery(bus: EventBus) -> None:
    received: list[Event[object]] = []

    subscription = bus.subscribe("x", received.append)
    bus.publish(Event[object](type="x", payload=None))
    bus.unsubscribe(subscription)
    bus.publish(Event[object](type="x", payload=None))

    assert len(received) == 1


def test_subscription_is_frozen_token() -> None:
    subscription = Subscription(event_type="a", handler=lambda e: None)
    assert subscription.event_type == "a"


def test_handlers_are_isolated_per_type(bus: EventBus) -> None:
    on_a: list[Event[object]] = []
    on_b: list[Event[object]] = []

    bus.subscribe("a", on_a.append)
    bus.subscribe("b", on_b.append)
    bus.publish(Event[object](type="a", payload=None))

    assert len(on_a) == 1
    assert len(on_b) == 0


def test_subscriber_count_tracks_handlers(bus: EventBus) -> None:
    def handler(_: Event[object]) -> None:
        return None

    bus.subscribe("a", handler)
    assert bus.subscriber_count("a") == 1
    bus.subscribe("a", handler)
    assert bus.subscriber_count("a") == 2


def test_event_has_aware_timestamp(bus: EventBus) -> None:
    captured: list[Event[object]] = []
    bus.subscribe("ts", captured.append)
    bus.publish(Event[object](type="ts", payload=None))
    assert captured[0].timestamp.tzinfo is not None