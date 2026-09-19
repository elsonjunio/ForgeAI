"""Plugins package: the extension mechanism of the core."""

from core.plugins.base import Plugin
from core.plugins.context import PluginContext
from core.plugins.registry import PluginRegistry

__all__ = ["Plugin", "PluginContext", "PluginRegistry"]