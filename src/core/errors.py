"""Domain exceptions for the core framework."""

from __future__ import annotations


class CoreError(Exception):
    """Base error for every failure raised by the core framework."""


class PluginError(CoreError):
    """Base error for plugin registration and lifecycle failures."""


class DuplicatePluginError(PluginError):
    """Raised when a plugin id is registered more than once."""


class InvalidPluginError(PluginError):
    """Raised when a plugin does not satisfy the plugin contract."""


class InvalidGraphError(CoreError):
    """Raised when the contributed nodes cannot form a valid graph."""


class ConfigError(CoreError):
    """Raised when a configuration cannot be loaded or validated."""


class CapabilityError(CoreError):
    """Base error for capability registration and lookup failures."""


class DuplicateCapabilityError(CapabilityError):
    """Raised when a capability with the same kind and name is registered twice."""


class AmbiguousCapabilityError(CapabilityError):
    """Raised when a default provider cannot be resolved unambiguously."""


class DiscoveryError(PluginError):
    """Raised when a plugin cannot be discovered or materialized."""