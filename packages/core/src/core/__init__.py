"""core — extensible core framework for Code Agents.

The public API is intentionally small and stable:

    - state:        AgentState, Message; WorkflowState and friends
    - runtime:      AgentRuntime, WorkflowRuntime, build_core, CoreContainer
    - extension:    Plugin, PluginMetadata, PluginContext, PluginRegistry
    - discovery:    Discoverer, EntryPointDiscoverer, discover_plugins
    - capabilities: Capability, CapabilityDescriptor, LLMProvider, Tool,
                    CodeAnalyzer, Validator, Planner
    - execution:    ExecutionPlan, PlanNode, PlanEdge, ExecutionContext,
                    NodeResult, ExecutionControl, callbacks, InteractionProvider
    - events:       Event, EventBus, CoreEvents, WorkflowEvents, EventHandler
    - config:       CoreConfig, LangGraphOptions, WorkflowOptions, PluginSlot
    - contracts:    ToolContract, NodeContract, NodeContribution, AgentNode

The core ships no LLM provider and no concrete tool; everything is contributed
by plugins. With zero plugins the framework still builds and runs.
"""

from __future__ import annotations

from core.agent.graph import GraphBuilder, PlanExecutor
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
from core.contracts.callbacks import (
    ControlCallback,
    ExecutionEvent,
    ExecutionEventKind,
    ExecutionObserver,
)
from core.contracts.capability import Capability, CapabilityDescriptor
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
from core.contracts.planning import Planner, PlanningRequest, PlanningResult
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
from core.events.types import CoreEvents, EventHandler, WorkflowEvents
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
    "ConfigError",
    "ControlAction",
    "ControlCallback",
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
    "Plan",
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
    "ReviewResult",
    "Subscription",
    "Task",
    "Tool",
    "ToolContract",
    "ToolResult",
    "UnsupportedCapabilityError",
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
