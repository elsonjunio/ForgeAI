"""Filesystem tools exposed as core capabilities."""

from __future__ import annotations

import fnmatch
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from code_agent_plugin_filesystem.paths import resolve_path
from core import (
    InteractionRequest,
    NodeExecutionRequest,
    NodeResult,
    Tool,
    ToolContract,
    ToolResult,
)
from core.contracts.interaction import InteractionProvider

DEFAULT_MAX_READ_BYTES = 1_000_000


class _FilesystemTool(Tool):
    """Base for filesystem tools: shared root handling and group."""

    groups = ("filesystem",)

    def __init__(
        self,
        *,
        root: Path,
        allow_outside_root: bool = False,
        max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
        require_confirmation: bool = True,
        interaction: InteractionProvider | None = None,
    ) -> None:
        self._root = root
        self._allow_outside_root = allow_outside_root
        self._max_read_bytes = max_read_bytes
        self._require_confirmation = require_confirmation
        self._interaction = interaction

    def _path(self, arguments: Mapping[str, Any], key: str = "path") -> Path:
        return resolve_path(
            self._root,
            str(arguments.get(key, ".")),
            allow_outside=self._allow_outside_root,
        )


class ReadFileTool(_FilesystemTool):
    """Read a text file (truncated to ``max_bytes``)."""

    @property
    def contract(self) -> ToolContract:
        return ToolContract(
            name="fs.read_file",
            description="Read a UTF-8 text file, optionally truncated.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path."},
                    "max_bytes": {"type": "integer", "minimum": 1},
                },
                "required": ["path"],
            },
        )

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        path = self._path(arguments)
        max_bytes = int(arguments.get("max_bytes", self._max_read_bytes))
        text = path.read_text(encoding="utf-8", errors="replace")
        truncated = len(text) > max_bytes
        if truncated:
            text = text[:max_bytes]
        return ToolResult(
            output=text,
            metadata={"path": str(path), "truncated": truncated},
        )


class ListDirTool(_FilesystemTool):
    """List directory entries (optionally filtered by a glob pattern)."""

    @property
    def contract(self) -> ToolContract:
        return ToolContract(
            name="fs.list_dir",
            description="List directory entries, sorted; directories end with '/'.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path."},
                    "pattern": {"type": "string", "description": "Glob filter."},
                },
            },
        )

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        path = self._path(arguments)
        names = [
            f"{entry.name}/" if entry.is_dir() else entry.name
            for entry in sorted(path.iterdir(), key=lambda item: item.name)
        ]
        pattern = arguments.get("pattern")
        if pattern:
            names = [
                name
                for name in names
                if fnmatch.fnmatch(name.rstrip("/"), str(pattern))
            ]
        return ToolResult(
            output="\n".join(names),
            metadata={"path": str(path), "count": len(names)},
        )


class StatTool(_FilesystemTool):
    """Report basic metadata about a path."""

    @property
    def contract(self) -> ToolContract:
        return ToolContract(
            name="fs.stat",
            description="Report whether a path exists and its basic metadata.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        )

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        path = self._path(arguments)
        exists = path.exists()
        is_file = path.is_file() if exists else False
        data = {
            "exists": exists,
            "is_file": is_file,
            "is_dir": path.is_dir() if exists else False,
            "size": path.stat().st_size if is_file else None,
        }
        return ToolResult(output=json.dumps(data), metadata={"path": str(path)})


class WriteFileTool(_FilesystemTool):
    """Write a UTF-8 text file, asking for confirmation when required."""

    @property
    def contract(self) -> ToolContract:
        return ToolContract(
            name="fs.write_file",
            description="Write a UTF-8 text file (creates directories optionally).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "create_dirs": {"type": "boolean"},
                },
                "required": ["path", "content"],
            },
        )

    def execute(self, request: NodeExecutionRequest) -> NodeResult:
        if self._require_confirmation:
            provider = request.interaction or self._interaction
            if provider is None:
                return NodeResult.failed(
                    request.node.id,
                    "write requires confirmation but no InteractionProvider is configured",
                )
            path = self._path(request.node.parameters)
            response = provider.request(
                InteractionRequest(
                    kind="confirm",
                    message=f"Write to {path}?",
                    default="n",
                )
            )
            if not response.approved:
                return NodeResult.failed(request.node.id, "write not approved")
        return super().execute(request)

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        path = self._path(arguments)
        content = str(arguments.get("content", ""))
        if arguments.get("create_dirs"):
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ToolResult(
            output=f"wrote {len(content.encode('utf-8'))} bytes to {path}",
            metadata={"path": str(path)},
        )
