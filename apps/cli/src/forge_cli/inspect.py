"""Formatting helpers for inspecting the plugin registry."""

from __future__ import annotations

from core import LLMProvider, PluginRegistry


def _join(values: list[str]) -> str:
    return ", ".join(values) if values else "-"


def format_plugins(registry: PluginRegistry) -> list[str]:
    """One line per registered plugin."""
    lines: list[str] = []
    for plugin in registry:
        metadata = plugin.metadata()
        groups = _join(registry.plugin_groups(metadata.id))
        lines.append(
            f"{metadata.id}  v{metadata.version}  groups=[{groups}]  "
            f"{metadata.description}"
        )
    return lines or ["(nenhum plugin registrado)"]


def format_capabilities(registry: PluginRegistry, kind: str | None = None) -> list[str]:
    """One line per capability, optionally filtered by ``kind``."""
    lines = [
        f"{descriptor.id}  groups=[{_join(list(descriptor.groups))}]  "
        f"{descriptor.description}"
        for descriptor in registry.capability_descriptors(kind)
    ]
    return lines or ["(nenhuma capability registrada)"]


def format_groups(registry: PluginRegistry) -> list[str]:
    """One line per declared group, with members."""
    lines: list[str] = []
    for group in registry.groups():
        capabilities = _join(
            [cap.name for cap in registry.capabilities_in_group(group.id)]
        )
        plugins = _join(registry.plugin_ids_in_group(group.id))
        lines.append(
            f"{group.id}  {group.name}  capabilities=[{capabilities}]  "
            f"plugins=[{plugins}]"
        )
    return lines or ["(nenhum grupo declarado)"]


def format_planners(registry: PluginRegistry, group: str | None = None) -> list[str]:
    """One line per planner, optionally restricted to ``group``."""
    lines: list[str] = []
    for planner in registry.planners(group):
        descriptor = planner.describe()
        scope = _join(list(descriptor.groups)) if descriptor.groups else "global"
        lines.append(f"{descriptor.id}  scope=[{scope}]")
    return lines or ["(nenhum planner registrado)"]


def format_providers(registry: PluginRegistry) -> list[str]:
    """One line per LLM provider, marking the default."""
    providers = registry.capabilities(LLMProvider)
    default = registry.default_capability(LLMProvider)
    lines = [
        f"{provider.name}{'  (default)' if provider is default else ''}"
        for provider in providers
    ]
    return lines or ["(nenhum LLMProvider registrado)"]
