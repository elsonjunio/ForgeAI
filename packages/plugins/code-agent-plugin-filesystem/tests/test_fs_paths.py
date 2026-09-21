from __future__ import annotations

from pathlib import Path

import pytest

from code_agent_plugin_filesystem import PathSecurityError
from code_agent_plugin_filesystem.paths import resolve_path


def test_resolve_within_root(tmp_path: Path) -> None:
    assert resolve_path(tmp_path, "a.txt") == (tmp_path / "a.txt").resolve()


def test_reject_traversal(tmp_path: Path) -> None:
    with pytest.raises(PathSecurityError):
        resolve_path(tmp_path, "../escape.txt")


def test_reject_absolute_outside(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    with pytest.raises(PathSecurityError):
        resolve_path(tmp_path, str(outside))


def test_allow_outside(tmp_path: Path) -> None:
    resolved = resolve_path(tmp_path, "../escape.txt", allow_outside=True)
    assert resolved.name == "escape.txt"


def test_reject_empty(tmp_path: Path) -> None:
    with pytest.raises(PathSecurityError):
        resolve_path(tmp_path, "")
