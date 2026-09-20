"""Code analyzer contract.

Plugins contribute analyzers (linters, parsers, symbol indexers, ...). The core
only defines the interface and never ships an implementation.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.contracts.capability import Capability


@dataclass(frozen=True)
class AnalysisResult:
    """Outcome of a :class:`CodeAnalyzer` run.

    Args:
        findings: human-readable findings, in the analyzer's own format.
        metadata: free-form structured data (counts, rule ids, ...).
    """

    findings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


class CodeAnalyzer(Capability):
    """A source-code analyzer contributed by a plugin."""

    kind = "analyzer"

    @abstractmethod
    def analyze(self, source: str, *, path: str | None = None) -> AnalysisResult:
        """Analyze ``source`` and return the findings."""
        raise NotImplementedError
