from __future__ import annotations

from pathlib import Path

from code_agent_plugin_filesystem import FilesystemPlugin
from core import CoreConfig, EventBus, Tool
from core.plugins.registry import PluginRegistry


def _registry(tmp_path: Path) -> PluginRegistry:
    config = CoreConfig.model_validate(
        {
            "plugins": {
                "code-agent-plugin-filesystem": {"settings": {"root": str(tmp_path)}}
            }
        }
    )
    registry = PluginRegistry(config=config, events=EventBus())
    registry.register(FilesystemPlugin())
    registry.activate_all()
    return registry


def test_plugin_registers_tools(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    try:
        assert registry.capability(Tool, "fs.read_file") is not None
        names = sorted(
            cap.name for cap in registry.capabilities_in_group("filesystem")
        )
        assert names == ["fs.list_dir", "fs.read_file", "fs.stat", "fs.write_file"]
    finally:
        registry.deactivate_all()
