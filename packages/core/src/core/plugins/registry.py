"""Plugin registry: registration, lifecycle and contribution collection."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from core.config.schema import CoreConfig
from core.contracts.capability import Capability, CapabilityDescriptor
from core.contracts.group import Group
from core.contracts.interaction import InteractionProvider
from core.contracts.node import NodeContribution
from core.contracts.planning import Planner
from core.contracts.tool import ToolContract
from core.errors import (
    AmbiguousCapabilityError,
    CapabilityError,
    DuplicateCapabilityError,
    DuplicateGroupError,
    DuplicatePluginError,
    InvalidPluginError,
)
from core.events.bus import EventBus, Subscription
from core.events.event import Event
from core.events.types import CoreEvents
from core.plugins.base import Plugin, PluginMetadata
from core.plugins.context import PluginContext

CapabilityKey = tuple[str, str]


class PluginRegistry:
    """Holds plugins, drives their lifecycle and indexes their capabilities.

    Responsibilities:

    * ``register``/``extend`` — validate and store plugin instances.
    * ``load`` (via ``register``) / ``initialize`` / ``shutdown`` — run the
      lifecycle hooks and wire the event handlers declared by each plugin.
    * ``register_capability`` + ``capabilities``/``capability``/``default_capability``
      — register and query capabilities contributed by plugins.
    * ``collect_*`` — aggregate the declarative contributions (tools/nodes).

    The registry itself is agnostic of LangGraph: it only collects declarative
    descriptions and providers, which the runtime materializes.
    """

    def __init__(
        self,
        *,
        config: CoreConfig,
        events: EventBus,
        interaction: InteractionProvider | None = None,
    ) -> None:
        self._config = config
        self._events = events
        self._interaction = interaction
        self._plugins: dict[str, Plugin] = {}
        self._contexts: dict[str, PluginContext] = {}
        self._subscriptions: dict[str, list[Subscription]] = {}
        self._active_order: list[str] = []
        self._capabilities: dict[CapabilityKey, Capability] = {}
        self._capability_order: list[CapabilityKey] = []
        self._capabilities_by_plugin: dict[str, list[CapabilityKey]] = {}
        self._explicit_defaults: set[CapabilityKey] = set()
        self._groups: dict[str, Group] = {}
        self._group_order: list[str] = []
        self._groups_by_plugin: dict[str, list[str]] = {}

    @property
    def config(self) -> CoreConfig:
        """The configuration this registry operates against."""
        return self._config

    @property
    def events(self) -> EventBus:
        """The event bus plugins publish and subscribe on."""
        return self._events

    @property
    def interaction(self) -> InteractionProvider | None:
        """Host-provided interaction mechanism, if any."""
        return self._interaction

    def register(self, plugin: Plugin) -> None:
        """Store ``plugin``, rejecting invalid ids and duplicates.

        Calls ``plugin.load()`` once, before the plugin is stored or receives a
        context. Raises ``InvalidPluginError`` for objects that are not plugins
        or have an empty id, and ``DuplicatePluginError`` for repeated ids.
        """
        if not isinstance(plugin, Plugin):
            raise InvalidPluginError("plugin must be a Plugin instance")
        if not plugin.id:
            raise InvalidPluginError("plugin.id must be a non-empty string")
        if plugin.id in self._plugins:
            raise DuplicatePluginError(f"a plugin with id {plugin.id!r} is already registered")
        plugin.load()
        self._plugins[plugin.id] = plugin

    def extend(self, plugins: Iterable[Plugin]) -> None:
        """Register many plugins in order."""
        for plugin in plugins:
            self.register(plugin)

    def get(self, plugin_id: str) -> Plugin | None:
        """Return the registered plugin with ``plugin_id``, if any."""
        return self._plugins.get(plugin_id)

    def metadata(self, plugin_id: str) -> PluginMetadata | None:
        """Return the metadata of ``plugin_id``, if registered."""
        plugin = self._plugins.get(plugin_id)
        return plugin.metadata() if plugin is not None else None

    def context(self, plugin_id: str) -> PluginContext | None:
        """Return the active context for ``plugin_id``, if activated."""
        return self._contexts.get(plugin_id)

    def is_active(self, plugin_id: str) -> bool:
        return plugin_id in self._active_order

    def __contains__(self, plugin_id: object) -> bool:
        return plugin_id in self._plugins

    def __iter__(self) -> Iterable[Plugin]:
        return iter(self._plugins.values())

    def __len__(self) -> int:
        return len(self._plugins)

    def activate_all(self) -> None:
        """Activate every registered plugin in registration order.

        For each plugin: declared event handlers are subscribed, ``initialize``
        runs (with the plugin context), capabilities from
        ``declare_capabilities`` are registered, then ``plugin.activated`` fires.
        """
        for plugin_id, plugin in self._plugins.items():
            subscriptions = [
                self._events.subscribe(event_type, handler)
                for event_type, handler in plugin.event_handlers().items()
            ]
            self._subscriptions[plugin_id] = subscriptions

            for group in plugin.declare_groups():
                self._add_group(group, plugin_id=plugin_id)

            context = PluginContext(
                plugin_id=plugin_id,
                config=self._config.slot(plugin_id),
                events=self._events,
                registry=self,
                interaction=self._interaction,
            )
            plugin.initialize(context)
            for capability in plugin.declare_capabilities():
                self._add_capability(capability, plugin_id=plugin_id)
            self._contexts[plugin_id] = context
            self._active_order.append(plugin_id)

            self._events.publish(Event[object](
                type=CoreEvents.PLUGIN_ACTIVATED,
                source=plugin_id,
                payload={"version": plugin.version},
            ))

    def deactivate_all(self) -> None:
        """Deactivate plugins in reverse activation order and remove handlers.

        ``shutdown`` runs first, then the plugin's capabilities and event handlers
        are removed and ``plugin.deactivated`` fires.
        """
        for plugin_id in reversed(self._active_order):
            plugin = self._plugins[plugin_id]
            plugin.shutdown()
            self._remove_capabilities(plugin_id)
            self._remove_groups(plugin_id)
            for subscription in self._subscriptions.pop(plugin_id, ()):
                self._events.unsubscribe(subscription)
            self._contexts.pop(plugin_id, None)

            self._events.publish(Event[object](
                type=CoreEvents.PLUGIN_DEACTIVATED,
                source=plugin_id,
                payload={"version": plugin.version},
            ))
        self._active_order.clear()

    def register_capability(self, capability: Capability) -> Capability:
        """Register ``capability`` and return it.

        Raises:
            CapabilityError: if it is not a capability or has an empty name.
            DuplicateCapabilityError: if its ``(kind, name)`` is already taken.
        """
        self._add_capability(capability, plugin_id=None)
        return capability

    def capabilities(self, kind: type[Any] | str) -> list[Capability]:
        """Return the registered capabilities of ``kind`` (contract type or name)."""
        return self._filter_capabilities(kind)

    def capability(self, kind: type[Any] | str, name: str) -> Capability | None:
        """Return the capability of ``kind`` named ``name``, if registered."""
        for capability in self._filter_capabilities(kind):
            if capability.name == name:
                return capability
        return None

    def has_capability(self, kind: type[Any] | str) -> bool:
        """Whether at least one capability of ``kind`` is registered."""
        return bool(self._filter_capabilities(kind))

    def capability_names(self, kind: type[Any] | str) -> list[str]:
        """Names of the registered capabilities of ``kind``."""
        return [capability.name for capability in self._filter_capabilities(kind)]

    def capability_kinds(self) -> list[str]:
        """Sorted ``kind`` values of all registered capabilities."""
        return sorted({capability.kind for capability in self._capabilities.values()})

    def capability_descriptors(
        self,
        kind: type[Any] | str | None = None,
        group: str | None = None,
    ) -> list[CapabilityDescriptor]:
        """Descriptors of the registered capabilities, optionally filtered.

        Descriptors carry only descriptive information, so a planner or any other
        consumer can reason about capabilities without receiving the
        implementations.
        """
        capabilities = (
            list(self._capabilities.values())
            if kind is None
            else self._filter_capabilities(kind)
        )
        if group is not None:
            capabilities = [cap for cap in capabilities if group in cap.groups]
        return [capability.describe() for capability in capabilities]

    # -- groups --------------------------------------------------------------

    def groups(self) -> list[Group]:
        """Declared groups, in declaration order."""
        return [self._groups[group_id] for group_id in self._group_order]

    def group(self, group_id: str) -> Group | None:
        """Return the declared group with ``group_id``, if any."""
        return self._groups.get(group_id)

    def group_ids(self) -> list[str]:
        """Ids of the declared groups, in declaration order."""
        return list(self._group_order)

    def capabilities_in_group(self, group_id: str) -> list[Capability]:
        """Capabilities that belong to ``group_id`` (declared or implicit)."""
        return [
            capability
            for capability in self._capabilities.values()
            if group_id in capability.groups
        ]

    def capability_descriptors_in_group(
        self, group_id: str
    ) -> list[CapabilityDescriptor]:
        """Descriptors of the capabilities that belong to ``group_id``."""
        return [cap.describe() for cap in self.capabilities_in_group(group_id)]

    def plugin_groups(self, plugin_id: str) -> list[str]:
        """Groups a plugin belongs to (explicit plus its capabilities')."""
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return []
        result: set[str] = set(plugin.groups)
        for key in self._capabilities_by_plugin.get(plugin_id, ()):
            capability = self._capabilities.get(key)
            if capability is not None:
                result.update(capability.groups)
        return sorted(result)

    def plugin_ids_in_group(self, group_id: str) -> list[str]:
        """Ids of the plugins that belong to ``group_id``."""
        return [
            plugin_id
            for plugin_id in self._plugins
            if group_id in self.plugin_groups(plugin_id)
        ]

    # -- planners ------------------------------------------------------------

    def planners(self, group: str | None = None) -> list[Planner]:
        """Registered planners, optionally restricted to ``group``.

        A planner with no groups is global; a planner with groups is specialized.
        """
        planners = [
            capability
            for capability in self._capabilities.values()
            if isinstance(capability, Planner)
        ]
        if group is not None:
            planners = [planner for planner in planners if group in planner.groups]
        return planners

    def planner_descriptors(
        self, group: str | None = None
    ) -> list[CapabilityDescriptor]:
        """Descriptors of the registered planners, optionally restricted."""
        return [planner.describe() for planner in self.planners(group)]

    def default_capability(self, kind: type[Any]) -> Capability | None:
        """Resolve the default provider of ``kind``.

        Resolution order:

        1. ``CoreConfig.defaults`` (keyed by ``kind.kind`` or class name);
        2. the provider flagged with ``default = True``;
        3. the only provider, when exactly one is registered.

        Returns ``None`` when no provider is registered. Raises
        :class:`AmbiguousCapabilityError` when several providers exist and none
        was selected, and :class:`CapabilityError` when the configured default
        does not match a registered provider.
        """
        providers = self.capabilities(kind)
        if not providers:
            return None

        configured = self._configured_default(kind)
        if configured is not None:
            for capability in providers:
                if capability.name == configured:
                    return capability
            raise CapabilityError(
                f"configured default {configured!r} for capability "
                f"{kind.kind!r} is not registered"
            )

        flagged = [cap for cap in providers if (cap.kind, cap.name) in self._explicit_defaults]
        if len(flagged) > 1:
            names = ", ".join(sorted(cap.name for cap in flagged))
            raise AmbiguousCapabilityError(
                f"multiple default providers for capability {kind.kind!r}: {names}"
            )
        if len(flagged) == 1:
            return flagged[0]
        if len(providers) == 1:
            return providers[0]

        names = ", ".join(sorted(cap.name for cap in providers))
        raise AmbiguousCapabilityError(
            f"no default provider configured for capability {kind.kind!r} "
            f"(available: {names})"
        )

    def collect_nodes(self) -> list[NodeContribution]:
        """Aggregate the node contributions of every registered plugin."""
        return [
            contribution
            for plugin in self._plugins.values()
            for contribution in plugin.declare_nodes()
        ]

    def collect_tools(self) -> list[ToolContract]:
        """Aggregate the tool contracts of every registered plugin."""
        return [
            contract
            for plugin in self._plugins.values()
            for contract in plugin.declare_tools()
        ]

    def _filter_capabilities(self, kind: type[Any] | str) -> list[Capability]:
        result: list[Capability] = []
        for key in list(self._capability_order):
            capability = self._capabilities[key]
            if isinstance(kind, str):
                if capability.kind == kind:
                    result.append(capability)
            elif isinstance(capability, kind):
                result.append(capability)
        return result

    def _add_capability(self, capability: Capability, *, plugin_id: str | None) -> None:
        if not isinstance(capability, Capability):
            raise CapabilityError("capability must be a Capability instance")
        if not capability.name:
            raise CapabilityError("capability.name must be a non-empty string")
        key: CapabilityKey = (capability.kind, capability.name)
        if key in self._capabilities:
            raise DuplicateCapabilityError(
                f"capability {capability.name!r} of kind {capability.kind!r} "
                "is already registered"
            )
        self._capabilities[key] = capability
        self._capability_order.append(key)
        if capability.default:
            self._explicit_defaults.add(key)
        if plugin_id is not None:
            self._capabilities_by_plugin.setdefault(plugin_id, []).append(key)

    def _remove_capabilities(self, plugin_id: str) -> None:
        for key in self._capabilities_by_plugin.pop(plugin_id, ()):
            self._capabilities.pop(key, None)
            self._explicit_defaults.discard(key)
            if key in self._capability_order:
                self._capability_order.remove(key)

    def _add_group(self, group: Group, *, plugin_id: str) -> None:
        if group.id in self._groups:
            raise DuplicateGroupError(f"group {group.id!r} is already declared")
        self._groups[group.id] = group
        self._group_order.append(group.id)
        self._groups_by_plugin.setdefault(plugin_id, []).append(group.id)

    def _remove_groups(self, plugin_id: str) -> None:
        for group_id in self._groups_by_plugin.pop(plugin_id, ()):
            self._groups.pop(group_id, None)
            if group_id in self._group_order:
                self._group_order.remove(group_id)

    def _configured_default(self, kind: type[Any]) -> str | None:
        defaults = self._config.defaults
        return defaults.get(kind.kind) or defaults.get(kind.__name__)
