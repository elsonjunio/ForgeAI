"""Complexity evaluator contract.

A complexity evaluator is a capability (``kind="complexity"``) contributed by a
plugin. It classifies a planning request so the application/planner can decide
the strategy (run directly, build a simple plan, build a complex graph, use
specialized planners, iterate, ...). The core defines the contract only; no
heuristic is implemented here.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.contracts.capability import Capability
from core.contracts.planning import PlanningRequest


class ComplexityLevel(str, Enum):
    """Coarse complexity buckets; plugins may extend via metadata."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


@dataclass(frozen=True)
class ComplexityAssessment:
    """Result of a complexity evaluation.

    Args:
        level: the assessed complexity.
        rationale: why the evaluator chose the level.
        metadata: free-form data (signals, scores, ...).
    """

    level: ComplexityLevel
    rationale: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ComplexityEvaluator(Capability):
    """A capability that classifies the complexity of a planning request."""

    kind = "complexity"

    @abstractmethod
    def evaluate(self, request: PlanningRequest) -> ComplexityAssessment:
        """Assess the complexity of ``request``."""
        raise NotImplementedError
