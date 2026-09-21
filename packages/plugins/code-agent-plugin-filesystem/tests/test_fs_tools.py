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
