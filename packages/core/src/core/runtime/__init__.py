"""Runtime package: infrastructure that wires and serves the core.

This is the composition layer (``bootstrap``/``container``). The actual
execution engine — LangGraph — is encapsulated in ``core.agent.runtime``.
"""

from core.runtime.bootstrap import build_core
from core.runtime.container import CoreContainer

__all__ = ["CoreContainer", "build_core"]