"""The LLM planner plugin: exposes :class:`LLMPlanner` to the core."""

from __future__ import annotations

from code_agent_plugin_llm_planner.planner import DEFAULT_MAX_NODES, LLMPlanner
from core import Capability, Plugin, PluginContext
from core.contracts.registry import CapabilitySource

PLUGIN_ID = "code-agent-plugin-llm-planner"


class LLMPlannerPlugin(Plugin):
    """Contributes an :class:`LLMPlanner`.

    Settings (``CoreConfig.plugins["code-agent-plugin-llm-planner"].settings``):

    * ``provider`` (optional: name of the LLM provider; default = default one)
    * ``max_nodes`` (default ``8``)
    * ``system_prompt`` (optional override)
    """

    id = PLUGIN_ID
    version = "0.1.0"
    description = "LLM-based planner that produces an ExecutionPlan."
    author = "ForgeAI"

    def __init__(
        self,
        *,
        provider: str | None = None,
        max_nodes: int = DEFAULT_MAX_NODES,
        system_prompt: str | None = None,
    ) -> None:
        self._provider = provider
        self._max_nodes = max_nodes
        self._system_prompt = system_prompt
        self._source: CapabilitySource | None = None

    def initialize(self, context: PluginContext) -> None:
        self._source = context.capability_source
        self._provider = context.get_setting("provider", self._provider)
        self._max_nodes = int(context.get_setting("max_nodes", self._max_nodes))
        self._system_prompt = context.get_setting("system_prompt", self._system_prompt)

    def declare_capabilities(self) -> list[Capability]:
        assert self._source is not None
        return [
            LLMPlanner(
                source=self._source,
                provider_name=self._provider,
                max_nodes=self._max_nodes,
                system_prompt=self._system_prompt,
            )
        ]
