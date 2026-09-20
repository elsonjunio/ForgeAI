"""Plugins package: the extension mechanism of the core."""

from core.plugins.base import Plugin, PluginMetadata
from core.plugins.context import PluginContext
from core.plugins.discovery import (
    DEFAULT_ENTRY_POINT_GROUP,
    EntryPointDiscoverer,
    discover_plugins,
)
from core.plugins.registry import PluginRegistry

__all__ = [
    "DEFAULT_ENTRY_POINT_GROUP",
    "EntryPointDiscoverer",
    "Plugin",
    "PluginContext",
    "PluginMetadata",
    "PluginRegistry",
    "discover_plugins",
]
