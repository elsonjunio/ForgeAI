"""LLM provider contract.

The core is provider-neutral: this module only *describes* how an LLM backend is
exposed. No provider is implemented or shipped here.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from typing import Any

from core.agent.state import Message
from core.contracts.capability import Capability


class LLMProvider(Capability):
    """An LLM backend contributed by a plugin.

    Implementations receive the conversation as :class:`Message` objects and
    return the assistant reply. Streaming, retries and provider-specific
    options are intentionally left out of the contract; extra keyword arguments
    are accepted and passed through by convention.
    """

    kind = "llm"

    @abstractmethod
    def complete(self, messages: Sequence[Message], **options: Any) -> Message:
        """Return the assistant reply for ``messages``."""
        raise NotImplementedError
