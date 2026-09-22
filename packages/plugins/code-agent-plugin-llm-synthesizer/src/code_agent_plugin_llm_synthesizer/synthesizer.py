"""LLM-based synthesizer: turns prior steps into an answer or a checkpoint.

The synthesizer resolves the default :class:`~core.LLMProvider` through a
:class:`~core.CapabilitySource` (provided by the plugin context) and converts the
accumulated :class:`~core.Observation` list — plus an optional prior checkpoint —
into text. It supports two modes:

* ``"answer"``: a user-facing final answer (it also sees the prior checkpoint);
* ``"compact"``: a compressed checkpoint that replaces the folded observations,
  so an iterative host can keep the planner's context bounded.

The plugin only implements the synthesis contract; deciding when to compact and
feeding the checkpoint back to the planner is the host's job.
"""

from __future__ import annotations

from core import (
    CoreError,
    LLMProvider,
    Message,
    MissingCapabilityError,
    Observation,
    Synthesis,
    SynthesisRequest,
    Synthesizer,
)
from core.contracts.registry import CapabilitySource

DEFAULT_MAX_OBSERVATION_CHARS = 2000

_SYSTEM_PROMPT = (
    "You are a synthesis component for an iterative agent. You receive the "
    "user's request, an optional checkpoint summarizing earlier steps and the "
    "results of the steps executed since. Follow the requested mode exactly:\n"
    "- mode 'answer': answer the user's request directly and completely, using "
    "the gathered steps as evidence (do not merely list the steps).\n"
    "- mode 'compact': reply with a compact checkpoint preserving only the "
    "facts, decisions, artifacts and open questions needed to keep working.\n"
    "Return only the requested text: no JSON, no preamble, no commentary."
)


class LLMSynthesizerError(CoreError):
    """Raised when the synthesizer cannot produce a result."""


class LLMSynthesizer(Synthesizer):
    """A synthesizer that delegates answer/checkpoint generation to an LLM.

    Args:
        source: capability source used to resolve the LLM provider.
        provider_name: specific provider name; defaults to the default provider.
        system_prompt: overrides the built-in synthesis instruction.
        max_observation_chars: per-observation truncation used when building the
            prompt, so a single large step cannot blow the context budget.
    """

    def __init__(
        self,
        *,
        source: CapabilitySource,
        provider_name: str | None = None,
        system_prompt: str | None = None,
        max_observation_chars: int = DEFAULT_MAX_OBSERVATION_CHARS,
    ) -> None:
        if max_observation_chars < 1:
            raise ValueError("max_observation_chars must be >= 1")
        self._source = source
        self._provider_name = provider_name
        self._system_prompt = system_prompt or _SYSTEM_PROMPT
        self._max_observation_chars = max_observation_chars

    @property
    def name(self) -> str:
        return "llm-synthesizer"

    def synthesize(self, request: SynthesisRequest) -> Synthesis:
        """Ask the LLM for the answer (``mode="answer"``) or checkpoint."""
        provider = self._resolve_provider()
        response = provider.complete(
            [
                Message(role="system", content=self._system_prompt),
                Message(role="user", content=self._build_prompt(request)),
            ]
        )
        text = response.content.strip()
        if not text:
            raise LLMSynthesizerError(
                f"synthesizer returned empty text for mode {request.mode!r}"
            )
        return Synthesis(
            text=text,
            usage=response.usage,
            metadata={"provider": provider.name, "mode": request.mode},
        )

    def _resolve_provider(self) -> LLMProvider:
        if self._provider_name is not None:
            capability = self._source.capability(LLMProvider, self._provider_name)
        else:
            capability = self._source.default_capability(LLMProvider)
        if not isinstance(capability, LLMProvider):
            raise MissingCapabilityError(
                "no LLM provider available for synthesis; install an LLM plugin"
            )
        return capability

    def _build_prompt(self, request: SynthesisRequest) -> str:
        return (
            f"Mode: {request.mode}\n\n"
            f"User request:\n{request.request}\n\n"
            f"Previous checkpoint:\n{request.checkpoint or '(none)'}\n\n"
            "Steps since the last checkpoint:\n"
            f"{self._format_observations(request.observations)}\n\n"
            f"Produce the {request.mode} text."
        )

    def _format_observations(self, observations: tuple[Observation, ...]) -> str:
        if not observations:
            return "(none)"
        return "\n".join(self._format_observation(obs) for obs in observations)

    def _format_observation(self, observation: Observation) -> str:
        output = observation.output
        truncated = len(output) > self._max_observation_chars
        body = output[: self._max_observation_chars]
        suffix = "…" if truncated else ""
        status = "ok" if observation.success else "failed"
        label = observation.capability or "?"
        return f"- {observation.node_id} ({label}) [{status}]: {body}{suffix}"


__all__ = [
    "DEFAULT_MAX_OBSERVATION_CHARS",
    "LLMSynthesizer",
    "LLMSynthesizerError",
]
