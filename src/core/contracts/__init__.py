"""Contracts: pure interfaces and declarative models for extending the core."""

from core.contracts.analyzer import AnalysisResult, CodeAnalyzer
from core.contracts.capability import Capability
from core.contracts.discovery import Discoverer
from core.contracts.llm import LLMProvider
from core.contracts.node import AgentNode, NodeContract, NodeContribution
from core.contracts.plugin import PluginMetadata
from core.contracts.registry import CapabilitySource
from core.contracts.tool import Tool, ToolContract, ToolResult
from core.contracts.validator import ValidationInput, ValidationResult, Validator

__all__ = [
    "AgentNode",
    "AnalysisResult",
    "Capability",
    "CapabilitySource",
    "CodeAnalyzer",
    "Discoverer",
    "LLMProvider",
    "NodeContract",
    "NodeContribution",
    "PluginMetadata",
    "Tool",
    "ToolContract",
    "ToolResult",
    "ValidationInput",
    "ValidationResult",
    "Validator",
]
