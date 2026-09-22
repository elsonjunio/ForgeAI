"""Validator contract: post-execution checks contributed by plugins.

Validators are capability providers. The core defines the interface only;
concrete validators (linters, test runners, policy checks, ...) are contributed
by plugins and invoked by whoever needs them (a planner, another capability or
the host).
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.contracts.capability import Capability
from core.contracts.llm import LLMUsage
from core.contracts.planning import Observation


@dataclass(frozen=True)
class ValidationInput:
    """Data handed to a :class:`Validator`.

    A validator judges the **whole outcome** of a run, not a single node, so it
    receives the accumulated observations (plus the deterministic scratchpad and
    any checkpoint) in addition to the original request.

    Args:
        request: the original user request.
        task: description of the task that was executed, when any.
        output: the produced output for that task, when any.
        success: whether the run completed without a non-recoverable failure.
        observations: steps executed, with success/params/output.
        checkpoint: compressed summary of earlier steps, when any.
        scratchpad: deterministic progress summary maintained by the host.
    """

    request: str
    task: str | None = None
    output: str | None = None
    success: bool = True
    observations: tuple[Observation, ...] = ()
    checkpoint: str = ""
    scratchpad: str = ""


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of a single validation.

    Args:
        passed: whether the validation succeeded.
        messages: human-readable findings (what is missing, when it failed).
        usage: token accounting for the validation call, when it used an LLM.
        metadata: free-form structured data (rule ids, file names, ...).
    """

    passed: bool
    messages: tuple[str, ...] = ()
    usage: LLMUsage | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Validator(Capability):
    """A post-execution validator contributed by a plugin."""

    kind = "validator"

    @abstractmethod
    def validate(self, data: ValidationInput) -> ValidationResult:
        """Validate ``data`` and return the result."""
        raise NotImplementedError
