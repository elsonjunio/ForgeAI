"""Live progress rendering for plan execution events."""

from __future__ import annotations

import sys
from typing import TextIO

from core import ExecutionEvent, ExecutionEventKind


class ProgressObserver:
    """Print node-level progress as execution events arrive.

    Writes to ``stderr`` by default so it does not interleave with the buffered
    command output printed on ``stdout``.
    """

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stderr

    def on_event(self, event: ExecutionEvent) -> None:
        if event.kind is ExecutionEventKind.NODE_START:
            self._write(f"  → {event.node_id} ({event.capability or '?'})")
        elif event.kind is ExecutionEventKind.NODE_COMPLETE:
            if event.data.get("success", True):
                self._write(f"  ✓ {event.node_id}")
            else:
                self._write(f"  ✗ {event.node_id}: {event.error or 'failed'}")

    def _write(self, text: str) -> None:
        print(text, file=self._stream, flush=True)
