"""Plugin metadata: identity, version and descriptive information.

This model lives in the contract layer so orchestration code can reference plugin
metadata without depending on the plugin implementation layer.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PluginMetadata(BaseModel):
    """Identity, version and descriptive information about a plugin.

    Args:
        id: stable identity, unique across loaded plugins.
        version: plugin version string.
        name: human-readable name (defaults to the class name).
        description: what the plugin does.
        author: plugin author or maintainer.
        homepage: project/documentation URL.
        tags: free-form labels for filtering.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    version: str = "0.0.0"
    name: str = ""
    description: str = ""
    author: str = ""
    homepage: str | None = None
    tags: tuple[str, ...] = ()
