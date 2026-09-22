"""Synthesis contract: how a capability turns prior steps into an answer/summary.

A synthesizer is a capability (``kind="synthesizer"``) contributed by a plugin.
It reads the information gathered by previous plan/execute iterations — the
``Observation`` list and an optional prior ``checkpoint`` — and produces either
a user-facing answer (``mode="answer"``) or a compressed checkpoint
(``mode="compact"``).

The core defines the contract only; no synthesis implementation and no
compaction policy live here. In particular, a synthesizer is **not** an
``Executable`` capability: the planner does not place it in a plan. Instead the
planner may request compaction through
:class:`~core.contracts.planning.CompactionRequest`, and the host runs the
synthesizer to obtain the answer/checkpoint.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.contracts.capability import Capability
from core.contracts.llm import LLMUsage
from core.contracts.planning import Observation

SynthesisMode = Literal["answer", "compact"]


class SynthesisRequest(BaseModel):
    """Input handed to a :class:`Synthesizer`.

    Args:
        request: the original user request.
        observations: information gathered since the last checkpoint.
        checkpoint: compressed summary produced by a previous compaction, if any.
        mode: ``"answer"`` to produce a user-facing answer, ``"compact"`` to
            produce a compressed checkpoint.
        metadata: free-form synthesis metadata.
    """

    model_config = ConfigDict(extra="forbid")

    request: str
    observations: tuple[Observation, ...] = ()
    checkpoint: str | None = None
    mode: SynthesisMode = "answer"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Synthesis(BaseModel):
    """Output produced by a :class:`Synthesizer`.

    Args:
        text: the answer when ``mode="answer"``, or the compressed checkpoint
            when ``mode="compact"``.
        usage: token accounting for this call, when the synthesizer uses an LLM
            that reports it.
        metadata: free-form data about the synthesis process.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = ""
    usage: LLMUsage | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Synthesizer(Capability):
    """A capability that synthesizes an answer or a compressed checkpoint."""

    kind = "synthesizer"

    @abstractmethod
    def synthesize(self, request: SynthesisRequest) -> Synthesis:
        """Produce an answer or checkpoint for ``request``."""
        raise NotImplementedError
