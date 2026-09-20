"""A fake *external* plugin, built using only the public ``core`` API.

It lives outside ``src/core`` on purpose: it proves that a third-party package
can add capabilities (LLM provider, tool, validator) and be loaded through the
entry-point discovery mechanism **without modifying the core**.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core import (
    Capability,
    LLMProvider,
    Message,
    Plugin,
    Tool,
    ToolContract,
    ToolResult,
    ValidationInput,
    ValidationResult,
    Validator,
)

PLUGIN_ID = "code-agent-plugin-fake"


class FakeLLMProvider(LLMProvider):
    """Deterministic provider that answers the workflow's three prompt shapes."""

    default = True

    @property
    def name(self) -> str:
        return "integration-llm"

    def complete(self, messages: Sequence[Message], **options: Any) -> Message:
        prompt = messages[-1].content if messages else ""
        if "one task per line" in prompt:
            return Message(role="assistant", content="- first task\n- second task")
        if 'Reply "APPROVED"' in prompt:
            return Message(role="assistant", content="APPROVED")
        return Message(role="assistant", content="done")


class FakeTool(Tool):
    """A no-op tool, enough to appear in the execution prompt."""

    @property
    def contract(self) -> ToolContract:
        return ToolContract(name="noop", description="does nothing")

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        return ToolResult(output="ok")


class FakeValidator(Validator):
    """Always passes."""

    @property
    def name(self) -> str:
        return "always-pass"

    def validate(self, data: ValidationInput) -> ValidationResult:
        return ValidationResult(passed=True, messages=("ok",))


class ExternalFakePlugin(Plugin):
    """Contributes one provider of each capability the workflow consumes."""

    id = PLUGIN_ID
    version = "0.1.0"
    description = "Fake external plugin used by the integration tests."
    author = "test-suite"

    def declare_capabilities(self) -> list[Capability]:
        return [FakeLLMProvider(), FakeTool(), FakeValidator()]


# A convenience used by the fake entry point in the integration test.
def build() -> Plugin:
    """Zero-argument factory, the shape an entry point may resolve to."""
    return ExternalFakePlugin()
