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
    debug: bool = False


class WorkflowOptions(BaseModel):
    """Knobs for the code-agent workflow orchestration.

    Args:
        max_attempts: maximum number of ``execution`` passes (>= 1). A value of
            2 means the initial attempt plus one retry.
        recursion_limit: LangGraph recursion budget for the workflow graph.
    """

    max_attempts: int = Field(default=2, ge=1, le=100)
    recursion_limit: int = Field(default=50, ge=1, le=1_000_000)


class CoreConfig(BaseModel):
    """Top-level configuration of a core instance.

    Args:
        app_name: human-readable name of the running application.
        version: application version, defaults to the framework version.
        environment: deployment environment.
        plugins: per-plugin slots keyed by plugin id.
        langgraph: options forwarded to the execution engine.
        defaults: default provider per capability, keyed by ``kind`` (for
            example ``{"llm": "openai"}``) or by contract class name. Used by
            ``PluginRegistry.default_capability`` without coupling the core to
            any concrete provider.
        workflow: options for the code-agent workflow orchestration.
    """

    app_name: str = "core-agent"
    version: str = VERSION
    environment: Environment = "development"
    plugins: dict[str, PluginSlot] = Field(default_factory=dict)
    langgraph: LangGraphOptions = Field(default_factory=LangGraphOptions)
    defaults: dict[str, str] = Field(default_factory=dict)
    workflow: WorkflowOptions = Field(default_factory=WorkflowOptions)

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