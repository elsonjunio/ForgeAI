"""Configuration package: schema and loading infrastructure."""

from core.config.loader import load_config
from core.config.schema import CoreConfig, LangGraphOptions, PluginSlot

__all__ = ["CoreConfig", "LangGraphOptions", "PluginSlot", "load_config"]