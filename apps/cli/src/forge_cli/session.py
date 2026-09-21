"""Host-owned chat session: history plus a resolved LLM provider."""

from __future__ import annotations

from collections.abc import Callable

from core import LLMChunk, LLMProvider, Message


class ChatSession:
    """Keeps the conversation history and calls the provider.

    The history lives in the host (this class); the core never fetches it.

    Args:
        provider: the LLM provider used to produce replies.
        system_prompt: optional system message kept at the head of the history.
        stream: when true, pass an ``on_chunk`` callback to the provider.
        on_chunk: receives streamed text pieces (host rendering).
    """

    def __init__(
        self,
        provider: LLMProvider,
        *,
        system_prompt: str | None = None,
        stream: bool = True,
        on_chunk: Callable[[str], None] | None = None,
    ) -> None:
        self._provider = provider
        self._system_prompt = system_prompt
        self._stream = stream
        self._on_chunk = on_chunk
        self._history: list[Message] = []
        if system_prompt:
            self._history.append(Message(role="system", content=system_prompt))

    @property
    def provider(self) -> LLMProvider:
        return self._provider

    @property
    def history(self) -> list[Message]:
        """A copy of the current history."""
        return list(self._history)

    def clear(self) -> None:
        """Reset the history, keeping the system prompt if any."""
        self._history = []
        if self._system_prompt:
            self._history.append(Message(role="system", content=self._system_prompt))

    def set_system_prompt(self, text: str) -> None:
        """Replace the system prompt, preserving the rest of the history."""
        self._system_prompt = text
        rest = [message for message in self._history if message.role != "system"]
        self._history = (
            [Message(role="system", content=text)] if text else []
        ) + rest

    def send(self, user_text: str) -> str:
        """Append the user message, call the provider and return the reply."""
        self._history.append(Message(role="user", content=user_text))
        callback = self._chunk_callback() if self._stream else None
        response = self._provider.complete(self._history, on_chunk=callback)
        self._history.append(response.message)
        return response.content

    def _chunk_callback(self) -> Callable[[LLMChunk], None] | None:
        if self._on_chunk is None:
            return None
        render = self._on_chunk

        def emit(chunk: LLMChunk) -> None:
            if chunk.content:
                render(chunk.content)

        return emit
