"""Filesystem tools plugin for ``core-agent``."""

from code_agent_plugin_filesystem.paths import PathSecurityError, resolve_path
from code_agent_plugin_filesystem.plugin import FilesystemPlugin
from code_agent_plugin_filesystem.tools import (
    ListDirTool,
    ReadFileTool,
    StatTool,
    WriteFileTool,
)

__all__ = [
    "FilesystemPlugin",
    "ListDirTool",
    "PathSecurityError",
    "ReadFileTool",
    "StatTool",
    "WriteFileTool",
    "resolve_path",
]
