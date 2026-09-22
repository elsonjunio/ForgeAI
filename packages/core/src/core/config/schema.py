"""Configuration models for the core framework."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from core.version import VERSION

Environment = Literal["development", "test", "production"]


class PluginSlot(BaseModel):
    """Per-plugin configuration slice exposed to the plugin at run time.

    Args:
        enabled: whether the plugin should be loaded.
        settings: free-form settings the plugin can consume via its context.
    """

    enabled: bool = True
    settings: dict[str, Any] = Field(default_factory=dict)


class LangGraphOptions(BaseModel):
    """Knobs forwarded to the underlying execution engine (LangGraph).

    These options are consumed only inside ``AgentRuntime``; they are part of
    the public config surface but intentionally generic.
    """

    recursion_limit: int = Field(default=25, ge=1, le=1_000_000)


class ExecutionBudgets(BaseModel):
    """Advisory limits for a host-driven plan/execute/replan run.

    The core never reads these values; a host (for example the CLI) applies
    them to bound a long-running request. ``deadline_seconds`` and
    ``max_total_tokens`` are cooperative: they are checked between iterations.

    Args:
        max_iterations: planning iterations for one request.
        max_recoveries: replans allowed after a recoverable failure.
        max_nodes: maximum nodes per plan (planner override), when set.
        deadline_seconds: wall-clock budget for the whole run, when set.
        max_total_tokens: token budget for the whole run, when set.
        compaction_chars: auto-compact the gathered output above this size.
        compaction_keep_last: observations kept verbatim when auto-compacting.
        history_limit: most recent conversation messages injected as history.
    """

    max_iterations: int = Field(default=5, ge=1)
    max_recoveries: int = Field(default=3, ge=0)
    max_nodes: int | None = Field(default=None, ge=1)
    deadline_seconds: float | None = Field(default=None, gt=0)
    max_total_tokens: int | None = Field(default=None, ge=1)
    compaction_chars: int = Field(default=8000, ge=0)
    compaction_keep_last: int = Field(default=2, ge=0)
    history_limit: int = Field(default=20, ge=0)


class CoreConfig(BaseModel):
    """Top-level configuration of a core instance.

    Args:
        app_name: human-readable name of the running application.
        version: application version, defaults to the framework version.
        environment: deployment environment.
        plugins: per-plugin slots keyed by plugin id.
        langgraph: options forwarded to the execution engine.
        budgets: advisory limits a host applies to a long-running request.
        defaults: default provider per capability, keyed by ``kind`` (for
            example ``{"llm": "openai"}``) or by contract class name. Used by
            ``PluginRegistry.default_capability`` without coupling the core to
            any concrete provider.
    """

    app_name: str = "core-agent"
    version: str = VERSION
    environment: Environment = "development"
    plugins: dict[str, PluginSlot] = Field(default_factory=dict)
    langgraph: LangGraphOptions = Field(default_factory=LangGraphOptions)
    budgets: ExecutionBudgets = Field(default_factory=ExecutionBudgets)
    defaults: dict[str, str] = Field(default_factory=dict)

    def slot(self, plugin_id: str) -> PluginSlot:
        """Return the slot for ``plugin_id``, defaulting to an enabled empty one."""
        return self.plugins.get(plugin_id) or PluginSlot()

    def is_enabled(self, plugin_id: str, *, default_enabled: bool = True) -> bool:
        """Whether ``plugin_id`` should be loaded.

        Plugins absent from the ``plugins`` dict are enabled by default, which
        keeps the zero-configuration / zero-plugin scenario trivially working.
        """
        slot = self.plugins.get(plugin_id)
        return slot.enabled if slot is not None else default_enabled