"""core — extensible core framework for Code Agents.

The public API is intentionally small and stable:

    - state:        AgentState, Message
    - runtime:      AgentRuntime, build_core, CoreContainer
    - extension:    Plugin, PluginMetadata, PluginContext, PluginRegistry
    - discovery:    Discoverer, EntryPointDiscoverer, discover_plugins
    - capabilities: Capability, LLMProvider, Tool, ToolResult, CodeAnalyzer
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
from core.contracts.analyzer import AnalysisResult, CodeAnalyzer
from core.contracts.capability import Capability
from core.contracts.discovery import Discoverer
from core.contracts.llm import LLMProvider
from core.contracts.node import AgentNode, NodeContract, NodeContribution
from core.contracts.tool import Tool, ToolContract, ToolResult
from core.errors import (
    AmbiguousCapabilityError,
    CapabilityError,
    ConfigError,
    CoreError,
    DiscoveryError,
    DuplicateCapabilityError,
    DuplicatePluginError,
    InvalidGraphError,
    InvalidPluginError,
    PluginError,
)
from core.events.bus import EventBus, Subscription
from core.events.event import Event
from core.events.types import CoreEvents, EventHandler
from core.plugins.base import Plugin, PluginMetadata
from core.plugins.context import PluginContext
from core.plugins.discovery import (
    DEFAULT_ENTRY_POINT_GROUP,
    EntryPointDiscoverer,
    discover_plugins,
)
from core.plugins.registry import PluginRegistry
from core.runtime.bootstrap import build_core
from core.runtime.container import CoreContainer
from core.version import VERSION as __version__

__all__ = [
    "DEFAULT_ENTRY_POINT_GROUP",
    "AgentNode",
    "AgentRuntime",
    "AgentState",
    "AgentStatus",
    "AmbiguousCapabilityError",
    "AnalysisResult",
    "Capability",
    "CapabilityError",
    "CodeAnalyzer",
    "ConfigError",
    "CoreConfig",
    "CoreContainer",
    "CoreError",
    "CoreEvents",
    "Discoverer",
    "DiscoveryError",
    "DuplicateCapabilityError",
    "DuplicatePluginError",
    "EntryPointDiscoverer",
    "Event",
    "EventBus",
    "EventHandler",
    "InvalidGraphError",
    "InvalidPluginError",
    "LLMProvider",
    "LangGraphOptions",
    "Message",
    "NodeContract",
    "NodeContribution",
    "Plugin",
    "PluginContext",
    "PluginError",
    "PluginMetadata",
    "PluginRegistry",
    "PluginSlot",
    "Subscription",
    "Tool",
    "ToolContract",
    "ToolResult",
    "build_core",
    "discover_plugins",
    "load_config",
    "__version__",
]
