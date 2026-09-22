from __future__ import annotations

import io

from core import ExecutionEvent, ExecutionEventKind
from forge_cli.progress import ProgressObserver


def test_progress_observer_renders_node_events() -> None:
    stream = io.StringIO()
    observer = ProgressObserver(stream=stream)

    observer.on_event(
        ExecutionEvent(
            kind=ExecutionEventKind.NODE_START, node_id="n1", capability="tool:echo"
        )
    )
    observer.on_event(
        ExecutionEvent(
            kind=ExecutionEventKind.NODE_COMPLETE,
            node_id="n1",
            data={"success": True},
        )
    )
    observer.on_event(
        ExecutionEvent(
            kind=ExecutionEventKind.NODE_COMPLETE,
            node_id="n2",
            error="boom",
            data={"success": False},
        )
    )

    output = stream.getvalue()
    assert "→ n1 (tool:echo)" in output
    assert "✓ n1" in output
    assert "✗ n2: boom" in output


def test_progress_observer_ignores_execution_events() -> None:
    stream = io.StringIO()
    observer = ProgressObserver(stream=stream)

    observer.on_event(ExecutionEvent(kind=ExecutionEventKind.EXECUTION_START))
    observer.on_event(ExecutionEvent(kind=ExecutionEventKind.EXECUTION_COMPLETE))

    assert stream.getvalue() == ""
