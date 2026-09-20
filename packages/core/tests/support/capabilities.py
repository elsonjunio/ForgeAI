"""Capability stubs used by the test-suite (never shipped by the core)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from core.agent.state import Message
from core.contracts.analyzer import AnalysisResult, CodeAnalyzer
from core.contracts.capability import Capability
from core.contracts.discovery import Discoverer
from core.contracts.llm import LLMProvider, LLMResponse
from core.contracts.tool import Tool, ToolContract, ToolResult
from core.contracts.validator import ValidationInput, ValidationResult, Validator
from core.plugins.base import Plugin
from core.plugins.context import PluginContext


class FakeLLMProvider(LLMProvider):
    """Minimal LLM provider; records the messages it receives."""

    def __init__(self, name: str = "fake-llm", *, default: bool = False) -> None:
        self._name = name
        self.default = default
        self.calls: list[Sequence[Message]] = []

    @property
    def name(self) -> str:
        return self._name

    def complete(self, messages: Sequence[Message], **options: Any) -> LLMResponse:
        self.calls.append(messages)
        return LLMResponse(
            message=Message(role="assistant", content=f"{self._name}:{len(messages)}")
        )


class FakeTool(Tool):
    """Minimal executable tool."""

    def __init__(self, name: str = "echo", *, default: bool = False) -> None:
        self._contract = ToolContract(name=name, description="fake tool")
        self.default = default

    @property
    def contract(self) -> ToolContract:
        return self._contract

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        return ToolResult(output=str(dict(arguments)))


class FakeAnalyzer(CodeAnalyzer):
    """Minimal code analyzer."""

    def __init__(self, name: str = "fake-analyzer", *, default: bool = False) -> None:
        self._name = name
        self.default = default

    @property
    def name(self) -> str:
        return self._name

    def analyze(self, source: str, *, path: str | None = None) -> AnalysisResult:
        return AnalysisResult(findings=(source.strip(),), metadata={"path": path})


class FakeDiscoverer(Discoverer):
    """Returns a fixed list of plugins and counts discovery calls."""

    def __init__(self, plugins: Iterable[Plugin] = ()) -> None:
        self._plugins = list(plugins)
        self.calls = 0

    def discover(self) -> list[Plugin]:
        self.calls += 1
        return list(self._plugins)


class CapabilityPlugin(Plugin):
    """Contributes a fixed set of capabilities."""

    id = "capabilities"

    def __init__(
        self,
        capabilities: Iterable[Capability] = (),
        *,
        plugin_id: str = "capabilities",
    ) -> None:
        self.id = plugin_id
        self._capabilities = list(capabilities)

    def declare_capabilities(self) -> list[Capability]:
        return list(self._capabilities)


class DynamicCapabilityPlugin(Plugin):
    """Registers a capability from ``initialize`` using the context."""

    id = "dynamic"

    def __init__(self, capability: Capability) -> None:
        self._capability = capability

    def initialize(self, context: PluginContext) -> None:
        context.register_capability(self._capability)


class BadCapabilityPlugin(Plugin):
    """Violates the capability contract on purpose."""

    id = "bad-capability"

    def declare_capabilities(self) -> list[Capability]:
        return [object()]  # type: ignore[list-item]


class RecordingPlugin(Plugin):
    """Records lifecycle transitions in order."""

    id = "recording"

    def __init__(self) -> None:
        self.events: list[str] = []

    def load(self) -> None:
        self.events.append("load")

    def initialize(self, context: PluginContext) -> None:
        self.events.append("initialize")

    def shutdown(self) -> None:
        self.events.append("shutdown")


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

    def complete(self, messages: Sequence[Message], **options: Any) -> LLMResponse:
        self.calls.append(list(messages))
        if self._index < len(self._responses):
            content = self._responses[self._index]
            self._index += 1
        elif self._responses:
            content = self._responses[-1]
        else:
            content = ""
        return LLMResponse(message=Message(role="assistant", content=content))


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
