from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from core import LLMChunk, LLMChunkCallback, LLMProvider, LLMResponse, Message
from forge_cli.session import ChatSession


class FakeProvider(LLMProvider):
    """Replies from a queue; records the messages it receives."""

    def __init__(self, replies: Sequence[str]) -> None:
        self._replies = list(replies)
        self._index = 0
        self.calls: list[list[Message]] = []

    @property
    def name(self) -> str:
        return "fake"

    def complete(
        self,
        messages: Sequence[Message],
        *,
        on_chunk: LLMChunkCallback | None = None,
        **options: Any,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        index = min(self._index, len(self._replies) - 1)
        content = self._replies[index]
        self._index += 1
        if on_chunk is not None:
            on_chunk(LLMChunk(content=content))
        return LLMResponse(message=Message(role="assistant", content=content))


def test_session_keeps_history() -> None:
    provider = FakeProvider(["hi", "again"])
    session = ChatSession(provider, stream=False)

    assert session.send("hello") == "hi"
    assert session.send("more") == "again"
    assert [message.role for message in session.history] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert provider.calls[0][0].content == "hello"
    assert len(provider.calls[1]) == 3


def test_session_system_prompt_and_clear() -> None:
    provider = FakeProvider(["ok"])
    session = ChatSession(provider, system_prompt="be nice", stream=False)
    assert session.history[0].role == "system"

    session.send("hi")
    session.clear()
    assert [message.role for message in session.history] == ["system"]

    session.set_system_prompt("be terse")
    assert session.history[0].content == "be terse"


def test_session_streams_chunks() -> None:
    provider = FakeProvider(["hello"])
    chunks: list[str] = []
    session = ChatSession(provider, stream=True, on_chunk=chunks.append)

    reply = session.send("hi")

    assert chunks == ["hello"]
    assert reply == "hello"
