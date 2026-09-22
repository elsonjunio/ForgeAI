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
from typing import Any

from core import (
    CompactionRequest,
    CoreError,
    Executable,
    ExecutionPlan,
    LLMProvider,
    Message,
    MissingCapabilityError,
    Observation,
    Planner,
    PlanningRequest,
    PlanningResult,
)
from core.contracts.registry import CapabilitySource

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
DEFAULT_MAX_NODES = 8
_MAX_HISTORY_MESSAGES = 20

_SYSTEM_PROMPT = (
    "You are a planning component for an iterative agent. Produce an execution "
    'plan as JSON with the shape {"id": string, "needs_more_info": boolean, '
    '"nodes": [{"id": string, "capability": string, "description": string, '
    '"parameters": object}], "edges": [{"source": string, "target": string}], '
    '"compaction": {"keep_last": integer}}. '
    "Use only the executable capability ids from the provided list as node "
    "capabilities (never the LLM or a planner). "
    "Every edge source and target MUST be the id of a declared node: node ids "
    "are unique, referenced exactly as written, with no self-loops and no "
    "cycles. "
    "Never assume a path exists or a directory layout is known. Verify before "
    "acting: before reading a file, confirm the path with a read capability "
    "(for example fs.stat, checking exists/is_file) or discover it with "
    "fs.list_dir; add an edge so the check runs before the action. Before "
    "writing a file, confirm the target directory exists (fs.stat is_dir / "
    "fs.list_dir) and make sure the path is the intended one (use create_dirs "
    "only when you really want to create the directory). Never invent file "
    "names: use the names returned by fs.list_dir. Do not add a check when the "
    "path already came from a successful fs.list_dir in the gathered "
    "information. "
    "Set \"needs_more_info\": true when the plan only gathers information needed "
    "for a later planning step; "
    'set it false when the plan completes the user\'s request. When an '
    "observation is marked [FAILED], do not repeat the same command with the "
    "same parameters: read the error, verify preconditions with a read "
    "capability (for example fs.stat/fs.list_dir) or choose another capability, "
    "and return a new plan. If the failure cannot be avoided, return an empty "
    'nodes list. When a synthesizer '
    "is available and many steps have already been gathered, you may request "
    'compaction with "compaction": {"keep_last": integer} (0 folds everything); '
    "omit it otherwise. If none fits, return an empty nodes list. Return only JSON."
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
        limit = request.max_nodes if request.max_nodes is not None else self._max_nodes
        response = provider.complete(
            [
                Message(role="system", content=self._system_prompt),
                Message(role="user", content=self._build_prompt(request, limit)),
            ]
        )
        plan, needs_more_info, compaction = self._parse_response(
            response.content, limit
        )
        return PlanningResult(
            plan=plan,
            rationale=response.content.strip()[:500],
            needs_more_info=needs_more_info,
            compaction=compaction,
            usage=response.usage,
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

    def _build_prompt(self, request: PlanningRequest, limit: int) -> str:
        capabilities = request.capabilities
        listing = (
            "\n".join(f"- {d.id}: {d.description}" for d in capabilities)
            if capabilities
            else "(none)"
        )
        synthesizers = (
            "\n".join(f"- {d.id}: {d.description}" for d in request.synthesizers)
            if request.synthesizers
            else "(none)"
        )
        if request.observations:
            observed = "\n".join(
                self._format_observation(obs) for obs in request.observations
            )
        else:
            observed = "(none)"
        return (
            f"User request:\n{request.request}\n\n"
            f"Conversation history:\n{self._format_history(request.history)}\n\n"
            f"Execution context:\n{self._format_context(request)}\n\n"
            f"Progress so far:\n{request.scratchpad or '(none)'}\n\n"
            f"Available executable capabilities:\n{listing}\n\n"
            f"Available synthesizers:\n{synthesizers}\n\n"
            f"Previous checkpoint:\n{request.checkpoint or '(none)'}\n\n"
            f"Information already gathered:\n{observed}\n\n"
            f"Node limit: {limit}.\n\n"
            "Produce the JSON plan."
        )

    @staticmethod
    def _format_history(messages: tuple[Message, ...]) -> str:
        if not messages:
            return "(none)"
        recent = messages[-_MAX_HISTORY_MESSAGES:]
        return "\n".join(
            f"- {message.role}: {message.content[:500]}"
            f"{'…' if len(message.content) > 500 else ''}"
            for message in recent
        )

    @staticmethod
    def _format_context(request: PlanningRequest) -> str:
        metadata = request.context.metadata
        if not metadata:
            return "(none)"
        return "\n".join(
            f"- {key}: "
            f"{value if isinstance(value, str) else json.dumps(value, default=str, sort_keys=True)}"
            for key, value in metadata.items()
        )

    @staticmethod
    def _format_observation(observation: Observation) -> str:
        status = "ok" if observation.success else "FAILED"
        output = observation.output[:500]
        suffix = "…" if len(observation.output) > 500 else ""
        parameters = (
            f" params={json.dumps(observation.parameters, sort_keys=True)}"
            if observation.parameters
            else ""
        )
        return (
            f"- {observation.node_id} ({observation.capability or '?'}) "
            f"[{status}]{parameters}: {output}{suffix}"
        )

    def _parse_response(
        self, content: str, max_nodes: int
    ) -> tuple[ExecutionPlan, bool, CompactionRequest | None]:
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
        if len(nodes) > max_nodes:
            raise LLMPlannerError(
                f"plan has {len(nodes)} nodes; at most {max_nodes} are allowed"
            )
        needs_more_info = bool(data.pop("needs_more_info", False))
        compaction = self._parse_compaction(data.pop("compaction", None))
        data.setdefault("id", f"plan-{uuid.uuid4().hex[:8]}")
        try:
            plan = ExecutionPlan.model_validate(data)
        except Exception as exc:
            raise LLMPlannerError(f"invalid plan: {exc}") from exc
        self._validate_executable(plan)
        return plan, needs_more_info, compaction

    @staticmethod
    def _parse_compaction(raw: Any) -> CompactionRequest | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise LLMPlannerError("plan 'compaction' must be an object")
        try:
            return CompactionRequest.model_validate(raw)
        except Exception as exc:
            raise LLMPlannerError(f"invalid compaction request: {exc}") from exc

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
