"""Container holding the wired core services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.agent.graph import PlanExecutor
    from core.agent.runtime import AgentRuntime, WorkflowRuntime
    from core.config.schema import CoreConfig
    from core.events.bus import EventBus
    from core.plugins.registry import PluginRegistry


@dataclass
class CoreContainer:
    """Aggregates the services produced by :func:`build_core`.

    Attributes:
        config: the resolved configuration.
        events: the shared event bus.
        registry: the plugin registry.
        runtime: the compiled generic agent runtime (plugin-contributed nodes).
        workflow: the compiled code-agent workflow runtime.
        executor: the dynamic plan executor (ExecutionPlan -> LangGraph).
    """

    config: CoreConfig
    events: EventBus
    registry: PluginRegistry
    runtime: AgentRuntime
    workflow: WorkflowRuntime
    executor: PlanExecutor

    @property
    def node_ids(self) -> tuple[str, ...]:
        """Ids of the nodes wired into the agent graph, in execution order."""
        return self.runtime.node_ids

    def shutdown(self) -> None:
        """Deactivate plugins in reverse activation order."""
        self.registry.deactivate_all()