"""core — extensible core framework for Code Agents.

The public API is intentionally small and stable:

    - state:        AgentState, Message
    - runtime:      AgentRuntime, PlanExecutor, NodeRunner, GraphBuilder,
                    build_core
    - extension:    Plugin, PluginMetadata, PluginContext, PluginRegistry
    - discovery:    Discoverer, EntryPointDiscoverer, discover_plugins
    - capabilities: Capability, CapabilityDescriptor, LLMProvider, Tool,
                    CodeAnalyzer, Validator, Discoverer, Planner,
                    ComplexityEvaluator
    - execution:    ExecutionPlan, PlanNode, PlanEdge, ExecutionContext,
                    NodeResult, ExecutionControl, callbacks, InteractionProvider
    - groups:       Group
    - events:       Event, EventBus, CoreEvents, EventHandler
    - config:       CoreConfig, LangGraphOptions, PluginSlot

The core ships no LLM provider, no planner and no concrete tool; everything is
contributed by plugins. With zero plugins the framework still builds and runs.
"""

from __future__ import annotations

from core.agent.graph import GraphBuilder, NodeRunner, PlanExecutor
from core.agent.runtime import AgentRuntime
from core.agent.state import AgentState, AgentStatus, Message
from core.config.loader import load_config
from core.config.schema import CoreConfig, LangGraphOptions, PluginSlot
from core.contracts.analyzer import AnalysisResult, CodeAnalyzer
from core.contracts.callbacks import (
    ControlCallback,
    ExecutionEvent,
    ExecutionEventKind,
    ExecutionObserver,
)
from core.contracts.capability import Capability, CapabilityDescriptor
from core.contracts.complexity import (
    ComplexityAssessment,
    ComplexityEvaluator,
    ComplexityLevel,
)
from core.contracts.discovery import Discoverer
from core.contracts.execution import (
    ControlAction,
    Executable,
    ExecutionContext,
    ExecutionControl,
    ExecutionResult,
    NodeExecutionRequest,
    NodeResult,
)
from core.contracts.group import Group
from core.contracts.interaction import (
    InteractionProvider,
    InteractionRequest,
    InteractionResponse,
)
from core.contracts.llm import (
    LLMChunk,
    LLMChunkCallback,
    LLMProvider,
    LLMResponse,
    LLMUsage,
)
from core.contracts.node import AgentNode, NodeContract, NodeContribution
from core.contracts.plan import ExecutionPlan, PlanEdge, PlanNode
from core.contracts.planning import (
    Observation,
    Planner,
    PlanningRequest,
    PlanningResult,
)
from core.contracts.plugin import PluginMetadata
from core.contracts.registry import CapabilitySource
from core.contracts.tool import Tool, ToolContract, ToolResult
from core.contracts.validator import ValidationInput, ValidationResult, Validator
from core.errors import (
    AmbiguousCapabilityError,
    CapabilityError,
    ConfigError,
    CoreError,
    DiscoveryError,
    DuplicateCapabilityError,
    DuplicateGroupError,
    DuplicatePluginError,
    GraphBuildError,
    InvalidGraphError,
    InvalidPlanError,
    InvalidPluginError,
    MissingCapabilityError,
    PluginError,
    UnsupportedCapabilityError,
)
from core.events.bus import EventBus, Subscription
from core.events.event import Event
from core.events.types import CoreEvents, EventHandler
from core.plugins.base import Plugin
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
    "CapabilityDescriptor",
    "CapabilityError",
    "CapabilitySource",
    "CodeAnalyzer",
    "ComplexityAssessment",
    "ComplexityEvaluator",
    "ComplexityLevel",
    "ConfigError",
    "ControlAction",
    "ControlCallback",
    "CoreConfig",
    "CoreContainer",
    "CoreError",
    "CoreEvents",
    "Discoverer",
    "DiscoveryError",
    "DuplicateCapabilityError",
    "DuplicateGroupError",
    "DuplicatePluginError",
    "EntryPointDiscoverer",
    "Event",
    "EventBus",
    "EventHandler",
    "ExecutionContext",
    "ExecutionControl",
    "ExecutionEvent",
    "ExecutionEventKind",
    "ExecutionObserver",
    "ExecutionPlan",
    "ExecutionResult",
    "Executable",
    "GraphBuildError",
    "GraphBuilder",
    "Group",
    "InteractionProvider",
    "InteractionRequest",
    "InteractionResponse",
    "InvalidGraphError",
    "InvalidPlanError",
    "InvalidPluginError",
    "LLMChunk",
    "LLMChunkCallback",
    "LLMProvider",
    "LLMResponse",
    "LLMUsage",
    "LangGraphOptions",
    "Message",
    "MissingCapabilityError",
    "NodeContract",
    "NodeContribution",
    "NodeExecutionRequest",
    "NodeResult",
    "NodeRunner",
    "Observation",
    "PlanEdge",
    "PlanExecutor",
    "PlanNode",
    "Planner",
    "PlanningRequest",
    "PlanningResult",
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
    "UnsupportedCapabilityError",
    "ValidationInput",
    "ValidationResult",
    "Validator",
    "build_core",
    "discover_plugins",
    "load_config",
    "__version__",
]
