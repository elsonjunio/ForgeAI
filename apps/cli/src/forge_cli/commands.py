"""Slash-command handling for the CLI.

Commands are split into chat commands (need a session) and inspection/execution
commands (only need the core), so the CLI is usable for developing plugins even
when no LLM provider is registered.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core import (
    CoreContainer,
    ExecutionContext,
    ExecutionPlan,
    InteractionRequest,
    Planner,
    PlanningRequest,
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
    "  /run <request>        planeja e executa (planner + executor)",
]

_NO_SESSION = "sem sessão (nenhum LLMProvider registrado)"
_NO_PLANNER = "nenhum Planner registrado (instale um plugin de planner)"


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
        return CommandResult(_plan(core, arg))
    if name == "run":
        return CommandResult(_run(core, arg))
    return CommandResult([f"comando desconhecido: /{name} (use /help)"])


def _context(core: CoreContainer, request: str) -> ExecutionContext:
    return ExecutionContext(
        request=request,
        capabilities=tuple(core.registry.capability_descriptors()),
    )


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


def _plan(core: CoreContainer, request: str) -> list[str]:
    planner = _planner(core)
    if planner is None:
        return [_NO_PLANNER]
    context = _context(core, request)
    planning = PlanningRequest(
        request=request,
        context=context,
        planners=tuple(core.registry.planner_descriptors()),
    )
    plan = planner.plan(planning).plan
    return _describe_plan(plan)


def _run(core: CoreContainer, request: str) -> list[str]:
    planner = _planner(core)
    if planner is None:
        return [_NO_PLANNER]
    context = _context(core, request)
    planning = PlanningRequest(
        request=request,
        context=context,
        planners=tuple(core.registry.planner_descriptors()),
    )
    plan = planner.plan(planning).plan
    execution = core.executor.run(plan, context)
    lines = _describe_plan(plan)
    lines.append(f"status: {execution.status}")
    lines.extend(
        f"  {node_id}: {'ok' if result.success else (result.error or 'failed')}"
        for node_id, result in execution.results.items()
    )
    if execution.error:
        lines.append(f"erro: {execution.error}")
    return lines


def _describe_plan(plan: ExecutionPlan) -> list[str]:
    lines = [f"plan {plan.id}: {len(plan.nodes)} node(s)"]
    lines.extend(f"  {node.id} -> {node.capability}" for node in plan.nodes)
    return lines
