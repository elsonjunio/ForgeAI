"""core — extensible core framework for Code Agents.

The public API is intentionally small and stable:

    - state:        AgentState, Message
    - runtime:      AgentRuntime, build_core, CoreContainer
    - extension:    Plugin, PluginContext, PluginRegistry
    - events:       Event, EventBus, CoreEvents, EventHandler
    - config:       CoreConfig, LangGraphOptions, PluginSlot, load_config
    - contracts:    ToolContract, NodeContract, NodeContribution, AgentNode

The core ships no LLM provider and no concrete tool; everything is contributed
by plugins. With zero plugins the framework still builds and runs.
"""

from __future__ import annotations

from core.agent.runtime import AgentRuntime
from core.agent.state import AgentState, AgentStatus, Message
from core.config.loader import load_config
from core.config.schema import CoreConfig, LangGraphOptions, PluginSlot
from core.contracts.node import AgentNode, NodeContract, NodeContribution
from core.contracts.tool import ToolContract
from core.errors import (
    ConfigError,
    CoreError,
    DuplicatePluginError,
    InvalidGraphError,
    InvalidPluginError,
    PluginError,
)
from core.events.bus import EventBus, Subscription
from core.events.event import Event
from core.events.types import CoreEvents, EventHandler
from core.plugins.base import Plugin
from core.plugins.context import PluginContext
from core.plugins.registry import PluginRegistry
from core.runtime.bootstrap import build_core
from core.runtime.container import CoreContainer
from core.version import VERSION as __version__

__all__ = [
    "AgentNode",
    "AgentRuntime",
    "AgentState",
    "AgentStatus",
    "ConfigError",
    "CoreConfig",
    "CoreContainer",
    "CoreError",
    "CoreEvents",
    "DuplicatePluginError",
    "Event",
    "EventBus",
    "EventHandler",
    "InvalidGraphError",
    "InvalidPluginError",
    "LangGraphOptions",
    "Message",
    "NodeContract",
    "NodeContribution",
    "Plugin",
    "PluginContext",
    "PluginError",
    "PluginRegistry",
    "PluginSlot",
    "Subscription",
    "ToolContract",
    "build_core",
    "load_config",
    "__version__",
]