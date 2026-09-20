"""Configuration package: schema and loading infrastructure."""

from core.config.loader import load_config
from core.config.schema import CoreConfig, LangGraphOptions, PluginSlot, WorkflowOptions

__all__ = ["CoreConfig", "LangGraphOptions", "PluginSlot", "WorkflowOptions", "load_config"]