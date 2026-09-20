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


@dataclass(frozen=True)
class ValidationInput:
    """Data handed to a :class:`Validator`.

    Args:
        request: the original user request.
        task: description of the task that was executed, when any.
        output: the produced output for that task, when any.
    """

    request: str
    task: str | None = None
    output: str | None = None


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of a single validation.

    Args:
        passed: whether the validation succeeded.
        messages: human-readable findings.
        metadata: free-form structured data (rule ids, file names, ...).
    """

    passed: bool
    messages: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


class Validator(Capability):
    """A post-execution validator contributed by a plugin."""

    kind = "validator"

    @abstractmethod
    def validate(self, data: ValidationInput) -> ValidationResult:
        """Validate ``data`` and return the result."""
        raise NotImplementedError
