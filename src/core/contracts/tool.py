"""Tool contract: how plugins declare tool capabilities.

``ToolContract`` is a purely declarative descriptor. The core ships no concrete
tool and does not execute tools; it only knows how tools are *described* so the
future execution flow can materialize them from a provider.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolContract(BaseModel):
    """Declarative description of a tool a plugin offers.

    Args:
        name: stable, unique tool name.
        description: natural-language description used to advertise the tool.
        parameters: JSON-schema describing the expected arguments.
    """

    name: str = Field(min_length=1)
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)