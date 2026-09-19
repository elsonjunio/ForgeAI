from __future__ import annotations

import asyncio
from collections.abc import Iterable

import pytest

from core.agent.workflow_state import WorkflowState
from core.config.schema import CoreConfig
from core.contracts.capability import Capability
from core.errors import MissingCapabilityError
from core.events.types import WorkflowEvents
from core.runtime.bootstrap import build_core
from core.runtime.container import CoreContainer
from tests.support.capabilities import CapabilityPlugin, FakeDiscoverer, FakeTool
from tests.support.plugins import NoopPlugin
from tests.support.workflow import (
    AlwaysFailValidator,
    AlwaysPassValidator,
    FailOnceValidator,
    RaisingValidator,
    ScriptedLLMProvider,
)


def make_container(
    capabilities: Iterable[Capability],
    *,
    config: CoreConfig | None = None,
) -> CoreContainer:
    plugin = CapabilityPlugin(capabilities, plugin_id="workflow-caps")
    return build_core(config=config, plugins=[plugin], discoverers=[])


def collect_events(core: CoreContainer, event_type: str) -> list[str]:
    seen: list[str] = []
    core.events.subscribe(event_type, lambda event: seen.append(event.type))
    return seen


# --- initialization ---------------------------------------------------------


def test_build_core_exposes_workflow_without_plugins() -> None:
    core = build_core(discoverers=[])
    assert core.workflow.context.registry is core.registry
    assert core.workflow.context.options.max_attempts >= 1
    core.shutdown()


def test_workflow_requires_llm_with_clear_error() -> None:
    core = build_core(discoverers=[])
    started = collect_events(core, WorkflowEvents.WORKFLOW_STARTED)
    failures = collect_events(core, WorkflowEvents.WORKFLOW_FAILED)

    with pytest.raises(MissingCapabilityError) as excinfo:
        core.workflow.run(request="do something")

    assert "llm" in str(excinfo.value).lower()
    assert started == [WorkflowEvents.WORKFLOW_STARTED]
    assert failures == [WorkflowEvents.WORKFLOW_FAILED]
    core.shutdown()


def test_workflow_runs_without_tools_or_discoverers() -> None:
    llm = ScriptedLLMProvider(["task", "out", "APPROVED"])
    core = make_container([llm])

    state = core.workflow.run(request="x")
    core.shutdown()

    assert state.status == "completed"
    assert state.context.capabilities["llm"] == ["scripted"]
    assert "tool" not in state.context.capabilities
    assert "discoverer" not in state.context.capabilities


# --- success flow -----------------------------------------------------------


def test_success_flow_tracks_state() -> None:
    llm = ScriptedLLMProvider(
        ["write code\nrun tests", "code done", "tests done", "APPROVED"]
    )
    core = make_container([llm])

    state = core.workflow.run(request="fix the bug")
    core.shutdown()

    assert state.status == "completed"
    assert state.request == "fix the bug"
    assert state.plan is not None
    assert [task.id for task in state.completed_tasks] == ["task-1", "task-2"]
    assert state.current_task is not None
    assert state.current_task.output == "tests done"
    assert state.review is not None
    assert state.review.approved is True
    assert state.errors == []
    assert state.attempts == 1
    assert state.validations == []


def test_arun_matches_run_semantics() -> None:
    llm = ScriptedLLMProvider(["task", "out", "APPROVED"])
    core = make_container([llm])

    async def execute() -> WorkflowState:
        return await core.workflow.arun(request="x")

    state = asyncio.run(execute())
    core.shutdown()

    assert state.status == "completed"
    assert state.review is not None


# --- discovery / execution / validation capabilities ------------------------


def test_discovery_uses_registered_discoverer() -> None:
    discoverer = FakeDiscoverer([NoopPlugin()])
    llm = ScriptedLLMProvider(["a", "b", "APPROVED"])
    core = make_container([llm, discoverer])

    state = core.workflow.run(request="x")
    core.shutdown()

    assert [plugin.id for plugin in state.context.plugins] == ["noop"]
    assert state.context.capabilities["llm"] == ["scripted"]
    assert "discoverer" in state.context.capabilities


def test_execution_consults_available_tools() -> None:
    tool = FakeTool("echo")
    llm = ScriptedLLMProvider(["task", "out", "APPROVED"])
    core = make_container([llm, tool])

    state = core.workflow.run(request="x")
    core.shutdown()

    assert state.status == "completed"
    assert any(
        "echo" in message.content for call in llm.calls for message in call
    )


def test_validators_are_executed() -> None:
    validator = AlwaysPassValidator()
    llm = ScriptedLLMProvider(["task", "out", "APPROVED"])
    core = make_container([llm, validator])

    state = core.workflow.run(request="x")
    core.shutdown()

    assert [record.validator for record in state.validations] == ["pass"]
    assert validator.inputs
    assert validator.inputs[0].output == "out"


# --- error flow and retry ---------------------------------------------------


def test_error_flow_when_validation_fails_without_retry() -> None:
    config = CoreConfig.model_validate({"workflow": {"max_attempts": 1}})
    llm = ScriptedLLMProvider(["task", "out", "APPROVED"])
    core = make_container([llm, AlwaysFailValidator()], config=config)

    state = core.workflow.run(request="x")
    core.shutdown()

    assert state.status == "failed"
    assert state.attempts == 1
    assert state.validations[0].passed is False


def test_retry_after_validation_failure_then_success() -> None:
    config = CoreConfig.model_validate({"workflow": {"max_attempts": 2}})
    llm = ScriptedLLMProvider(["task", "out", "APPROVED", "out2", "APPROVED"])
    core = make_container([llm, FailOnceValidator()], config=config)
    retries = collect_events(core, WorkflowEvents.WORKFLOW_RETRY)

    state = core.workflow.run(request="x")
    core.shutdown()

    assert state.status == "completed"
    assert state.attempts == 2
    assert state.validations[0].passed is True
    assert retries == [WorkflowEvents.WORKFLOW_RETRY]


def test_unexpected_error_emits_failed_event() -> None:
    llm = ScriptedLLMProvider(["task", "out", "APPROVED"])
    core = make_container([llm, RaisingValidator()])
    failures = collect_events(core, WorkflowEvents.WORKFLOW_FAILED)

    with pytest.raises(RuntimeError):
        core.workflow.run(request="x")

    assert failures == [WorkflowEvents.WORKFLOW_FAILED]
    core.shutdown()


def test_retry_after_review_rejection() -> None:
    config = CoreConfig.model_validate({"workflow": {"max_attempts": 2}})
    llm = ScriptedLLMProvider(
        ["task", "out", "REJECT needs work", "out2", "APPROVED"]
    )
    core = make_container([llm], config=config)

    state = core.workflow.run(request="x")
    core.shutdown()

    assert state.status == "completed"
    assert state.attempts == 2
    assert state.review is not None
    assert state.review.approved is True


# --- events -----------------------------------------------------------------


def test_workflow_emits_events() -> None:
    llm = ScriptedLLMProvider(["task", "out", "APPROVED"])
    core = make_container([llm])
    started = collect_events(core, WorkflowEvents.WORKFLOW_STARTED)
    stage_started = collect_events(core, WorkflowEvents.STAGE_STARTED)
    stage_finished = collect_events(core, WorkflowEvents.STAGE_FINISHED)
    completed = collect_events(core, WorkflowEvents.WORKFLOW_COMPLETED)

    core.workflow.run(request="x")
    core.shutdown()

    assert started == [WorkflowEvents.WORKFLOW_STARTED]
    assert len(stage_started) == 6
    assert len(stage_finished) == 6
    assert stage_started[0] == WorkflowEvents.STAGE_STARTED
    assert completed == [WorkflowEvents.WORKFLOW_COMPLETED]
