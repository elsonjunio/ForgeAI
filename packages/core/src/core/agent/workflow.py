"""Code-agent workflow: typed stages orchestrated by the runtime.

This module contains no LangGraph import and no concrete plugin. Stages only use
the capability contracts and the :class:`PluginRegistry` through a
:class:`WorkflowContext`, so the workflow stays independent of any provider.

Pipeline::

    START -> initialize -> discovery -> planning -> execution -> validation
          -> review -> (conditional) -> END

``review`` is the decision point: an approved run with passing validations ends;
otherwise the workflow retries ``execution`` while attempts remain, or ends as
failed.
"""

from __future__ import annotations

import re
from typing import Any, cast

from core.agent.state import Message
from core.agent.workflow_state import (
    DiscoveredContext,
    Plan,
    ReviewResult,
    Task,
    ValidationRecord,
    WorkflowError,
    WorkflowState,
)
from core.config.schema import WorkflowOptions
from core.contracts.discovery import Discoverer
from core.contracts.llm import LLMProvider
from core.contracts.registry import CapabilitySource
from core.contracts.tool import Tool
from core.contracts.validator import ValidationInput, Validator
from core.errors import CoreError, MissingCapabilityError
from core.events.bus import EventBus
from core.events.event import Event
from core.events.types import WorkflowEvents

# Stage identifiers, also used as event sources.
STAGE_INITIALIZE = "initialize"
STAGE_DISCOVERY = "discovery"
STAGE_PLANNING = "planning"
STAGE_EXECUTION = "execution"
STAGE_VALIDATION = "validation"
STAGE_REVIEW = "review"

# Routing keys resolved by the runtime's conditional edges.
ROUTE_EXECUTION = "execution"
ROUTE_END = "end"

# Strips a leading bullet or ordinal ("- ", "* ", "1. ", "2) ") from a plan line.
_TASK_PREFIX = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s*")


class WorkflowContext:
    """Services available to workflow stages.

    Stages use this instead of importing concrete plugins: LLM providers, tools,
    validators and discoverers are all resolved from a
    :class:`~core.contracts.registry.CapabilitySource` at call time.

    Args:
        registry: the capability source holding the providers.
        events: the bus the workflow publishes its events on.
        options: workflow knobs; defaults are used when omitted.
    """

    def __init__(
        self,
        *,
        registry: CapabilitySource,
        events: EventBus,
        options: WorkflowOptions | None = None,
    ) -> None:
        self._registry = registry
        self._events = events
        self._options = options or WorkflowOptions()

    @property
    def registry(self) -> CapabilitySource:
        """The capability source stages resolve providers from."""
        return self._registry

    @property
    def events(self) -> EventBus:
        return self._events

    @property
    def options(self) -> WorkflowOptions:
        return self._options

    def capability_inventory(self) -> dict[str, list[str]]:
        """Map each registered capability ``kind`` to its provider names."""
        return {
            kind: self._registry.capability_names(kind)
            for kind in self._registry.capability_kinds()
        }

    def llm(self) -> LLMProvider:
        """Return the default LLM provider.

        Raises:
            MissingCapabilityError: when no ``LLMProvider`` is registered, with
                a message identifying the missing capability.
        """
        provider = self._registry.default_capability(LLMProvider)
        if provider is None:
            raise MissingCapabilityError(
                "no LLM provider is registered (capability kind 'llm'); "
                "install a plugin that provides an LLMProvider"
            )
        if not isinstance(provider, LLMProvider):
            raise MissingCapabilityError(
                f"capability {provider.name!r} of kind 'llm' is not an LLMProvider"
            )
        return provider

    def tools(self) -> list[Tool]:
        """Available executable tools, in registration order."""
        return cast("list[Tool]", self._registry.capabilities(Tool))

    def validators(self) -> list[Validator]:
        """Available validators, in registration order."""
        return cast("list[Validator]", self._registry.capabilities(Validator))

    def discoverers(self) -> list[Discoverer]:
        """Available discoverers, in registration order."""
        return cast("list[Discoverer]", self._registry.capabilities(Discoverer))

    def emit(
        self,
        event_type: str,
        *,
        source: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Publish a workflow event."""
        self._events.publish(Event[object](type=event_type, source=source, payload=payload))


def _updated(state: WorkflowState, **changes: Any) -> WorkflowState:
    """Return a copy of ``state`` with ``changes`` applied and timestamped."""
    updated = state.model_copy(update=changes)
    updated.touch()
    return updated


def _format_capabilities(context: DiscoveredContext) -> str:
    if not context.capabilities:
        return "none"
    return "; ".join(
        f"{kind}: {', '.join(names)}" for kind, names in sorted(context.capabilities.items())
    )


def _tasks_from_text(text: str) -> list[Task]:
    """Derive tasks from the planner reply, one per non-empty line."""
    tasks: list[Task] = []
    for line in text.splitlines():
        description = _TASK_PREFIX.sub("", line).strip()
        if description:
            tasks.append(Task(id=f"task-{len(tasks) + 1}", description=description))
    if not tasks:
        tasks.append(Task(id="task-1", description=text.strip() or "no-op"))
    return tasks


# --- stages -----------------------------------------------------------------


def initialize(state: WorkflowState, context: WorkflowContext) -> WorkflowState:
    """Reset the run and mark it as running."""
    context.emit(
        WorkflowEvents.WORKFLOW_STARTED,
        source=STAGE_INITIALIZE,
        payload={"request": state.request},
    )
    return _updated(
        state,
        status="running",
        context=DiscoveredContext(),
        plan=None,
        current_task=None,
        completed_tasks=[],
        validations=[],
        review=None,
        errors=[],
        attempts=0,
    )


def discovery(state: WorkflowState, context: WorkflowContext) -> WorkflowState:
    """Collect the capability inventory and run the registered discoverers."""
    inventory = context.capability_inventory()
    plugins = []
    errors = list(state.errors)
    for discoverer in context.discoverers():
        try:
            for plugin in discoverer.discover():
                plugins.append(plugin.metadata())
        except CoreError as exc:
            errors.append(
                WorkflowError(
                    stage=STAGE_DISCOVERY,
                    type=type(exc).__name__,
                    message=str(exc),
                )
            )
    discovered = DiscoveredContext(capabilities=inventory, plugins=plugins)
    return _updated(state, context=discovered, errors=errors)


def planning(state: WorkflowState, context: WorkflowContext) -> WorkflowState:
    """Ask the registered LLM for a plan and turn it into tasks."""
    provider = context.llm()
    prompt = (
        f"User request:\n{state.request or ''}\n\n"
        f"Available capabilities:\n{_format_capabilities(state.context)}\n\n"
        "Produce a short plan, one task per line."
    )
    reply = provider.complete([Message(role="user", content=prompt)])
    plan = Plan(summary=reply.content.strip(), tasks=_tasks_from_text(reply.content))
    return _updated(state, plan=plan)


def execution(state: WorkflowState, context: WorkflowContext) -> WorkflowState:
    """Execute every planned task using the registered LLM.

    Available tools are recorded in the prompt; the base workflow does not
    perform tool-calling yet.
    """
    provider = context.llm()
    if state.plan is None or not state.plan.tasks:
        errors = [
            *state.errors,
            WorkflowError(
                stage=STAGE_EXECUTION,
                type="InvalidState",
                message="cannot execute without a plan",
            ),
        ]
        return _updated(state, status="failed", errors=errors)

    tool_names = ", ".join(tool.name for tool in context.tools()) or "none"
    completed: list[Task] = []
    current: Task | None = None
    for task in state.plan.tasks:
        prompt = (
            f"User request:\n{state.request or ''}\n\n"
            f"Task:\n{task.description}\n\n"
            f"Available tools: {tool_names}\n\n"
            "Produce the result for this task."
        )
        reply = provider.complete([Message(role="user", content=prompt)])
        current = task.model_copy(update={"status": "completed", "output": reply.content})
        completed.append(current)
    return _updated(
        state,
        current_task=current,
        completed_tasks=completed,
        attempts=state.attempts + 1,
    )


def validation(state: WorkflowState, context: WorkflowContext) -> WorkflowState:
    """Run every registered validator against the current task."""
    validators = context.validators()
    if not validators:
        return _updated(state, validations=[])

    data = ValidationInput(
        request=state.request or "",
        task=state.current_task.description if state.current_task else None,
        output=state.current_task.output if state.current_task else None,
    )
    records = [
        ValidationRecord(
            validator=validator.name,
            passed=result.passed,
            messages=result.messages,
            task_id=state.current_task.id if state.current_task else None,
        )
        for validator in validators
        for result in (validator.validate(data),)
    ]
    return _updated(state, validations=records)


def review(state: WorkflowState, context: WorkflowContext) -> WorkflowState:
    """Ask the registered LLM to review the run and decide the status."""
    provider = context.llm()
    prompt = (
        f"User request:\n{state.request or ''}\n\n"
        f"Plan:\n{state.plan.summary if state.plan else ''}\n\n"
        f"Results:\n{_format_results(state)}\n\n"
        f"Validations:\n{_format_validations(state)}\n\n"
        'Reply "APPROVED" or "REJECT" with feedback.'
    )
    reply = provider.complete([Message(role="user", content=prompt)])
    approved = "REJECT" not in reply.content.upper()
    feedback = reply.content.strip()
    review_result = ReviewResult(
        approved=approved,
        feedback=feedback,
        summary=feedback.splitlines()[0] if feedback else "",
    )

    validations_ok = all(record.passed for record in state.validations)
    if approved and validations_ok:
        return _updated(state, review=review_result, status="completed")
    if state.attempts < context.options.max_attempts:
        context.emit(
            WorkflowEvents.WORKFLOW_RETRY,
            source=STAGE_REVIEW,
            payload={
                "attempt": state.attempts + 1,
                "reason": "review_rejected" if not approved else "validation_failed",
            },
        )
        return _updated(state, review=review_result, status="running")
    return _updated(state, review=review_result, status="failed")


def _format_results(state: WorkflowState) -> str:
    if not state.completed_tasks:
        return "none"
    return "\n".join(
        f"- {task.id}: {task.output or ''}" for task in state.completed_tasks
    )


def _format_validations(state: WorkflowState) -> str:
    if not state.validations:
        return "none"
    return "\n".join(
        f"- {record.validator}: {'passed' if record.passed else 'failed'}"
        for record in state.validations
    )


# --- routing ----------------------------------------------------------------


def route_after_planning(state: WorkflowState) -> str:
    """End early when planning failed, otherwise continue to execution."""
    if state.status == "failed" or state.plan is None:
        return ROUTE_END
    return ROUTE_EXECUTION


def route_after_review(state: WorkflowState, options: WorkflowOptions) -> str:
    """End on approval, retry execution while attempts remain, else fail."""
    if state.status == "failed":
        return ROUTE_END
    validations_ok = all(record.passed for record in state.validations)
    approved = state.review is not None and state.review.approved
    if approved and validations_ok:
        return ROUTE_END
    if state.attempts < options.max_attempts:
        return ROUTE_EXECUTION
    return ROUTE_END
