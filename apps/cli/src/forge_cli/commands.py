"""Slash-command handling for the CLI.

Commands are split into chat commands (need a session) and inspection/execution
commands (only need the core), so the CLI is usable for developing plugins even
when no LLM provider is registered.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from core import (
    CompactionRequest,
    CoreContainer,
    CoreError,
    ExecutionBudgets,
    ExecutionContext,
    ExecutionPlan,
    ExecutionResult,
    InteractionRequest,
    LLMUsage,
    Message,
    Observation,
    Planner,
    PlanningRequest,
    PlanningResult,
    SynthesisMode,
    SynthesisRequest,
    Synthesizer,
    ValidationInput,
    Validator,
    merge_usage,
)
from forge_cli.inspect import (
    format_capabilities,
    format_groups,
    format_planners,
    format_plugins,
    format_providers,
)
from forge_cli.session import ChatSession

HELP = [
    "comandos:",
    "  /help                 mostra esta ajuda",
    "  /exit | /quit         encerra",
    "  /clear                limpa o histórico",
    "  /history              mostra o histórico",
    "  /system <texto>       define o system prompt",
    "  /plugins              lista plugins registrados",
    "  /capabilities [kind]  lista capabilities",
    "  /groups               lista grupos",
    "  /planners [group]     lista planners",
    "  /providers            lista LLM providers e o default",
    "  /config               mostra a configuração resolvida",
    "  /interaction <msg>    testa o InteractionProvider",
    "  /plan <request>       planeja e mostra o ExecutionPlan",
    "  /run <request>        planeja e executa (planner + executor + síntese)",
]

_NO_SESSION = "sem sessão (nenhum LLMProvider registrado)"
_NO_PLANNER = "nenhum Planner registrado (instale um plugin de planner)"
_NO_SYNTHESIZER = (
    "nenhum Synthesizer registrado; instale um plugin de síntese "
    "(ex.: code-agent-plugin-llm-synthesizer) para obter a resposta final"
)

_MAX_OUTPUT_LINES = 40
_MAX_OUTPUT_CHARS = 2000
_MAX_SCRATCH_LINES = 50


@dataclass
class CommandResult:
    """Output of a slash command."""

    output: list[str] = field(default_factory=list)
    should_exit: bool = False


def handle_command(
    line: str, *, core: CoreContainer, session: ChatSession | None
) -> CommandResult | None:
    """Handle ``line`` if it is a slash command, else return ``None``."""
    if not line.startswith("/"):
        return None
    head, _, arg = line[1:].partition(" ")
    name = head.strip().lower()
    arg = arg.strip()

    if name in {"exit", "quit"}:
        return CommandResult(["até logo"], should_exit=True)
    if name == "help":
        return CommandResult(list(HELP))
    if name == "clear":
        if session is None:
            return CommandResult([_NO_SESSION])
        session.clear()
        return CommandResult(["histórico limpo"])
    if name == "history":
        if session is None:
            return CommandResult([_NO_SESSION])
        return CommandResult(
            [f"{message.role}: {message.content}" for message in session.history]
            or ["(vazio)"]
        )
    if name == "system":
        if session is None:
            return CommandResult([_NO_SESSION])
        session.set_system_prompt(arg)
        return CommandResult(["system prompt atualizado"])
    if name == "plugins":
        return CommandResult(format_plugins(core.registry))
    if name == "capabilities":
        return CommandResult(format_capabilities(core.registry, arg or None))
    if name == "groups":
        return CommandResult(format_groups(core.registry))
    if name == "planners":
        return CommandResult(format_planners(core.registry, arg or None))
    if name == "providers":
        return CommandResult(format_providers(core.registry))
    if name == "config":
        return CommandResult(core.config.model_dump_json(indent=2).splitlines())
    if name == "interaction":
        return CommandResult(_interaction(core, arg))
    if name == "plan":
        return CommandResult(_plan(core, arg, session))
    if name == "run":
        return CommandResult(_run(core, arg, session))
    return CommandResult([f"comando desconhecido: /{name} (use /help)"])


def _context(
    core: CoreContainer, request: str, session: ChatSession | None = None
) -> ExecutionContext:
    return ExecutionContext(
        request=request,
        capabilities=tuple(core.registry.executable_capability_descriptors()),
        metadata={"working_directory": os.getcwd()},
        history=tuple(_history(session, core.config.budgets.history_limit)),
    )


def _history(session: ChatSession | None, limit: int) -> list[Message]:
    """Return the most recent conversation messages to inject as history."""
    if session is None or limit <= 0:
        return []
    return session.history[-limit:]


def _planner(core: CoreContainer) -> Planner | None:
    planner = core.registry.default_capability(Planner)
    return planner if isinstance(planner, Planner) else None


def _interaction(core: CoreContainer, message: str) -> list[str]:
    provider = core.registry.interaction
    if provider is None:
        return ["nenhum InteractionProvider configurado"]
    response = provider.request(
        InteractionRequest(kind="input", message=message or "diga algo")
    )
    return [
        f"resposta: value={response.value!r} approved={response.approved!r} "
        f"cancelled={response.cancelled!r}"
    ]


def _plan(core: CoreContainer, request: str, session: ChatSession | None = None) -> list[str]:
    planner = _planner(core)
    if planner is None:
        return [_NO_PLANNER]
    context = _context(core, request, session)
    planning = PlanningRequest(
        request=request,
        context=context,
        planners=tuple(core.registry.planner_descriptors()),
        max_nodes=core.config.budgets.max_nodes,
    )
    plan = planner.plan(planning).plan
    return _describe_plan(plan)


def _run(
    core: CoreContainer, request: str, session: ChatSession | None = None
) -> list[str]:
    """Plan, execute, observe, recover, compact and re-plan until done.

    The planner may return ``needs_more_info=True``, meaning the plan only
    gathers information; the gathered results are fed back into the next
    planning iteration until the planner produces the final plan (or the
    iteration limit is reached).

    When a node fails and the failure is recoverable (``ExecutionResult``
    carries the flag from the capability), the host feeds the error back to the
    planner and replans, bounded by the configured recoveries and by a
    no-progress guard that stops when the same ``(capability, parameters, error)``
    repeats.

    A plan that cannot be built (``InvalidPlanError`` and friends) or a planner
    that fails to produce one is handled the same way: the plan is discarded,
    an error observation (including the rejected plan when available) is folded
    into the accumulated observations, and the planner replans **with the full
    history preserved**. The same budget/no-progress guard applies.

    Budgets (``core.config.budgets``) bound iterations, recoveries and, when
    set, wall-clock time and tokens. A deterministic scratchpad records one line
    per executed step and survives compaction.

    When a :class:`Synthesizer` is registered:

    * a planner-requested ``PlanningResult.compaction`` — or the automatic
      char-threshold policy — folds the accumulated observations into a
      checkpoint (``mode="compact"``), fed back via
      ``PlanningRequest.checkpoint`` while ``keep_last`` observations stay
      verbatim;
    * once the run ends, the final answer is synthesized (``mode="answer"``)
      from the checkpoint plus the remaining observations.
    """
    planner = _planner(core)
    if planner is None:
        return [_NO_PLANNER]
    budgets = core.config.budgets
    synthesizer = _synthesizer(core)
    validators = _validators(core)
    context = _context(core, request, session)
    synthesizers = tuple(core.registry.capability_descriptors(Synthesizer))
    observations: list[Observation] = []
    checkpoint: str | None = None
    scratch_lines: list[str] = []
    usage: LLMUsage | None = None
    lines: list[str] = []
    seen_failures: set[tuple[str, ...]] = set()
    recoveries = 0
    started = time.monotonic()
    for iteration in range(1, budgets.max_iterations + 1):
        if _deadline_exceeded(started, budgets.deadline_seconds):
            lines.append(f"prazo ({budgets.deadline_seconds}s) excedido; encerrando")
            break
        planning = PlanningRequest(
            request=request,
            context=context,
            planners=tuple(core.registry.planner_descriptors()),
            synthesizers=synthesizers,
            observations=tuple(observations),
            checkpoint=checkpoint,
            scratchpad=_render_scratchpad(scratch_lines),
            max_nodes=budgets.max_nodes,
        )
        lines.append(f"[iteração {iteration}]")
        result: PlanningResult | None = None
        try:
            result = planner.plan(planning)
            usage = merge_usage(usage, result.usage)
            lines.extend(_describe_plan(result.plan))
            execution = core.executor.run(result.plan, context)
        except CoreError as exc:
            plan = result.plan if result is not None else None
            signature = _plan_error_signature(exc, plan)
            if signature in seen_failures:
                lines.append(
                    f"erro de plano repetido; sem progresso, encerrando: {exc}"
                )
                break
            if recoveries >= budgets.max_recoveries:
                lines.append(
                    f"limite de recuperações ({budgets.max_recoveries}) atingido"
                )
                break
            seen_failures.add(signature)
            recoveries += 1
            observations.append(_plan_error_observation(exc, plan))
            lines.append(f"plano inválido descartado: {type(exc).__name__}: {exc}")
            lines.append(
                f"recuperação {recoveries}/{budgets.max_recoveries}: "
                "replanejando com o erro observado"
            )
            continue
        lines.append(f"status: {execution.status}")
        lines.extend(_describe_results(execution))
        new_observations = _observations(result.plan, execution)
        observations.extend(new_observations)
        scratch_lines.extend(_scratch_lines(new_observations))
        if _token_budget_exceeded(usage, budgets.max_total_tokens):
            lines.append(
                f"limite de tokens ({budgets.max_total_tokens}) atingido; encerrando"
            )
            break
        if execution.status != "completed":
            signature = _failure_signature(result.plan, execution)
            if not execution.recoverable:
                lines.append("(falha não recuperável; encerrando)")
                break
            if signature in seen_failures:
                lines.append("(falha repetida; sem progresso, encerrando)")
                break
            if recoveries >= budgets.max_recoveries:
                lines.append(
                    f"limite de recuperações ({budgets.max_recoveries}) atingido"
                )
                break
            seen_failures.add(signature)
            recoveries += 1
            lines.append(
                f"recuperação {recoveries}/{budgets.max_recoveries}: "
                "replanejando com o erro observado"
            )
            continue
        if not result.needs_more_info:
            issues, validation_usage = _run_validators(
                validators,
                request,
                observations,
                checkpoint,
                _render_scratchpad(scratch_lines),
                success=True,
            )
            usage = merge_usage(usage, validation_usage)
            if not issues:
                break
            signature = ("validator", *issues)
            if signature in seen_failures:
                lines.append(
                    "validação falhou de novo; sem progresso, encerrando: "
                    + "; ".join(issues)
                )
                break
            if recoveries >= budgets.max_recoveries:
                lines.append(
                    "validação não atendida: " + "; ".join(issues)
                    + f" (limite de recuperações {budgets.max_recoveries} atingido)"
                )
                break
            seen_failures.add(signature)
            recoveries += 1
            observations.append(
                Observation(
                    node_id="validator",
                    success=False,
                    output="; ".join(issues),
                )
            )
            lines.append("validação não atendida: " + "; ".join(issues))
            lines.append(
                f"recuperação {recoveries}/{budgets.max_recoveries}: "
                "replanejando para atender à validação"
            )
            continue
        if not new_observations:
            lines.append("(nenhuma nova informação coletada; encerrando)")
            break
        compaction = _compaction_request(result, observations, synthesizer, budgets)
        if compaction is not None:
            checkpoint, observations, note, compact_usage = _compact(
                synthesizer, request, observations, checkpoint, compaction
            )
            usage = merge_usage(usage, compact_usage)
            lines.append(note)
    else:
        lines.append(f"limite de iterações ({budgets.max_iterations}) atingido")
    if synthesizer is not None:
        answer_lines, synthesis_usage = _final_answer(
            synthesizer, request, observations, checkpoint
        )
        usage = merge_usage(usage, synthesis_usage)
        lines.extend(answer_lines)
    else:
        lines.append(_NO_SYNTHESIZER)
    lines.extend(_usage_lines(usage))
    return lines


def _plan_error_signature(
    exc: CoreError, plan: ExecutionPlan | None
) -> tuple[str, ...]:
    """Stable signature for a rejected plan, ignoring volatile plan ids.

    When the plan is available it is keyed on the plan shape (nodes/edges), so
    the same broken plan is recognised across iterations even though its id is
    random each time.
    """
    if plan is not None:
        nodes = "|".join(sorted(node.id for node in plan.nodes))
        edges = "|".join(
            sorted(f"{edge.source}->{edge.target}" for edge in plan.edges)
        )
        return (type(exc).__name__, nodes, edges)
    return (type(exc).__name__, str(exc))


def _plan_error_observation(
    exc: CoreError, plan: ExecutionPlan | None
) -> Observation:
    """Turn a planning/build failure into an observation for the next plan.

    Keeps the full history intact (observations are only appended to) and
    includes an extract of the rejected plan, when one was produced, so the
    planner can see exactly what was wrong.
    """
    output = f"{type(exc).__name__}: {exc}"
    if plan is not None:
        nodes = ", ".join(node.id for node in plan.nodes) or "(none)"
        edges = (
            ", ".join(f"{edge.source}->{edge.target}" for edge in plan.edges)
            or "(none)"
        )
        output += f" | rejected plan: nodes=[{nodes}] edges=[{edges}]"
    return Observation(node_id="plan", success=False, output=output)


def _failure_signature(
    plan: ExecutionPlan, execution: ExecutionResult
) -> tuple[str, ...]:
    """Extract a stable signature for the failed node(s) of a run.

    Keyed on ``capability`` + ``parameters`` + error (not the node id), so the
    same failing command is detected even if the planner renames the node.
    """
    nodes = {node.id: node for node in plan.nodes}
    entries: list[str] = []
    for node_id, result in execution.results.items():
        if result.success:
            continue
        node = nodes.get(node_id)
        capability = node.capability if node is not None else None
        parameters = (
            json.dumps(node.parameters, sort_keys=True, default=str)
            if node is not None
            else ""
        )
        entries.append(f"{capability}|{parameters}|{result.error or ''}")
    return tuple(sorted(entries))


def _synthesizer(core: CoreContainer) -> Synthesizer | None:
    capability = core.registry.default_capability(Synthesizer)
    return capability if isinstance(capability, Synthesizer) else None


def _validators(core: CoreContainer) -> list[Validator]:
    return [
        capability
        for capability in core.registry.capabilities(Validator)
        if isinstance(capability, Validator)
    ]


def _run_validators(
    validators: list[Validator],
    request: str,
    observations: list[Observation],
    checkpoint: str | None,
    scratchpad: str,
    *,
    success: bool,
) -> tuple[list[str], LLMUsage | None]:
    """Judge the whole outcome of a run; return failure messages and usage."""
    if not validators:
        return [], None
    data = ValidationInput(
        request=request,
        success=success,
        observations=tuple(observations),
        checkpoint=checkpoint or "",
        scratchpad=scratchpad,
    )
    issues: list[str] = []
    usage: LLMUsage | None = None
    for validator in validators:
        try:
            result = validator.validate(data)
        except CoreError as exc:
            issues.append(f"{validator.name}: {type(exc).__name__}: {exc}")
            continue
        usage = merge_usage(usage, result.usage)
        if not result.passed:
            details = "; ".join(result.messages) or "não atendido"
            issues.append(f"{validator.name}: {details}")
    return issues, usage


def _compaction_request(
    result: PlanningResult,
    observations: list[Observation],
    synthesizer: Synthesizer | None,
    budgets: ExecutionBudgets,
) -> CompactionRequest | None:
    """Planner-requested compaction, else the host's char-threshold policy."""
    if result.compaction is not None and result.compaction.enabled:
        return result.compaction
    if synthesizer is None or budgets.compaction_chars <= 0:
        return None
    total = sum(len(observation.output) for observation in observations)
    if total > budgets.compaction_chars:
        return CompactionRequest(
            keep_last=budgets.compaction_keep_last,
            reason="limite de contexto atingido (auto)",
        )
    return None


def _compact(
    synthesizer: Synthesizer | None,
    request: str,
    observations: list[Observation],
    checkpoint: str | None,
    compaction: CompactionRequest,
) -> tuple[str | None, list[Observation], str, LLMUsage | None]:
    """Fold observations into a checkpoint, keeping ``keep_last`` verbatim."""
    keep_last = max(0, min(compaction.keep_last, len(observations)))
    folded = observations[: len(observations) - keep_last]
    kept = observations[len(observations) - keep_last :]
    if not folded:
        return checkpoint, observations, "compactação pedida, mas nada a resumir", None
    if synthesizer is None:
        return (
            checkpoint,
            observations,
            "compactação pedida, mas nenhum Synthesizer registrado",
            None,
        )
    try:
        synthesis = synthesizer.synthesize(
            _synthesis_request(request, folded, checkpoint, "compact")
        )
    except CoreError as exc:
        return (
            checkpoint,
            observations,
            f"compactação falhou ({type(exc).__name__}): {exc}",
            None,
        )
    return (
        synthesis.text,
        kept,
        f"compactação: {len(folded)} observação(ões) resumida(s)",
        synthesis.usage,
    )


def _final_answer(
    synthesizer: Synthesizer,
    request: str,
    observations: list[Observation],
    checkpoint: str | None,
) -> tuple[list[str], LLMUsage | None]:
    try:
        synthesis = synthesizer.synthesize(
            _synthesis_request(request, observations, checkpoint, "answer")
        )
    except CoreError as exc:
        return [f"síntese falhou ({type(exc).__name__}): {exc}"], None
    return [
        f"resposta: [{synthesizer.name}]",
        *_format_answer(synthesis.text),
    ], synthesis.usage


def _format_answer(text: str) -> list[str]:
    """Render the final synthesized answer in full (no truncation, no indent)."""
    return text.splitlines() or [""]


def _synthesis_request(
    request: str,
    observations: list[Observation],
    checkpoint: str | None,
    mode: SynthesisMode,
) -> SynthesisRequest:
    return SynthesisRequest(
        request=request,
        observations=tuple(observations),
        checkpoint=checkpoint,
        mode=mode,
    )


def _scratch_lines(observations: list[Observation]) -> list[str]:
    """One deterministic line per executed step, for the planner's scratchpad."""
    lines: list[str] = []
    for observation in observations:
        status = "ok" if observation.success else "FAILED"
        label = observation.capability or observation.node_id
        parameters = (
            json.dumps(observation.parameters, sort_keys=True, default=str)
            if observation.parameters
            else ""
        )
        lines.append(f"- {label} {parameters} -> {status}: {_first_line(observation.output)}")
    return lines


def _render_scratchpad(lines: list[str]) -> str:
    if not lines:
        return ""
    if len(lines) > _MAX_SCRATCH_LINES:
        omitted = len(lines) - _MAX_SCRATCH_LINES
        return "\n".join(
            [f"(+{omitted} passo(s) anterior(es))", *lines[-_MAX_SCRATCH_LINES:]]
        )
    return "\n".join(lines)


def _first_line(text: str, limit: int = 160) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:limit]
    return ""


def _deadline_exceeded(started: float, seconds: float | None) -> bool:
    return seconds is not None and (time.monotonic() - started) > seconds


def _token_budget_exceeded(usage: LLMUsage | None, limit: int | None) -> bool:
    if limit is None or usage is None:
        return False
    total = usage.total_tokens
    if total is None:
        parts = [
            value
            for value in (usage.prompt_tokens, usage.completion_tokens)
            if value is not None
        ]
        total = sum(parts) if parts else None
    return total is not None and total > limit


def _usage_lines(usage: LLMUsage | None) -> list[str]:
    if usage is None:
        return []
    return [
        f"uso: prompt={usage.prompt_tokens} completion={usage.completion_tokens} "
        f"total={usage.total_tokens}"
    ]


def _describe_results(execution: ExecutionResult) -> list[str]:
    lines: list[str] = []
    for node_id, result in execution.results.items():
        if result.success:
            lines.append(f"  {node_id}: ok")
            lines.extend(_format_node_output(result.output))
        else:
            lines.append(f"  {node_id}: {result.error or 'failed'}")
    if execution.error:
        lines.append(f"erro: {execution.error}")
    return lines


def _observations(plan: ExecutionPlan, execution: ExecutionResult) -> list[Observation]:
    nodes = {node.id: node for node in plan.nodes}
    return [
        Observation(
            node_id=node_id,
            capability=nodes[node_id].capability if node_id in nodes else None,
            success=result.success,
            output=_as_text(result.output, result.error),
            parameters=dict(nodes[node_id].parameters) if node_id in nodes else {},
        )
        for node_id, result in execution.results.items()
    ]


def _as_text(output: object, error: str | None) -> str:
    if output is not None:
        return output if isinstance(output, str) else str(output)
    return error or ""


def _format_node_output(output: Any) -> list[str]:
    """Render a node output indented and truncated for the terminal."""
    if output is None:
        return []
    text = output if isinstance(output, str) else str(output)
    lines = text.splitlines() or [""]
    formatted = [f"    {line}" for line in lines[:_MAX_OUTPUT_LINES]]
    if len(lines) > _MAX_OUTPUT_LINES or len(text) > _MAX_OUTPUT_CHARS:
        formatted.append("    … (output truncated)")
    return formatted


def _describe_plan(plan: ExecutionPlan) -> list[str]:
    lines = [f"plan {plan.id}: {len(plan.nodes)} node(s)"]
    lines.extend(f"  {node.id} -> {node.capability}" for node in plan.nodes)
    return lines
