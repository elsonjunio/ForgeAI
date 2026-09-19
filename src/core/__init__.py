"""core — extensible core framework for Code Agents.

The public API is intentionally small and stable:

    - state:        AgentState, Message; WorkflowState and friends
    - runtime:      AgentRuntime, WorkflowRuntime, build_core, CoreContainer
    - extension:    Plugin, PluginMetadata, PluginContext, PluginRegistry
    - discovery:    Discoverer, EntryPointDiscoverer, discover_plugins
    - capabilities: Capability, LLMProvider, Tool, ToolResult, CodeAnalyzer,
                    Validator
    - events:       Event, EventBus, CoreEvents, WorkflowEvents, EventHandler
    - config:       CoreConfig, LangGraphOptions, WorkflowOptions, PluginSlot
    - contracts:    ToolContract, NodeContract, NodeContribution, AgentNode

The core ships no LLM provider and no concrete tool; everything is contributed
by plugins. With zero plugins the framework still builds and runs.
"""

from __future__ import annotations

from core.agent.runtime import AgentRuntime, WorkflowRuntime
from core.agent.state import AgentState, AgentStatus, Message
from core.agent.workflow import WorkflowContext
from core.agent.workflow_state import (
    DiscoveredContext,
    Plan,
    ReviewResult,
    Task,
    ValidationRecord,
    WorkflowError,
    WorkflowState,
    WorkflowStatus,
)
from core.config.loader import load_config
from core.config.schema import (
    CoreConfig,
    LangGraphOptions,
    PluginSlot,
    WorkflowOptions,
)
from core.contracts.analyzer import AnalysisResult, CodeAnalyzer
from core.contracts.capability import Capability
from core.contracts.discovery import Discoverer
from core.contracts.llm import LLMProvider
from core.contracts.node import AgentNode, NodeContract, NodeContribution
from core.contracts.tool import Tool, ToolContract, ToolResult
from core.contracts.validator import ValidationInput, ValidationResult, Validator
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
    MissingCapabilityError,
    PluginError,
)
from core.events.bus import EventBus, Subscription
from core.events.event import Event
from core.events.types import CoreEvents, EventHandler, WorkflowEvents
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
    "DiscoveredContext",
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
    "MissingCapabilityError",
    "NodeContract",
    "NodeContribution",
    "Plan",
    "Plugin",
    "PluginContext",
    "PluginError",
    "PluginMetadata",
    "PluginRegistry",
    "PluginSlot",
    "ReviewResult",
    "Subscription",
    "Task",
    "Tool",
    "ToolContract",
    "ToolResult",
    "ValidationInput",
    "ValidationRecord",
    "ValidationResult",
    "Validator",
    "WorkflowContext",
    "WorkflowError",
    "WorkflowEvents",
    "WorkflowOptions",
    "WorkflowRuntime",
    "WorkflowState",
    "WorkflowStatus",
    "build_core",
    "discover_plugins",
    "load_config",
    "__version__",
]
