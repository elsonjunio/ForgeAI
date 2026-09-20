"""Dynamic plan execution: ``ExecutionPlan`` -> LangGraph -> runtime.

This module belongs to the LangGraph execution layer (alongside
``core.agent.runtime``) and is one of the only two modules allowed to import
LangGraph. The plan and the execution contracts never depend on LangGraph; only
this module does.

Pipeline::

    ExecutionPlan --(GraphBuilder)--> compiled LangGraph --(PlanExecutor)--> ExecutionResult

Plan nodes are resolved through the capability registry and executed via the
:class:`~core.contracts.execution.Executable` protocol, or via the ``Tool``
contract adapter. The core contains no concrete capability.

Limitations (documented, not faked): there is no persistent checkpoint. A
``PAUSE`` or ``INTERRUPT`` request stops the current run; resuming/streaming is
left for a future checkpointing mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict, cast

from langchain_core.runnables.config import RunnableConfig
from langgraph.graph import END, START, StateGraph

from core.contracts.callbacks import (
    ControlCallback,
    ExecutionEvent,
    ExecutionEventKind,
    ExecutionObserver,
)
from core.contracts.capability import Capability
from core.contracts.execution import (
    ControlAction,
    Executable,
    ExecutionContext,
    ExecutionControl,
    ExecutionResult,
    ExecutionStatus,
    NodeExecutionRequest,
    NodeResult,
)
from core.contracts.interaction import InteractionProvider
from core.contracts.plan import ExecutionPlan, PlanNode
from core.contracts.registry import CapabilitySource
from core.contracts.tool import Tool
from core.errors import (
    GraphBuildError,
    InvalidPlanError,
    MissingCapabilityError,
    UnsupportedCapabilityError,
)

_RESERVED_NODE_IDS = {"__start__", "__end__"}
_DEFAULT_RECURSION_LIMIT = 100


@dataclass
class _PlanExecution:
    """Mutable state carried through the compiled graph.

    ``ExecutionContext`` stays a pure contract; this wrapper only adds the
    per-node results needed while the graph runs. It is an internal detail of
    the engine and never exposed in public contracts.
    """

    context: ExecutionContext
    results: dict[str, NodeResult] = field(default_factory=dict)


def _merge_execution(left: _PlanExecution, right: _PlanExecution) -> _PlanExecution:
    """Reducer for concurrent updates from parallel branches.

    ``_PlanExecution`` is a single mutable object shared by every node (results
    and context are updated in place), so any of the concurrent updates refers to
    the same object; keeping ``left`` is enough and avoids LangGraph's
    "one value per step" error.
    """
    return left


class _GraphState(TypedDict):
    execution: Annotated[_PlanExecution, _merge_execution]


class _ExecutionStopped(Exception):
    """Internal signal used to stop the graph (interrupt, pause, node failure)."""

    def __init__(
        self, control: ExecutionControl, execution: _PlanExecution, *, failed: bool
    ) -> None:
        super().__init__(control.reason or control.action.value)
        self.control = control
        self.execution = execution
        self.failed = failed


class GraphBuilder:
    """Transforms an :class:`ExecutionPlan` into a compiled LangGraph graph.

    Args:
        registry: capability source used to resolve plan nodes.
        observer: optional observer for lifecycle events.
        control: optional callback invoked after each node completes; it may
            request ``CONTINUE``, ``PAUSE``, ``INTERRUPT`` or ``RETRY``.
        max_node_retries: how many times a node may be retried when a control
            callback requests ``RETRY`` (``0`` means no retry).
        recursion_limit: LangGraph recursion budget for the compiled graph.
    """

    def __init__(
        self,
        *,
        registry: CapabilitySource,
        observer: ExecutionObserver | None = None,
        control: ControlCallback | None = None,
        max_node_retries: int = 0,
        recursion_limit: int = _DEFAULT_RECURSION_LIMIT,
        interaction: InteractionProvider | None = None,
    ) -> None:
        if max_node_retries < 0:
            raise ValueError("max_node_retries must be >= 0")
        self._registry = registry
        self._observer = observer
        self._control = control
        self._max_node_retries = max_node_retries
        self._recursion_limit = recursion_limit
        self._interaction = interaction

    @property
    def recursion_limit(self) -> int:
        """LangGraph recursion budget used when invoking the compiled graph."""
        return self._recursion_limit

    def validate(self, plan: ExecutionPlan) -> None:
        """Validate the plan structure and referenced capabilities.

        Raises:
            InvalidPlanError: duplicate/reserved ids, dangling edges, self-loops
                or a node without a capability.
            MissingCapabilityError: a node references an unknown capability.
        """
        seen: set[str] = set()
        for node in plan.nodes:
            if node.id in seen:
                raise InvalidPlanError(
                    f"duplicate node id in plan {plan.id!r}: {node.id!r}"
                )
            if node.id in _RESERVED_NODE_IDS:
                raise InvalidPlanError(f"node id {node.id!r} is reserved")
            seen.add(node.id)

        node_ids = {node.id for node in plan.nodes}
        for edge in plan.edges:
            if edge.source not in node_ids:
                raise InvalidPlanError(
                    f"plan {plan.id!r} edge references unknown source node {edge.source!r}"
                )
            if edge.target not in node_ids:
                raise InvalidPlanError(
                    f"plan {plan.id!r} edge references unknown target node {edge.target!r}"
                )
            if edge.source == edge.target:
                raise InvalidPlanError(
                    f"plan {plan.id!r} has a self-loop on node {edge.source!r}"
                )

        for node in plan.nodes:
            capability = self._resolve_node(node)
            if not isinstance(capability, Executable) and not isinstance(capability, Tool):
                raise UnsupportedCapabilityError(
                    f"capability {node.capability!r} on node {node.id!r} "
                    "cannot run as a plan node"
                )

    def build(self, plan: ExecutionPlan) -> Any:
        """Validate ``plan`` and return a compiled LangGraph graph.

        Raises:
            InvalidPlanError / MissingCapabilityError: invalid plan.
            GraphBuildError: if compilation fails.
        """
        self.validate(plan)
        try:
            graph: StateGraph[_GraphState] = StateGraph(_GraphState)
            for node in plan.nodes:
                graph.add_node(node.id, cast(Any, self._node_function(node)))

            roots = [node.id for node in plan.nodes if not _has_incoming(plan, node.id)]
            leaves = [node.id for node in plan.nodes if not _has_outgoing(plan, node.id)]
            for root in roots:
                graph.add_edge(START, root)
            for edge in plan.edges:
                graph.add_edge(edge.source, edge.target)
            for leaf in leaves:
                graph.add_edge(leaf, END)
            if not plan.nodes:
                graph.add_edge(START, END)
            return graph.compile()
        except (InvalidPlanError, MissingCapabilityError, UnsupportedCapabilityError):
            raise
        except Exception as exc:
            raise GraphBuildError(
                f"failed to build graph for plan {plan.id!r}: {type(exc).__name__}: {exc}"
            ) from exc

    # -- internals -----------------------------------------------------------

    def _resolve(self, capability_id: str, node_id: str) -> Capability:
        kind, separator, name = capability_id.partition(":")
        if not separator or not name:
            raise InvalidPlanError(
                f"invalid capability id {capability_id!r} on node {node_id!r}; "
                "expected '<kind>:<name>'"
            )
        capability = self._registry.capability(kind, name)
        if capability is None:
            raise MissingCapabilityError(
                f"node {node_id!r} references capability {capability_id!r}, "
                "which is not registered"
            )
        return capability

    def _resolve_node(self, node: PlanNode) -> Capability:
        capability_id = node.capability
        if not capability_id:
            raise InvalidPlanError(f"node {node.id!r} has no capability")
        return self._resolve(capability_id, node.id)

    def _node_function(self, node: PlanNode) -> Any:
        node_id = node.id

        def run(state: _GraphState) -> dict[str, Any]:
            execution = state["execution"]
            capability = self._resolve_node(node)
            self._emit(ExecutionEventKind.NODE_START, node=node)
            attempts = 0
            while True:
                self._emit(ExecutionEventKind.CAPABILITY_START, node=node)
                result = self._invoke(capability, node, execution)
                self._emit(
                    ExecutionEventKind.CAPABILITY_COMPLETE, node=node, result=result
                )
                control = self._after_node(execution.context, result)
                if (
                    control is not None
                    and control.action is ControlAction.RETRY
                    and attempts < self._max_node_retries
                ):
                    attempts += 1
                    continue
                break

            execution.results[node_id] = result
            if result.success:
                self._emit(ExecutionEventKind.NODE_COMPLETE, node=node, result=result)
            else:
                self._emit(
                    ExecutionEventKind.ERROR,
                    node=node,
                    result=result,
                    error=result.error,
                )
                self._emit(ExecutionEventKind.NODE_COMPLETE, node=node, result=result)
                raise _ExecutionStopped(
                    ExecutionControl(
                        ControlAction.INTERRUPT,
                        reason=result.error or f"node {node_id!r} failed",
                    ),
                    execution,
                    failed=True,
                )
            if control is not None and control.action in (
                ControlAction.PAUSE,
                ControlAction.INTERRUPT,
            ):
                raise _ExecutionStopped(control, execution, failed=False)
            return {"execution": execution}

        return run

    def _invoke(
        self, capability: Capability, node: PlanNode, execution: _PlanExecution
    ) -> NodeResult:
        request = NodeExecutionRequest(
            node=node,
            context=execution.context,
            results=dict(execution.results),
            interaction=self._interaction,
        )
        try:
            if isinstance(capability, Executable):
                return capability.execute(request)
            if isinstance(capability, Tool):
                tool_result = capability.invoke(dict(node.parameters))
                error = tool_result.output if tool_result.is_error else None
                return NodeResult(
                    node_id=node.id,
                    success=not tool_result.is_error,
                    output=tool_result.output,
                    error=error,
                    metadata=dict(tool_result.metadata),
                )
            raise UnsupportedCapabilityError(
                f"capability {node.capability!r} on node {node.id!r} "
                "cannot run as a plan node"
            )
        except (InvalidPlanError, MissingCapabilityError, UnsupportedCapabilityError):
            raise
        except Exception as exc:
            return NodeResult.failed(node.id, f"{type(exc).__name__}: {exc}")

    def _after_node(
        self, context: ExecutionContext, result: NodeResult
    ) -> ExecutionControl | None:
        if self._control is None:
            return None
        return self._control.on_node_complete(context, result)

    def _emit(
        self,
        kind: ExecutionEventKind,
        *,
        node: PlanNode,
        result: NodeResult | None = None,
        error: str | None = None,
    ) -> None:
        if self._observer is None:
            return
        self._observer.on_event(
            ExecutionEvent(
                kind=kind,
                node_id=node.id,
                capability=node.capability,
                error=error,
                data={"success": result.success} if result is not None else {},
            )
        )


def _has_incoming(plan: ExecutionPlan, node_id: str) -> bool:
    return any(edge.target == node_id for edge in plan.edges)


def _has_outgoing(plan: ExecutionPlan, node_id: str) -> bool:
    return any(edge.source == node_id for edge in plan.edges)


class PlanExecutor:
    """Builds and runs the dynamic graph of a plan.

    Args:
        registry: capability source used to resolve plan nodes.
        observer: optional observer for lifecycle events.
        control: optional callback invoked after each node completes.
        max_node_retries: retries allowed per node on ``RETRY`` requests.
        recursion_limit: LangGraph recursion budget.
    """

    def __init__(
        self,
        *,
        registry: CapabilitySource,
        observer: ExecutionObserver | None = None,
        control: ControlCallback | None = None,
        max_node_retries: int = 0,
        recursion_limit: int = _DEFAULT_RECURSION_LIMIT,
        interaction: InteractionProvider | None = None,
    ) -> None:
        self._observer = observer
        self._builder = GraphBuilder(
            registry=registry,
            observer=observer,
            control=control,
            max_node_retries=max_node_retries,
            recursion_limit=recursion_limit,
            interaction=interaction,
        )

    @property
    def builder(self) -> GraphBuilder:
        """The underlying :class:`GraphBuilder`."""
        return self._builder

    def validate(self, plan: ExecutionPlan) -> None:
        """Validate ``plan`` without building the graph."""
        self._builder.validate(plan)

    def build(self, plan: ExecutionPlan) -> Any:
        """Build (and compile) the LangGraph graph for ``plan``."""
        return self._builder.build(plan)

    def run(self, plan: ExecutionPlan, context: ExecutionContext) -> ExecutionResult:
        """Execute ``plan`` and return its outcome.

        Raises:
            InvalidPlanError / MissingCapabilityError / GraphBuildError: the plan
                cannot be executed. Errors raised *by a capability* while a node
                runs are captured in the returned :class:`ExecutionResult`.
        """
        self._emit(ExecutionEventKind.EXECUTION_START, plan=plan)
        execution = _PlanExecution(context=context)
        compiled = self._builder.build(plan)
        config: RunnableConfig = {"recursion_limit": self._builder.recursion_limit}
        try:
            compiled.invoke({"execution": execution}, config=config)
        except _ExecutionStopped as stop:
            return self._finalize_stop(plan, stop)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            self._emit(ExecutionEventKind.ERROR, plan=plan, error=message)
            return ExecutionResult(
                success=False,
                status="failed",
                results=dict(execution.results),
                control=ExecutionControl(ControlAction.INTERRUPT, reason=message),
                error=message,
            )
        return self._finalize_complete(plan, execution)

    def _finalize_complete(
        self, plan: ExecutionPlan, execution: _PlanExecution
    ) -> ExecutionResult:
        results = dict(execution.results)
        success = all(result.success for result in results.values())
        self._emit(ExecutionEventKind.EXECUTION_COMPLETE, plan=plan)
        if success:
            return ExecutionResult(success=True, status="completed", results=results)
        return ExecutionResult(
            success=False,
            status="failed",
            results=results,
            error="one or more nodes failed",
        )

    def _finalize_stop(
        self, plan: ExecutionPlan, stop: _ExecutionStopped
    ) -> ExecutionResult:
        status: ExecutionStatus = "failed" if stop.failed else "stopped"
        self._emit(ExecutionEventKind.EXECUTION_COMPLETE, plan=plan)
        return ExecutionResult(
            success=False,
            status=status,
            results=dict(stop.execution.results),
            control=stop.control,
            error=stop.control.reason if stop.failed else None,
        )

    def _emit(
        self,
        kind: ExecutionEventKind,
        *,
        plan: ExecutionPlan | None = None,
        error: str | None = None,
    ) -> None:
        if self._observer is None:
            return
        self._observer.on_event(
            ExecutionEvent(
                kind=kind,
                error=error,
                data={"plan_id": plan.id} if plan is not None else {},
            )
        )
