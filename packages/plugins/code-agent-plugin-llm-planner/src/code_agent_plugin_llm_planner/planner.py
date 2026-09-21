"""LLM-based planner: turns a request into an ``ExecutionPlan``.

The planner resolves the default :class:`~core.LLMProvider` through a
:class:`~core.CapabilitySource` (provided by the plugin context) and asks it for
a JSON plan. It only references capabilities that the request advertises, so it
never needs concrete tool implementations.
"""

from __future__ import annotations

import json
import re
import uuid

from core import (
    CoreError,
    Executable,
    ExecutionPlan,
    LLMProvider,
    Message,
    MissingCapabilityError,
    Planner,
    PlanningRequest,
    PlanningResult,
)
from core.contracts.registry import CapabilitySource

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
DEFAULT_MAX_NODES = 8

_SYSTEM_PROMPT = (
    "You are a planning component for an iterative agent. Produce an execution "
    'plan as JSON with the shape {"id": string, "needs_more_info": boolean, '
    '"nodes": [{"id": string, "capability": string, "description": string, '
    '"parameters": object}], "edges": [{"source": string, "target": string}]}. '
    "Use only the executable capability ids from the provided list as node "
    "capabilities (never the LLM or a planner). Set \"needs_more_info\": true "
    "when the plan only gathers information needed for a later planning step; "
    'set it false when the plan completes the user\'s request. If none fits, '
    "return an empty nodes list. Return only JSON."
)


class LLMPlannerError(CoreError):
    """Raised when the planner cannot produce a valid ``ExecutionPlan``."""


class LLMPlanner(Planner):
    """A planner that delegates plan generation to an LLM provider.

    Args:
        source: capability source used to resolve the LLM provider.
        provider_name: specific provider name; defaults to the default provider.
        max_nodes: maximum number of nodes kept from the generated plan.
        system_prompt: overrides the built-in planning instruction.
    """

    def __init__(
        self,
        *,
        source: CapabilitySource,
        provider_name: str | None = None,
        max_nodes: int = DEFAULT_MAX_NODES,
        system_prompt: str | None = None,
    ) -> None:
        if max_nodes < 1:
            raise ValueError("max_nodes must be >= 1")
        self._source = source
        self._provider_name = provider_name
        self._max_nodes = max_nodes
        self._system_prompt = system_prompt or _SYSTEM_PROMPT

    @property
    def name(self) -> str:
        return "llm-planner"

    def plan(self, request: PlanningRequest) -> PlanningResult:
        """Ask the LLM for a plan and validate it as an ``ExecutionPlan``."""
        provider = self._resolve_provider()
        response = provider.complete(
            [
                Message(role="system", content=self._system_prompt),
                Message(role="user", content=self._build_prompt(request)),
            ]
        )
        plan, needs_more_info = self._parse_response(response.content)
        return PlanningResult(
            plan=plan,
            rationale=response.content.strip()[:500],
            needs_more_info=needs_more_info,
            metadata={"provider": provider.name},
        )

    def _resolve_provider(self) -> LLMProvider:
        if self._provider_name is not None:
            capability = self._source.capability(LLMProvider, self._provider_name)
        else:
            capability = self._source.default_capability(LLMProvider)
        if not isinstance(capability, LLMProvider):
            raise MissingCapabilityError(
                "no LLM provider available for planning; install an LLM plugin"
            )
        return capability

    def _build_prompt(self, request: PlanningRequest) -> str:
        capabilities = request.capabilities
        listing = (
            "\n".join(f"- {d.id}: {d.description}" for d in capabilities)
            if capabilities
            else "(none)"
        )
        if request.observations:
            observed = "\n".join(
                f"- {obs.node_id} ({obs.capability or '?'}): "
                f"{obs.output[:500]}{'…' if len(obs.output) > 500 else ''}"
                for obs in request.observations
            )
        else:
            observed = "(none)"
        return (
            f"User request:\n{request.request}\n\n"
            f"Available executable capabilities:\n{listing}\n\n"
            f"Information already gathered:\n{observed}\n\n"
            "Produce the JSON plan."
        )

    def _parse_response(self, content: str) -> tuple[ExecutionPlan, bool]:
        raw = self._extract_json(content)
        if raw is None:
            raise LLMPlannerError("planner did not return JSON")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMPlannerError(f"invalid plan JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMPlannerError("plan JSON must be an object")
        nodes = data.get("nodes")
        if not isinstance(nodes, list):
            raise LLMPlannerError("plan JSON must contain a 'nodes' list")
        needs_more_info = bool(data.pop("needs_more_info", False))
        data.setdefault("id", f"plan-{uuid.uuid4().hex[:8]}")
        data["nodes"] = nodes[: self._max_nodes]
        try:
            plan = ExecutionPlan.model_validate(data)
        except Exception as exc:
            raise LLMPlannerError(f"invalid plan: {exc}") from exc
        self._validate_executable(plan)
        return plan, needs_more_info

    def _validate_executable(self, plan: ExecutionPlan) -> None:
        """Reject plans whose nodes do not reference executable capabilities."""
        for node in plan.nodes:
            capability_id = node.capability or ""
            kind, separator, name = capability_id.partition(":")
            capability = (
                self._source.capability(kind, name) if separator and name else None
            )
            if not isinstance(capability, Executable):
                raise LLMPlannerError(
                    f"plan node {node.id!r} references non-executable capability "
                    f"{capability_id!r}"
                )

    @staticmethod
    def _extract_json(content: str) -> str | None:
        fenced = _JSON_FENCE.search(content)
        if fenced is not None:
            return fenced.group(1).strip()
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end < start:
            return None
        return content[start : end + 1]
