"""Contracts: pure interfaces and declarative models for extending the core."""

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
    merge_usage,
)
from core.contracts.node import AgentNode, NodeContract, NodeContribution
from core.contracts.plan import ExecutionPlan, PlanEdge, PlanNode
from core.contracts.planning import (
    CompactionRequest,
    Observation,
    Planner,
    PlanningRequest,
    PlanningResult,
)
from core.contracts.plugin import PluginMetadata
from core.contracts.registry import CapabilitySource
from core.contracts.synthesis import (
    Synthesis,
    SynthesisMode,
    SynthesisRequest,
    Synthesizer,
)
from core.contracts.tool import Tool, ToolContract, ToolResult
from core.contracts.validator import ValidationInput, ValidationResult, Validator

__all__ = [
    "AgentNode",
    "AnalysisResult",
    "Capability",
    "CapabilityDescriptor",
    "CapabilitySource",
    "CodeAnalyzer",
    "CompactionRequest",
    "ComplexityAssessment",
    "ComplexityEvaluator",
    "ComplexityLevel",
    "ControlAction",
    "ControlCallback",
    "Discoverer",
    "ExecutionContext",
    "ExecutionControl",
    "ExecutionEvent",
    "ExecutionEventKind",
    "ExecutionObserver",
    "ExecutionPlan",
    "ExecutionResult",
    "Executable",
    "Group",
    "InteractionProvider",
    "InteractionRequest",
    "InteractionResponse",
    "LLMChunk",
    "LLMChunkCallback",
    "LLMProvider",
    "LLMResponse",
    "LLMUsage",
    "merge_usage",
    "NodeContract",
    "NodeContribution",
    "NodeExecutionRequest",
    "NodeResult",
    "Observation",
    "PlanEdge",
    "PlanNode",
    "Planner",
    "PlanningRequest",
    "PlanningResult",
    "PluginMetadata",
    "Synthesis",
    "SynthesisMode",
    "SynthesisRequest",
    "Synthesizer",
    "Tool",
    "ToolContract",
    "ToolResult",
    "ValidationInput",
    "ValidationResult",
    "Validator",
]
