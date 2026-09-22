"""LLM provider contract.

The core is provider-neutral: this module only *describes* how an LLM backend is
exposed. No provider is implemented or shipped here.

A provider accumulates the full response and returns an :class:`LLMResponse`.
Streaming is observational: when a chunk callback is given, the provider emits
:class:`LLMChunk` values to it as they arrive, but the caller never needs to
reconstruct the response from chunks.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeAlias

from core.agent.state import Message
from core.contracts.capability import Capability


@dataclass(frozen=True)
class LLMUsage:
    """Token accounting reported by a provider, when available."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


def merge_usage(*usages: LLMUsage | None) -> LLMUsage | None:
    """Sum token usage across calls.

    Missing values are ignored; a field stays ``None`` when no call reported it,
    and ``None`` is returned when no usage was provided at all.
    """
    present = [usage for usage in usages if usage is not None]
    if not present:
        return None

    def _sum(field: str) -> int | None:
        values = [
            getattr(usage, field)
            for usage in present
            if getattr(usage, field) is not None
        ]
        return sum(values) if values else None

    return LLMUsage(
        prompt_tokens=_sum("prompt_tokens"),
        completion_tokens=_sum("completion_tokens"),
        total_tokens=_sum("total_tokens"),
    )


@dataclass(frozen=True)
class LLMChunk:
    """A partial piece of a streaming completion.

    Chunks are informational; the caller continues using the accumulated
    :class:`LLMResponse`.
    """

    content: str = ""
    index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


LLMChunkCallback: TypeAlias = Callable[[LLMChunk], None]


@dataclass(frozen=True)
class LLMResponse:
    """The accumulated result of an LLM completion.

    Args:
        message: the assistant message produced by the provider.
        usage: token accounting, when the provider reports it.
        metadata: provider-specific data (model, finish reason, ...).
    """

    message: Message
    usage: LLMUsage | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content(self) -> str:
        """Convenience access to the assistant message content."""
        return self.message.content


class LLMProvider(Capability):
    """An LLM backend contributed by a plugin.

    Implementations receive the conversation as :class:`Message` objects and
    return the accumulated :class:`LLMResponse`. If ``on_chunk`` is provided they
    should call it for each streamed piece; the callback is observational and
    must not change the returned response.
    """

    kind = "llm"

    @abstractmethod
    def complete(
        self,
        messages: Sequence[Message],
        *,
        on_chunk: LLMChunkCallback | None = None,
        **options: Any,
    ) -> LLMResponse:
        """Return the accumulated assistant reply for ``messages``."""
        raise NotImplementedError
