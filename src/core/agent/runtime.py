"""The agent runtime: the only component aware of LangGraph.

``AgentRuntime`` owns construction and compilation of the execution graph. The
rest of the framework — plugins, contracts, events — works with plain
:class:`AgentState` objects and never touches ``StateGraph`` directly. To
replace the execution engine later, only this module needs to change.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict, cast

from langchain_core.runnables.config import RunnableConfig
from langgraph.graph import END, START, StateGraph

from core.agent.state import AgentState, now_utc
from core.config.schema import LangGraphOptions
from core.contracts.node import NodeContribution
from core.errors import InvalidGraphError
from core.events.bus import EventBus
from core.events.event import Event
from core.events.types import CoreEvents

_INIT_NODE = "__core_init__"


class RuntimeState(TypedDict):
    """Internal graph state. Private to the runtime module."""

    agent_state: AgentState


class AgentRuntime:
    """Wraps a compiled state machine built from plugin contributions.

    Args:
        nodes: node contributions (usually collected from the registry).
        event_bus: event bus used for emitted events.
        options: execution-engine options (recursion limit, debug).
    """

    def __init__(
        self,
        *,
        nodes: list[NodeContribution] | tuple[NodeContribution, ...] = (),
        event_bus: EventBus | None = None,
        options: LangGraphOptions | None = None,
    ) -> None:
        self._events = event_bus or EventBus()
        self._options = options or LangGraphOptions()
        self._nodes = self._order_nodes(nodes)
        self._graph: StateGraph[RuntimeState] = self._build_graph()
        self._compiled: Any = self._graph.compile()

    @property
    def event_bus(self) -> EventBus:
        """The bus this runtime publishes events on."""
        return self._events

    @property
    def node_ids(self) -> tuple[str, ...]:
        """Ids of the contributed nodes, in execution order."""
        return tuple(contribution.contract.id for contribution in self._nodes)

    def run(self, *, task: str | None = None, state: AgentState | None = None) -> AgentState:
        """Execute the agent graph and return the final state.

        Args:
            task: initial task description used when ``state`` is not given.
            state: initial state; when omitted, a fresh state is created.

        Returns:
            The completed final state.
        """
        initial = state or AgentState(task=task)
        config: RunnableConfig = {"recursion_limit": self._options.recursion_limit}
        result = self._compiled.invoke(
            {"agent_state": initial},
            config=config,
        )
        return self._finalize(result["agent_state"])

    async def arun(self, *, task: str | None = None, state: AgentState | None = None) -> AgentState:
        """Async variant of :meth:`run`."""
        initial = state or AgentState(task=task)
        config: RunnableConfig = {"recursion_limit": self._options.recursion_limit}
        result = await self._compiled.ainvoke(
            {"agent_state": initial},
            config=config,
        )
        return self._finalize(result["agent_state"])

    def _finalize(self, state: AgentState) -> AgentState:
        """Mark the run as completed and publish the finish event."""
        final = state.model_copy(update={"status": "completed", "updated_at": now_utc()})
        self._events.publish(Event[object](
            type=CoreEvents.AGENT_FINISHED,
            source="core",
            payload={"state_id": id(final)},
        ))
        return final

    def _build_graph(self) -> StateGraph[RuntimeState]:
        """Assemble the LangGraph state machine from the contributed nodes.

        Structure: START -> initialize -> node_1 -> ... -> node_n -> END.
        With zero contributions the graph runs initialization only.
        """
        graph: StateGraph[RuntimeState] = StateGraph(RuntimeState)
        graph.add_node(_INIT_NODE, cast(Any, self._initialize))
        for contribution in self._nodes:
            node_id = contribution.contract.id
            if node_id == _INIT_NODE:
                raise InvalidGraphError(f"node id {node_id!r} is reserved")
            graph.add_node(node_id, cast(Any, self._compiled_node(contribution)))

        previous = _INIT_NODE
        graph.add_edge(START, previous)
        for contribution in self._nodes:
            graph.add_edge(previous, contribution.contract.id)
            previous = contribution.contract.id
        graph.add_edge(previous, END)
        return graph

    def _compiled_node(
        self,
        contribution: NodeContribution,
    ) -> Callable[[RuntimeState], dict[str, Any]]:
        """Adapt an AgentState transformation to a graph node function.

        The contributed callable only ever sees and returns :class:`AgentState`;
        the graph plumbing (reading/writing the internal state dict) stays here.
        """

        node_id = contribution.contract.id

        def wrapped(state: RuntimeState) -> dict[str, Any]:
            current = state["agent_state"]
            self._events.publish(Event[object](
                type=CoreEvents.NODE_STARTED,
                source=node_id,
                payload={"state_id": id(current)},
            ))
            updated = contribution.node(current) or current
            self._events.publish(Event[object](
                type=CoreEvents.NODE_FINISHED,
                source=node_id,
                payload={"state_id": id(updated)},
            ))
            return {"agent_state": updated}

        return wrapped

    def _initialize(self, state: RuntimeState) -> dict[str, Any]:
        """First node: promote the state to ``running`` and announce the run."""
        current = state["agent_state"]
        if current.status == "idle":
            current = current.model_copy(update={"status": "running"})
        self._events.publish(Event[object](
            type=CoreEvents.AGENT_STARTED,
            source="core",
            payload={"task": current.task},
        ))
        return {"agent_state": current}

    @staticmethod
    def _order_nodes(
        nodes: list[NodeContribution] | tuple[NodeContribution, ...],
    ) -> list[NodeContribution]:
        """Order nodes respecting ``after`` hints (stable topological sort).

        Raises:
            InvalidGraphError: on duplicate ids or unresolvable ordering.
        """
        seen: set[str] = set()
        for contribution in nodes:
            node_id = contribution.contract.id
            if node_id in seen:
                raise InvalidGraphError(f"duplicate node id: {node_id!r}")
            seen.add(node_id)

        ordered: list[NodeContribution] = []
        placed_ids: set[str] = set()
        remaining = list(nodes)

        while remaining:
            progressed = False
            for contribution in list(remaining):
                after = contribution.contract.after
                if after is None or after in placed_ids:
                    ordered.append(contribution)
                    placed_ids.add(contribution.contract.id)
                    remaining.remove(contribution)
                    progressed = True
            if not progressed:
                stuck = ", ".join(c.contract.id for c in remaining)
                raise InvalidGraphError(
                    f"cannot order nodes: unsatisfied 'after' dependencies or cycle: {stuck}"
                )
        return ordered