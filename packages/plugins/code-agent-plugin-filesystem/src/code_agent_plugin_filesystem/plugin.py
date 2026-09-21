"""The filesystem plugin: contributes filesystem tools to the core."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from code_agent_plugin_filesystem.tools import (
    ListDirTool,
    ReadFileTool,
    StatTool,
    WriteFileTool,
)
from core import Capability, Plugin, PluginContext

PLUGIN_ID = "code-agent-plugin-filesystem"


class FilesystemPlugin(Plugin):
    """Contributes ``fs.read_file``, ``fs.list_dir``, ``fs.stat`` and ``fs.write_file``.

    Settings (``CoreConfig.plugins["code-agent-plugin-filesystem"].settings``):

    * ``root`` (default: current working directory) — allowed base directory.
    * ``allow_outside_root`` (default ``False``) — disable containment checks.
    * ``max_read_bytes`` (default ``1_000_000``) — read truncation limit.
    * ``require_confirmation`` (default ``True``) — confirm writes via the
      ``InteractionProvider``.
    """

    id = PLUGIN_ID
    version = "0.1.0"
    description = "Filesystem tools (read/list/stat/write) for core-agent."
    author = "ForgeAI"

    def __init__(self, *, root: str | None = None) -> None:
        self._root = root
        self._tools: list[Capability] = []

    def initialize(self, context: PluginContext) -> None:
        root = Path(context.get_setting("root", self._root or os.getcwd()))
        allow_outside = bool(context.get_setting("allow_outside_root", False))
        max_read = int(context.get_setting("max_read_bytes", 1_000_000))
        require_confirmation = bool(context.get_setting("require_confirmation", True))
        common: dict[str, Any] = {
            "root": root,
            "allow_outside_root": allow_outside,
            "max_read_bytes": max_read,
        }
        self._tools = [
            ReadFileTool(**common),
            ListDirTool(**common),
            StatTool(**common),
            WriteFileTool(
                **common,
                require_confirmation=require_confirmation,
                interaction=context.interaction,
            ),
        ]

    def declare_capabilities(self) -> list[Capability]:
        return list(self._tools)
