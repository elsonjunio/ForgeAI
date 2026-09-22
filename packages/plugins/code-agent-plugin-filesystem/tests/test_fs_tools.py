from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from code_agent_plugin_filesystem import (
    ListDirTool,
    PathSecurityError,
    ReadFileTool,
    StatTool,
    WriteFileTool,
)
from core import (
    ExecutionContext,
    InteractionRequest,
    InteractionResponse,
    NodeExecutionRequest,
    PlanNode,
)


class _Interaction:
    def __init__(self, approved: bool = True) -> None:
        self.approved = approved
        self.requests: list[InteractionRequest] = []

    def request(self, request: InteractionRequest) -> InteractionResponse:
        self.requests.append(request)
        return InteractionResponse(approved=self.approved, value="y" if self.approved else "n")


def _request(
    node_id: str,
    capability: str,
    parameters: dict[str, Any],
    interaction: Any = None,
) -> NodeExecutionRequest:
    return NodeExecutionRequest(
        node=PlanNode(id=node_id, capability=capability, parameters=parameters),
        context=ExecutionContext(request="x"),
        interaction=interaction,
    )


def test_read_file(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    tool = ReadFileTool(root=tmp_path)
    result = tool.execute(_request("n1", "tool:fs.read_file", {"path": "a.txt"}))
    assert result.success
    assert result.output == "hello"


def test_read_file_truncates(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("0123456789", encoding="utf-8")
    tool = ReadFileTool(root=tmp_path, max_read_bytes=4)
    result = tool.execute(_request("n1", "tool:fs.read_file", {"path": "a.txt"}))
    assert result.output == "0123"
    assert result.metadata["truncated"] is True


def test_list_dir(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("", encoding="utf-8")
    (tmp_path / "a").mkdir()
    tool = ListDirTool(root=tmp_path)
    result = tool.execute(_request("n1", "tool:fs.list_dir", {}))
    assert (result.output or "").splitlines() == ["a/", "b.txt"]


def test_stat(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    tool = StatTool(root=tmp_path)
    result = tool.execute(_request("n1", "tool:fs.stat", {"path": "a.txt"}))
    assert '"exists": true' in (result.output or "")


def test_write_file_approved(tmp_path: Path) -> None:
    tool = WriteFileTool(root=tmp_path, interaction=_Interaction(True))
    result = tool.execute(
        _request("n1", "tool:fs.write_file", {"path": "out.txt", "content": "hi"})
    )
    assert result.success
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "hi"


def test_write_file_denied(tmp_path: Path) -> None:
    tool = WriteFileTool(root=tmp_path, interaction=_Interaction(False))
    result = tool.execute(
        _request("n1", "tool:fs.write_file", {"path": "out.txt", "content": "hi"})
    )
    assert not result.success
    assert not (tmp_path / "out.txt").exists()


def test_write_file_identical_content_is_noop(tmp_path: Path) -> None:
    (tmp_path / "out.txt").write_text("hi", encoding="utf-8")
    interaction = _Interaction(True)
    tool = WriteFileTool(root=tmp_path, interaction=interaction)
    result = tool.execute(
        _request("n1", "tool:fs.write_file", {"path": "out.txt", "content": "hi"})
    )
    assert result.success
    assert result.metadata.get("skipped") is True
    assert "unchanged" in (result.output or "")
    assert interaction.requests == []  # a no-op needs no confirmation


def test_write_file_dry_run_does_not_write(tmp_path: Path) -> None:
    tool = WriteFileTool(root=tmp_path)  # confirmation on, but dry-run skips it
    result = tool.execute(
        _request(
            "n1",
            "tool:fs.write_file",
            {"path": "out.txt", "content": "hi", "dry_run": True},
        )
    )
    assert result.success
    assert result.metadata.get("dry_run") is True
    assert "would create" in (result.output or "")
    assert not (tmp_path / "out.txt").exists()


def test_write_file_dry_run_reports_update(tmp_path: Path) -> None:
    (tmp_path / "out.txt").write_text("old", encoding="utf-8")
    tool = WriteFileTool(root=tmp_path)
    result = tool.execute(
        _request(
            "n1",
            "tool:fs.write_file",
            {"path": "out.txt", "content": "new", "dry_run": True},
        )
    )
    assert "would update" in (result.output or "")


def test_write_file_without_provider_fails(tmp_path: Path) -> None:
    tool = WriteFileTool(root=tmp_path)
    result = tool.execute(
        _request("n1", "tool:fs.write_file", {"path": "out.txt", "content": "hi"})
    )
    assert not result.success
    assert "InteractionProvider" in (result.error or "")


def test_read_outside_root_raises(tmp_path: Path) -> None:
    # The tool raises; the plan executor converts it into a failed NodeResult.
    tool = ReadFileTool(root=tmp_path)
    with pytest.raises(PathSecurityError):
        tool.execute(_request("n1", "tool:fs.read_file", {"path": "../secret.txt"}))


def test_read_missing_file_is_recoverable(tmp_path: Path) -> None:
    tool = ReadFileTool(root=tmp_path)
    result = tool.execute(_request("n1", "tool:fs.read_file", {"path": "missing.txt"}))
    assert not result.success
    assert result.recoverable is True
    assert "FileNotFoundError" in (result.error or "")


def test_list_missing_dir_is_recoverable(tmp_path: Path) -> None:
    tool = ListDirTool(root=tmp_path)
    result = tool.execute(_request("n1", "tool:fs.list_dir", {"path": "nope"}))
    assert not result.success
    assert result.recoverable is True


def test_read_missing_file_hints_existing_names(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hi", encoding="utf-8")
    tool = ReadFileTool(root=tmp_path)
    result = tool.execute(_request("n1", "tool:fs.read_file", {"path": "readme.md"}))
    assert not result.success
    message = result.error or ""
    assert "README.md" in message
    assert "did you mean" in message


def test_tool_descriptions_guide_verification(tmp_path: Path) -> None:
    assert "fs.stat" in ReadFileTool(root=tmp_path).contract.description
    assert "fs.stat" in WriteFileTool(root=tmp_path).contract.description
    assert "fs.list_dir" in ListDirTool(root=tmp_path).contract.description
