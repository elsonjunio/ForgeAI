"""ForgeAI command-line interface: chat plus plugin inspection.

For now the CLI is a chat REPL. It also exposes inspection commands and an
explicit ``--plugin`` loader so it can be used to build and test plugins before
they are installed.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from typing import Any

from core import (
    CoreConfig,
    CoreContainer,
    CoreError,
    Discoverer,
    LLMProvider,
    build_core,
    load_config,
)
from forge_cli.commands import handle_command
from forge_cli.interaction import TerminalInteractionProvider
from forge_cli.progress import ProgressObserver
from forge_cli.session import ChatSession


def load_plugin(spec: str) -> Any:
    """Import a plugin from ``module:attribute`` (a class or an instance)."""
    module_name, separator, attribute = spec.partition(":")
    if not separator or not attribute:
        raise ValueError(f"invalid plugin spec {spec!r}; expected 'module:attribute'")
    module = importlib.import_module(module_name)
    target = getattr(module, attribute)
    return target() if isinstance(target, type) else target


class _StreamPrinter:
    """Render streamed chunks and remember whether anything was printed."""

    def __init__(self) -> None:
        self.printed = False

    def __call__(self, text: str) -> None:
        self.printed = True
        print(text, end="", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forgeai", description="ForgeAI chat CLI")
    parser.add_argument("--config", metavar="ARQ", help="JSON configuration file")
    parser.add_argument("--system", metavar="TEXTO", help="system prompt")
    parser.add_argument("--no-stream", action="store_true", help="disable streaming")
    parser.add_argument(
        "--no-progress", action="store_true", help="disable live plan progress"
    )
    parser.add_argument(
        "--no-discover", action="store_true", help="disable entry-point discovery"
    )
    parser.add_argument(
        "--plugin",
        action="append",
        default=[],
        metavar="MODULE:ATTR",
        help="load a plugin explicitly (repeatable)",
    )
    parser.add_argument("--once", metavar="PROMPT", help="run a single turn and exit")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    return parser


def _build_container(args: argparse.Namespace) -> CoreContainer:
    config = load_config(args.config) if args.config else CoreConfig()
    plugins = [load_plugin(spec) for spec in args.plugin]
    discoverers: list[Discoverer] | None = [] if args.no_discover else None
    observer = None if args.no_progress else ProgressObserver()
    return build_core(
        config=config,
        plugins=plugins,
        discoverers=discoverers,
        interaction=TerminalInteractionProvider(),
        observer=observer,
    )


def _resolve_provider(core: CoreContainer) -> LLMProvider | None:
    provider = core.registry.default_capability(LLMProvider)
    return provider if isinstance(provider, LLMProvider) else None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.version:
        from core import __version__

        print(__version__)
        return 0

    try:
        core = _build_container(args)
    except (CoreError, ValueError) as exc:
        print(f"erro ao montar o core: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    try:
        provider = _resolve_provider(core)
        if args.once is not None:
            return _run_once(provider, args)
        return _run_repl(core, provider, args)
    finally:
        core.shutdown()


def _run_once(provider: LLMProvider | None, args: argparse.Namespace) -> int:
    if provider is None:
        print(
            "erro: nenhum LLMProvider registrado; instale um plugin de LLM",
            file=sys.stderr,
        )
        return 1
    printer = _StreamPrinter()
    session = ChatSession(
        provider,
        system_prompt=args.system,
        stream=not args.no_stream,
        on_chunk=printer,
    )
    try:
        reply = session.send(args.once)
    except CoreError as exc:
        print(f"erro ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
    if printer.printed:
        print()
    else:
        print(reply)
    return 0


def _run_repl(
    core: CoreContainer, provider: LLMProvider | None, args: argparse.Namespace
) -> int:
    printer = _StreamPrinter()
    session = (
        ChatSession(
            provider,
            system_prompt=args.system,
            stream=not args.no_stream,
            on_chunk=printer,
        )
        if provider is not None
        else None
    )
    print("ForgeAI chat — /help para comandos, /exit para sair")
    if provider is None:
        print(
            "aviso: nenhum LLMProvider registrado; comandos de inspeção continuam "
            "disponíveis",
            file=sys.stderr,
        )
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        try:
            result = handle_command(line, core=core, session=session)
        except CoreError as exc:
            print(f"erro ({type(exc).__name__}): {exc}")
            continue
        if result is not None:
            for output in result.output:
                print(output)
            if result.should_exit:
                break
            continue
        if session is None:
            print("erro: nenhum LLMProvider registrado")
            continue
        printer.printed = False
        try:
            reply = session.send(line)
        except CoreError as exc:
            print(f"erro ({type(exc).__name__}): {exc}")
            continue
        if printer.printed:
            print()
        else:
            print(reply)
    return 0
