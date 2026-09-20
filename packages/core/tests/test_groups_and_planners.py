from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

import pytest

from core import (
    Capability,
    ComplexityAssessment,
    ComplexityEvaluator,
    ComplexityLevel,
    CoreConfig,
    DuplicateGroupError,
    EventBus,
    ExecutionContext,
    ExecutionPlan,
    Group,
    InteractionProvider,
    InteractionRequest,
    InteractionResponse,
    NodeExecutionRequest,
    NodeResult,
    PlanExecutor,
    Planner,
    PlanningRequest,
    PlanningResult,
    PlanNode,
    Plugin,
    build_core,
)
from core.plugins.registry import PluginRegistry

# --- fake capabilities / planners / plugins (test-only) ---------------------


def make_step(name: str, groups: tuple[str, ...] = ()) -> Capability:
    """Build an executable capability in the given groups."""
    group_ids = tuple(groups)

    class _Step(Capability):
        kind = "step"
        groups: ClassVar[tuple[str, ...]] = group_ids

        @property
        def name(self) -> str:
            return name

        def execute(self, request: NodeExecutionRequest) -> NodeResult:
            return NodeResult.ok(request.node.id, output=name)

    return _Step()


def make_planner(
    name: str,
    groups: tuple[str, ...] = (),
    *,
    node_capability: str = "step:code-step",
) -> Planner:
    """Build a planner that emits a single-node plan."""
    group_ids = tuple(groups)

    class _Planner(Planner):
        groups: ClassVar[tuple[str, ...]] = group_ids

        @property
        def name(self) -> str:
            return name

        def plan(self, request: PlanningRequest) -> PlanningResult:
            node = PlanNode(id="n", capability=node_capability)
            return PlanningResult(
                plan=ExecutionPlan(id=f"plan-{name}", nodes=(node,)),
                rationale=name,
            )

    return _Planner()


class _GlobalPlanner(Planner):
    """Global planner that delegates to a specialized (group) planner."""

    def __init__(self, specialists: Iterable[Planner]) -> None:
        self._specialists = list(specialists)

    @property
    def name(self) -> str:
        return "global-planner"

    def plan(self, request: PlanningRequest) -> PlanningResult:
        available = sorted(descriptor.id for descriptor in request.planners)
        chosen = next(p for p in self._specialists if "code" in p.groups)
        result = chosen.plan(request)
        return PlanningResult(
            plan=result.plan,
            rationale=f"delegated to {chosen.name}; available={available}",
        )


class _GroupedPlugin(Plugin):
    def __init__(
        self,
        plugin_id: str,
        *,
        capabilities: Iterable[Capability] = (),
        groups: tuple[str, ...] = (),
        group_defs: Iterable[Group] = (),
    ) -> None:
        self.id = plugin_id
        self.groups = tuple(groups)
        self._capabilities = list(capabilities)
        self._group_defs = list(group_defs)

    def declare_groups(self) -> list[Group]:
        return list(self._group_defs)

    def declare_capabilities(self) -> list[Capability]:
        return list(self._capabilities)


class _FakeEvaluator(ComplexityEvaluator):
    @property
    def name(self) -> str:
        return "simple-eval"

    def evaluate(self, request: PlanningRequest) -> ComplexityAssessment:
        return ComplexityAssessment(
            level=ComplexityLevel.SIMPLE, rationale="tiny request"
        )


class _FakeInteraction:
    def __init__(self) -> None:
        self.requests: list[InteractionRequest] = []

    def request(self, request: InteractionRequest) -> InteractionResponse:
        self.requests.append(request)
        return InteractionResponse(approved=True)


class _CapturingStep(Capability):
    kind = "step"

    def __init__(self) -> None:
        self.seen: InteractionProvider | None = None

    @property
    def name(self) -> str:
        return "capture"

    def execute(self, request: NodeExecutionRequest) -> NodeResult:
        self.seen = request.interaction
        return NodeResult.ok(request.node.id)


def _registry(*plugins: Plugin) -> PluginRegistry:
    registry = PluginRegistry(config=CoreConfig(), events=EventBus())
    registry.extend(plugins)
    registry.activate_all()
    return registry


# --- A. a plugin belongs to one group ---------------------------------------


def test_plugin_in_one_group() -> None:
    plugin = _GroupedPlugin(
        "git", capabilities=[make_step("commit", groups=("version-control",))]
    )
    registry = _registry(plugin)

    assert registry.plugin_groups("git") == ["version-control"]
    assert registry.plugin_ids_in_group("version-control") == ["git"]
    assert [cap.name for cap in registry.capabilities_in_group("version-control")] == [
        "commit"
    ]


# --- B. a plugin belongs to multiple groups ---------------------------------


def test_plugin_in_multiple_groups() -> None:
    plugin = _GroupedPlugin(
        "git",
        groups=("project",),
        capabilities=[
            make_step("commit", groups=("code", "version-control")),
            make_step("status", groups=("project",)),
        ],
    )
    registry = _registry(plugin)

    assert registry.plugin_groups("git") == ["code", "project", "version-control"]
    assert registry.plugin_ids_in_group("code") == ["git"]
    assert registry.plugin_ids_in_group("version-control") == ["git"]
    assert registry.plugin_ids_in_group("project") == ["git"]
    assert {cap.name for cap in registry.capabilities_in_group("project")} == {
        "status"
    }


# --- C. two group planners --------------------------------------------------


def test_two_group_planners() -> None:
    registry = _registry(
        _GroupedPlugin(
            "planners",
            capabilities=[
                make_planner("code-planner", groups=("code",)),
                make_planner("fs-planner", groups=("filesystem",)),
            ],
        )
    )

    assert [p.name for p in registry.planners(group="code")] == ["code-planner"]
    assert [p.name for p in registry.planners(group="filesystem")] == ["fs-planner"]
    assert {p.name for p in registry.planners()} == {"code-planner", "fs-planner"}
    assert [d.id for d in registry.planner_descriptors(group="code")] == [
        "planner:code-planner"
    ]


# --- D. a global planner receives the specialized planners ------------------


def test_global_planner_receives_specialists() -> None:
    code = make_planner("code-planner", groups=("code",))
    filesystem = make_planner("fs-planner", groups=("filesystem",))
    registry = _registry(_GroupedPlugin("planners", capabilities=[code, filesystem]))

    global_planner = _GlobalPlanner([code, filesystem])
    request = PlanningRequest(
        request="do it",
        context=ExecutionContext(request="do it"),
        planners=tuple(registry.planner_descriptors()),
    )

    result = global_planner.plan(request)

    assert result.plan.id == "plan-code-planner"
    assert "code-planner" in result.rationale
    assert "planner:fs-planner" in result.rationale


# --- E. a planner produces an ExecutionPlan without knowing LangGraph -------


def test_planner_produces_plan_without_langgraph() -> None:
    import inspect

    from core.contracts import planning as planning_module

    assert "langgraph" not in inspect.getsource(planning_module)

    planner = make_planner("code-planner", groups=("code",))
    result = planner.plan(
        PlanningRequest(request="x", context=ExecutionContext(request="x"))
    )
    assert isinstance(result.plan, ExecutionPlan)


# --- F. the core turns the plan into LangGraph ------------------------------


def test_core_transforms_plan_into_langgraph() -> None:
    step = make_step("code-step", groups=("code",))
    registry = _registry(_GroupedPlugin("code", capabilities=[step]))
    planner = make_planner("code-planner", groups=("code",))

    request = PlanningRequest(request="do it", context=ExecutionContext(request="do it"))
    plan = planner.plan(request).plan

    executor = PlanExecutor(registry=registry)
    result = executor.run(plan, ExecutionContext(request="do it"))

    assert result.status == "completed"


# --- G. a capability is resolved by the registry during execution -----------


def test_capability_resolved_by_registry_during_execution() -> None:
    step = make_step("code-step", groups=("code",))
    registry = _registry(_GroupedPlugin("code", capabilities=[step]))
    assert registry.capability("step", "code-step") is step

    executor = PlanExecutor(registry=registry)
    plan = ExecutionPlan(
        id="p", nodes=(PlanNode(id="n", capability="step:code-step"),)
    )
    result = executor.run(plan, ExecutionContext(request="x"))

    assert result.status == "completed"
    assert result.results["n"].output == "code-step"


# --- H. no plugins installed, core still initializes ------------------------


def test_core_initializes_without_plugins() -> None:
    core = build_core(discoverers=[])
    try:
        assert core.registry.groups() == []
        assert core.registry.planners() == []
        assert core.registry.planner_descriptors() == []
        assert core.registry.capability_descriptors() == []
    finally:
        core.shutdown()


# --- groups: declarations and conflicts -------------------------------------


def test_group_declaration_is_queryable() -> None:
    registry = _registry(
        _GroupedPlugin(
            "git",
            capabilities=[make_step("commit", groups=("version-control",))],
            group_defs=[Group(id="version-control", name="Version Control")],
        )
    )

    assert registry.group_ids() == ["version-control"]
    group = registry.group("version-control")
    assert group is not None
    assert group.name == "Version Control"
    assert [g.id for g in registry.groups()] == ["version-control"]


def test_duplicate_group_declaration_raises() -> None:
    registry = PluginRegistry(config=CoreConfig(), events=EventBus())
    registry.extend(
        [
            _GroupedPlugin("a", group_defs=[Group(id="code")]),
            _GroupedPlugin("b", group_defs=[Group(id="code")]),
        ]
    )
    with pytest.raises(DuplicateGroupError):
        registry.activate_all()


# --- complexity evaluator ---------------------------------------------------


def test_complexity_evaluator_is_a_capability() -> None:
    registry = _registry(_GroupedPlugin("complexity", capabilities=[_FakeEvaluator()]))

    evaluator = registry.default_capability(ComplexityEvaluator)
    assert evaluator is not None
    assert isinstance(evaluator, ComplexityEvaluator)

    request = PlanningRequest(request="x", context=ExecutionContext(request="x"))
    assessment = evaluator.evaluate(request)
    assert assessment.level is ComplexityLevel.SIMPLE


# --- interaction ------------------------------------------------------------


def test_interaction_reaches_plugin_context() -> None:
    interaction = _FakeInteraction()
    core = build_core(
        plugins=[_GroupedPlugin("p")], discoverers=[], interaction=interaction
    )
    try:
        context = core.registry.context("p")
        assert context is not None
        assert context.interaction is interaction
    finally:
        core.shutdown()


def test_interaction_reaches_node_execution() -> None:
    interaction = _FakeInteraction()
    step = _CapturingStep()
    core = build_core(
        plugins=[_GroupedPlugin("p", capabilities=[step])],
        discoverers=[],
        interaction=interaction,
    )
    try:
        plan = ExecutionPlan(id="p", nodes=(PlanNode(id="n", capability="step:capture"),))
        result = core.executor.run(plan, ExecutionContext(request="x"))
    finally:
        core.shutdown()

    assert result.status == "completed"
    assert step.seen is interaction


def test_interaction_request_and_response_shapes() -> None:
    interaction = _FakeInteraction()
    response = interaction.request(
        InteractionRequest(kind="confirm", message="Run it?", default="n")
    )
    assert response.approved is True
    assert interaction.requests[0].message == "Run it?"


# --- types sanity -----------------------------------------------------------


def test_planner_descriptors_carry_groups() -> None:
    registry = _registry(
        _GroupedPlugin("planners", capabilities=[make_planner("code", groups=("code",))])
    )
    descriptor = registry.planner_descriptors()[0]
    assert descriptor.kind == "planner"
    assert descriptor.groups == ("code",)
    assert isinstance(descriptor.id, str) and descriptor.id
