from __future__ import annotations

import pytest

from forge_cli.cli import load_plugin, main
from forge_cli.interaction import TerminalInteractionProvider


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip()


def test_once_without_provider_reports_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["--once", "hi", "--no-discover"])
    assert code == 1
    assert "LLMProvider" in capsys.readouterr().err


def test_load_plugin_class() -> None:
    plugin = load_plugin("forge_cli.interaction:TerminalInteractionProvider")
    assert isinstance(plugin, TerminalInteractionProvider)


def test_load_plugin_invalid_spec() -> None:
    with pytest.raises(ValueError):
        load_plugin("not-a-spec")
