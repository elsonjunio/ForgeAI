"""Contracts: pure interfaces and declarative models for extending the core."""

from core.contracts.analyzer import AnalysisResult, CodeAnalyzer
from core.contracts.capability import Capability
from core.contracts.discovery import Discoverer
from core.contracts.llm import LLMProvider
from core.contracts.node import AgentNode, NodeContract, NodeContribution
from core.contracts.tool import Tool, ToolContract, ToolResult

__all__ = [
    "AgentNode",
    "AnalysisResult",
    "Capability",
    "CodeAnalyzer",
    "Discoverer",
    "LLMProvider",
    "NodeContract",
    "NodeContribution",
    "Tool",
    "ToolContract",
    "ToolResult",
]
