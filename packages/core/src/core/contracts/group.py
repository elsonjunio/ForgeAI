"""Group contract: declarative, many-to-many grouping of capabilities.

A group is a named domain area (``code``, ``filesystem``, ``version-control``,
...). Capabilities and plugins associate with groups by **reference** (ids), and
an item may belong to several groups. Groups are declared by plugins via
``Plugin.declare_groups()``; a group id may also be used without a declaration
(implicit group), in which case it simply has no description.

This is intentionally not ``plugin.group = "code"``: association is a set of
references, not a single field.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Group(BaseModel):
    """A named domain area that capabilities/plugins can belong to.

    Args:
        id: stable identifier referenced by capabilities/plugins.
        name: human-readable name (defaults to ``id`` when omitted).
        description: what the group represents.
        metadata: free-form data (owner, docs, ...).
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = ""
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
