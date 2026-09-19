"""Stub plugins used by the test-suite (never shipped by the core)."""

from __future__ import annotations

from core.agent.state import AgentState
from core.contracts.node import NodeContract, NodeContribution
from core.contracts.tool import ToolContract
from core.events.event import Event
from core.events.types import EventHandler
from core.plugins.base import Plugin
from core.plugins.context import PluginContext


class NoopPlugin(Plugin):
    """Empty plugin: proves that a plugin with no contributions is fine."""

    id = "noop"
    version = "0.1.0"


class LifecyclePlugin(Plugin):
    """Records lifecycle calls and subscribes a handler."""

    id = "lifecycle"
    version = "1.0.0"

    def __init__(self) -> None:
        self.activated = 0
        self.deactivated = 0
        self.handled: list[Event[object]] = []

    def activate(self, context: PluginContext) -> None:
        self.activated += 1
        context.publish(Event[object](
            type="test.plugin.activated",
            source=self.id,
            payload={"version": self.version},
        ))

    def deactivate(self) -> None:
        self.deactivated += 1

    def event_handlers(self) -> dict[str, EventHandler]:
        return {"test.ping": self._on_ping}

    def _on_ping(self, event: Event[object]) -> None:
        self.handled.append(event)


class EchoNodePlugin(Plugin):
    """Contributes a node that mirrors the task into the output."""

    id = "echo"
    version = "0.1.0"

    def declare_nodes(self) -> list[NodeContribution]:
        def node(state: AgentState) -> AgentState:
            return state.model_copy(update={"output": state.task})

        return [
            NodeContribution(
                contract=NodeContract(id="echo", description="mirror the task into output"),
                node=node,
            )
        ]


class GreetToolPlugin(Plugin):
    """Contributes a declarative tool contract only."""

    id = "greet"
    version = "0.2.0"

    def __init__(self) -> None:
        self.tool = ToolContract(
            name="greet",
            description="Say hello to someone.",
            parameters={"type": "object", "properties": {"who": {"type": "string"}}},
        )

    def declare_tools(self) -> list[ToolContract]:
        return [self.tool]

    def create_node(self) -> NodeContribution:
        def node(state: AgentState) -> AgentState:
            return state.model_copy(update={"output": f"hello {state.task}"})

        return NodeContribution(contract=NodeContract(id="greet"), node=node)


def make_ordered_node_plugin(
    plugin_id: str,
    step: object,
    after: str | None = None,
) -> type[Plugin]:
    """Build a plugin that appends ``step`` to metadata['trace']."""

    class OrderedNodePlugin(Plugin):
        id = plugin_id
        version = "0.1.0"

        def declare_nodes(self) -> list[NodeContribution]:
            def node(state: AgentState) -> AgentState:
                trace = state.metadata.setdefault("trace", [])
                trace.append(step)
                return state.model_copy(update={"metadata": state.metadata})

            return [
                NodeContribution(
                    contract=NodeContract(id=plugin_id, after=after, description=f"step {step}"),
                    node=node,
                )
            ]

    return OrderedNodePlugin