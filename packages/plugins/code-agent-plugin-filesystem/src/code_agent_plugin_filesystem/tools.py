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
_MAX_HINT_ENTRIES = 20

# Path/shape errors a different plan (for example `fs.list_dir` first) can avoid.
_RECOVERABLE_OS_ERRORS = (FileNotFoundError, NotADirectoryError, IsADirectoryError)


def _closest_name(target: str, names: list[str]) -> str | None:
    """Return a near match for ``target`` among ``names``, when there is one."""
    lowered = target.lower()
    for name in names:
        if name.lower() == lowered:
            return name
    for name in names:
        other = name.lower()
        if other.startswith(lowered) or lowered.startswith(other):
            return name
    return None


def _path_hint(path: Path) -> str:
    """Describe what actually exists near ``path`` to guide the next plan."""
    directory = path if path.is_dir() else path.parent
    while not directory.exists() and directory != directory.parent:
        directory = directory.parent
    if not directory.is_dir():
        return ""
    try:
        names = sorted(entry.name for entry in directory.iterdir())
    except OSError:
        return ""
    listing = ", ".join(names[:_MAX_HINT_ENTRIES])
    if len(names) > _MAX_HINT_ENTRIES:
        listing += ", …"
    hint = f"directory {str(directory)!r} contains: {listing or '(empty)'}"
    suggestion = _closest_name(path.name, names)
    if suggestion is not None:
        hint += f"; did you mean {suggestion!r}?"
    return hint


def _failure_result(exc: OSError, *, path: Path | None = None) -> ToolResult:
    """Convert an OS error into a failed ``ToolResult`` with a recovery hint."""
    message = f"{type(exc).__name__}: {exc}"
    if path is not None:
        hint = _path_hint(path)
        if hint:
            message = f"{message}. {hint}"
    return ToolResult(
        output=message,
        is_error=True,
        recoverable=isinstance(exc, _RECOVERABLE_OS_ERRORS),
    )


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
            description=(
                "Read a UTF-8 text file, optionally truncated. Verify the path "
                "exists first (fs.stat) or discover it with fs.list_dir; never "
                "read an invented path."
            ),
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
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return _failure_result(exc, path=path)
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
            description=(
                "List directory entries, sorted; directories end with '/'. Use "
                "fs.list_dir to discover real file names before reading or writing."
            ),
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
        try:
            names = [
                f"{entry.name}/" if entry.is_dir() else entry.name
                for entry in sorted(path.iterdir(), key=lambda item: item.name)
            ]
        except OSError as exc:
            return _failure_result(exc, path=path)
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
            description=(
                "Report whether a path exists and its basic metadata. Verify a "
                "path (exists/is_file/is_dir) before reading it or writing into "
                "its directory."
            ),
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
    """Write a UTF-8 text file, asking for confirmation when required.

    Idempotent: writing identical content is a no-op, and ``dry_run`` reports
    what would change without touching disk or asking for confirmation.
    """

    @property
    def contract(self) -> ToolContract:
        return ToolContract(
            name="fs.write_file",
            description=(
                "Write a UTF-8 text file (creates directories optionally). "
                "Confirm the target directory exists (fs.stat/fs.list_dir) before "
                "writing; the resolved path is shown for confirmation. Writing "
                "identical content is a no-op; use dry_run to preview."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "create_dirs": {"type": "boolean"},
                    "dry_run": {
                        "type": "boolean",
                        "description": "Report the intended write without doing it.",
                    },
                },
                "required": ["path", "content"],
            },
        )

    def execute(self, request: NodeExecutionRequest) -> NodeResult:
        parameters = request.node.parameters
        path = self._path(parameters)
        content = str(parameters.get("content", ""))
        if parameters.get("dry_run"):
            return NodeResult.ok(
                request.node.id,
                output=self._dry_run_summary(path, content),
                path=str(path),
                dry_run=True,
            )
        if self._is_noop(path, content):
            return NodeResult.ok(
                request.node.id,
                output=f"unchanged: {path}",
                path=str(path),
                skipped=True,
            )
        if self._require_confirmation:
            provider = request.interaction or self._interaction
            if provider is None:
                return NodeResult.failed(
                    request.node.id,
                    "write requires confirmation but no InteractionProvider is configured",
                )
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

    def _is_noop(self, path: Path, content: str) -> bool:
        if not path.is_file():
            return False
        try:
            return path.read_text(encoding="utf-8", errors="replace") == content
        except OSError:
            return False

    def _dry_run_summary(self, path: Path, content: str) -> str:
        size = len(content.encode("utf-8"))
        if path.is_file():
            action = "update" if not self._is_noop(path, content) else "no-op"
        else:
            action = "create"
        return f"dry-run: would {action} {path} ({size} bytes)"

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        path = self._path(arguments)
        content = str(arguments.get("content", ""))
        try:
            if arguments.get("create_dirs"):
                path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            return _failure_result(exc, path=path)
        return ToolResult(
            output=f"wrote {len(content.encode('utf-8'))} bytes to {path}",
            metadata={"path": str(path)},
        )
