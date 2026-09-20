"""Interaction contract: how the runtime asks the host for input/authorization.

The core never implements a CLI or any UI. It only defines the request/response
shapes and the provider protocol; the host (terminal, web UI, IDE, an automated
approver, ...) supplies an implementation when it wants interactive behavior.

Typical uses: confirm a destructive operation, request missing information,
authorize an action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class InteractionRequest(BaseModel):
    """A request for interaction sent to the host.

    Args:
        kind: nature of the interaction (``"confirm"``, ``"input"``,
            ``"authorization"``, ...).
        message: prompt shown to the user/application.
        options: allowed answers, when the interaction is a choice.
        default: suggested/default answer.
        metadata: free-form data for the host.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = "input"
    message: str
    options: tuple[str, ...] = ()
    default: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class InteractionResponse:
    """The host's answer.

    Args:
        value: free-form value (for ``input`` interactions).
        approved: authorization/confirmation result, when applicable.
        cancelled: whether the interaction was dismissed.
        metadata: free-form data from the host.
    """

    value: str | None = None
    approved: bool | None = None
    cancelled: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class InteractionProvider(Protocol):
    """Structural contract for host-side interaction. Not a capability."""

    def request(self, request: InteractionRequest) -> InteractionResponse:
        ...
