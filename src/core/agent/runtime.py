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
from core.agent.workflow import (
    ROUTE_END,
    ROUTE_EXECUTION,
    WorkflowContext,
    discovery,
    execution,
    initialize,
    planning,
    review,
    route_after_planning,
    route_after_review,
    validation,
)
from core.agent.workflow_state import WorkflowState
from core.config.schema import LangGraphOptions
from core.contracts.node import NodeContribution
from core.errors import CoreError, InvalidGraphError
from core.events.bus import EventBus
from core.events.event import Event
from core.events.types import CoreEvents, WorkflowEvents

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


class WorkflowStateDict(TypedDict):
    """Internal graph state for the code-agent workflow. Private to this module."""

    workflow_state: WorkflowState


class WorkflowRuntime:
    """Wraps the compiled code-agent workflow graph.

    This is the only place the workflow touches LangGraph. Stage logic lives in
    :mod:`core.agent.workflow` and receives services via a
    :class:`WorkflowContext`; this class only wires the stages into a
    ``StateGraph`` with conditional edges and emits lifecycle events.

    Pipeline: ``START -> initialize -> discovery -> planning -> execution ->
    validation -> review -> (conditional) -> END``.

    Args:
        context: services and options used by the stages.
    """

    def __init__(self, *, context: WorkflowContext) -> None:
        self._context = context
        self._graph: StateGraph[WorkflowStateDict] = self._build_graph()
        self._compiled: Any = self._graph.compile()

    @property
    def context(self) -> WorkflowContext:
        """The context this workflow resolves capabilities through."""
        return self._context

    def run(
        self,
        *,
        request: str | None = None,
        state: WorkflowState | None = None,
    ) -> WorkflowState:
        """Execute the workflow and return the final state.

        Args:
            request: initial user request used when ``state`` is not given.
            state: initial state; when omitted, a fresh state is created.

        Raises:
            CoreError: capability or graph errors are re-raised after a
                ``workflow.failed`` event is emitted, so callers can identify
                them (for example :class:`MissingCapabilityError`).
        """
        initial = state or WorkflowState(request=request)
        config: RunnableConfig = {
            "recursion_limit": self._context.options.recursion_limit
        }
        try:
            result = self._compiled.invoke({"workflow_state": initial}, config=config)
        except CoreError as exc:
            self._emit_failure(type(exc).__name__, str(exc))
            raise
        return self._finalize(result["workflow_state"])

    async def arun(
        self,
        *,
        request: str | None = None,
        state: WorkflowState | None = None,
    ) -> WorkflowState:
        """Async variant of :meth:`run`."""
        initial = state or WorkflowState(request=request)
        config: RunnableConfig = {
            "recursion_limit": self._context.options.recursion_limit
        }
        try:
            result = await self._compiled.ainvoke(
                {"workflow_state": initial}, config=config
            )
        except CoreError as exc:
            self._emit_failure(type(exc).__name__, str(exc))
            raise
        return self._finalize(result["workflow_state"])

    def _finalize(self, state: WorkflowState) -> WorkflowState:
        if state.status == "completed":
            self._context.emit(
                WorkflowEvents.WORKFLOW_COMPLETED,
                source="workflow",
                payload={"attempts": state.attempts},
            )
        elif state.status == "failed":
            self._context.emit(
                WorkflowEvents.WORKFLOW_FAILED,
                source="workflow",
                payload={"errors": [error.model_dump() for error in state.errors]},
            )
        return state

    def _emit_failure(self, error_type: str, message: str) -> None:
        self._context.emit(
            WorkflowEvents.WORKFLOW_FAILED,
            source="workflow",
            payload={"type": error_type, "message": message},
        )

    def _build_graph(self) -> StateGraph[WorkflowStateDict]:
        graph: StateGraph[WorkflowStateDict] = StateGraph(WorkflowStateDict)
        for name, stage in (
            ("initialize", initialize),
            ("discovery", discovery),
            ("planning", planning),
            ("execution", execution),
            ("validation", validation),
            ("review", review),
        ):
            graph.add_node(name, cast(Any, self._stage_node(name, stage)))
        graph.add_edge(START, "initialize")
        graph.add_edge("initialize", "discovery")
        graph.add_edge("discovery", "planning")
        graph.add_conditional_edges(
            "planning",
            cast(Any, self._route_after_planning),
            {ROUTE_EXECUTION: "execution", ROUTE_END: END},
        )
        graph.add_edge("execution", "validation")
        graph.add_edge("validation", "review")
        graph.add_conditional_edges(
            "review",
            cast(Any, self._route_after_review),
            {ROUTE_EXECUTION: "execution", ROUTE_END: END},
        )
        return graph

    def _stage_node(
        self,
        name: str,
        stage: Callable[[WorkflowState, WorkflowContext], WorkflowState],
    ) -> Callable[[WorkflowStateDict], dict[str, Any]]:
        def wrapped(state: WorkflowStateDict) -> dict[str, Any]:
            current = state["workflow_state"]
            self._context.emit(
                WorkflowEvents.STAGE_STARTED,
                source=name,
                payload={"status": current.status},
            )
            updated = stage(current, self._context)
            self._context.emit(
                WorkflowEvents.STAGE_FINISHED,
                source=name,
                payload={"status": updated.status},
            )
            return {"workflow_state": updated}

        return wrapped

    def _route_after_planning(self, state: WorkflowStateDict) -> str:
        return route_after_planning(state["workflow_state"])

    def _route_after_review(self, state: WorkflowStateDict) -> str:
        return route_after_review(state["workflow_state"], self._context.options)