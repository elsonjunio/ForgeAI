"""LLM-based validator: judges whether a run fulfilled the user's request.

Unlike a per-node check, a validator inspects the **whole outcome** — the
accumulated observations, the checkpoint and the deterministic scratchpad — and
decides whether the request was satisfied. It is a capability invoked by the
host after the plan completes; it is not a plan node.

The plugin only implements the validation contract; feeding failures back to the
planner (or not) is the host's job.
"""

from __future__ import annotations

import json
import re

from core import (
    CoreError,
    LLMProvider,
    Message,
    MissingCapabilityError,
    Observation,
    ValidationInput,
    ValidationResult,
    Validator,
)
from core.contracts.registry import CapabilitySource

DEFAULT_MAX_OBSERVATION_CHARS = 1500

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

_SYSTEM_PROMPT = (
    "You are a verification component for an iterative agent. Given the user's "
    "request, an optional checkpoint and the steps already executed, decide "
    "whether the request was fulfilled. Be strict but fair: only pass when the "
    "gathered evidence actually answers the request. Reply with JSON of the "
    'shape {"passed": boolean, "issues": [string]}, where "issues" lists what is '
    "still missing or wrong (empty when passed). Return only JSON."
)


class LLMValidatorError(CoreError):
    """Raised when the validator cannot produce a verdict."""


class LLMValidator(Validator):
    """A validator that asks an LLM whether the run satisfied the request.

    Args:
        source: capability source used to resolve the LLM provider.
        provider_name: specific provider name; defaults to the default provider.
        system_prompt: overrides the built-in verification instruction.
        max_observation_chars: per-observation truncation when building the
            prompt.
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
        return "llm-validator"

    def validate(self, data: ValidationInput) -> ValidationResult:
        """Ask the LLM for a verdict on ``data`` and validate it."""
        provider = self._resolve_provider()
        response = provider.complete(
            [
                Message(role="system", content=self._system_prompt),
                Message(role="user", content=self._build_prompt(data)),
            ]
        )
        passed, issues = self._parse_response(response.content)
        return ValidationResult(
            passed=passed,
            messages=tuple(issues),
            usage=response.usage,
            metadata={"provider": provider.name},
        )

    def _resolve_provider(self) -> LLMProvider:
        if self._provider_name is not None:
            capability = self._source.capability(LLMProvider, self._provider_name)
        else:
            capability = self._source.default_capability(LLMProvider)
        if not isinstance(capability, LLMProvider):
            raise MissingCapabilityError(
                "no LLM provider available for validation; install an LLM plugin"
            )
        return capability

    def _build_prompt(self, data: ValidationInput) -> str:
        return (
            f"User request:\n{data.request}\n\n"
            f"Run completed without a fatal failure: {data.success}\n\n"
            f"Previous checkpoint:\n{data.checkpoint or '(none)'}\n\n"
            f"Progress so far:\n{data.scratchpad or '(none)'}\n\n"
            "Steps executed:\n"
            f"{self._format_observations(data.observations)}\n\n"
            "Produce the JSON verdict."
        )

    def _format_observations(self, observations: tuple[Observation, ...]) -> str:
        if not observations:
            return "(none)"
        return "\n".join(self._format_observation(obs) for obs in observations)

    def _format_observation(self, observation: Observation) -> str:
        status = "ok" if observation.success else "FAILED"
        output = observation.output[: self._max_observation_chars]
        suffix = "…" if len(observation.output) > self._max_observation_chars else ""
        parameters = (
            f" params={json.dumps(observation.parameters, sort_keys=True)}"
            if observation.parameters
            else ""
        )
        return (
            f"- {observation.node_id} ({observation.capability or '?'}) "
            f"[{status}]{parameters}: {output}{suffix}"
        )

    def _parse_response(self, content: str) -> tuple[bool, list[str]]:
        raw = self._extract_json(content)
        if raw is None:
            raise LLMValidatorError("validator did not return JSON")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMValidatorError(f"invalid verdict JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMValidatorError("verdict JSON must be an object")
        passed = bool(data.get("passed", False))
        raw_issues = data.get("issues", [])
        if not isinstance(raw_issues, list):
            raise LLMValidatorError("verdict 'issues' must be a list")
        issues = [str(issue) for issue in raw_issues]
        return passed, issues

    @staticmethod
    def _extract_json(content: str) -> str | None:
        fenced = _JSON_FENCE.search(content)
        if fenced is not None:
            return fenced.group(1).strip()
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end < start:
            return None
        return content[start : end + 1]


__all__ = [
    "DEFAULT_MAX_OBSERVATION_CHARS",
    "LLMValidator",
    "LLMValidatorError",
]
