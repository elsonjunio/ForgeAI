"""Workflow stubs used by the test-suite (never shipped by the core)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from core.agent.state import Message
from core.contracts.llm import LLMProvider
from core.contracts.validator import ValidationInput, ValidationResult, Validator


class ScriptedLLMProvider(LLMProvider):
    """Returns queued replies; repeats the last one when the queue is exhausted.

    Records every call so tests can inspect the prompts.
    """

    def __init__(
        self,
        responses: Sequence[str] = (),
        name: str = "scripted",
        *,
        default: bool = True,
    ) -> None:
        self._responses = list(responses)
        self._name = name
        self._index = 0
        self.default = default
        self.calls: list[list[Message]] = []

    @property
    def name(self) -> str:
        return self._name

    def complete(self, messages: Sequence[Message], **options: Any) -> Message:
        self.calls.append(list(messages))
        if self._index < len(self._responses):
            content = self._responses[self._index]
            self._index += 1
        elif self._responses:
            content = self._responses[-1]
        else:
            content = ""
        return Message(role="assistant", content=content)


class AlwaysPassValidator(Validator):
    """Always passes; records the inputs it saw."""

    def __init__(self, name: str = "pass") -> None:
        self._name = name
        self.inputs: list[ValidationInput] = []

    @property
    def name(self) -> str:
        return self._name

    def validate(self, data: ValidationInput) -> ValidationResult:
        self.inputs.append(data)
        return ValidationResult(passed=True, messages=("ok",))


class AlwaysFailValidator(Validator):
    """Always fails."""

    def __init__(self, name: str = "fail") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def validate(self, data: ValidationInput) -> ValidationResult:
        return ValidationResult(passed=False, messages=("broken",))


class FailOnceValidator(Validator):
    """Fails the first validation and passes the following ones."""

    def __init__(self, name: str = "flaky") -> None:
        self._name = name
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    def validate(self, data: ValidationInput) -> ValidationResult:
        self.calls += 1
        passed = self.calls > 1
        return ValidationResult(
            passed=passed,
            messages=("first attempt",) if not passed else ("recovered",),
        )


class RaisingValidator(Validator):
    """Raises a non-core error, to test observability of unexpected failures."""

    def __init__(self, name: str = "boom") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def validate(self, data: ValidationInput) -> ValidationResult:
        raise RuntimeError("validator exploded")
