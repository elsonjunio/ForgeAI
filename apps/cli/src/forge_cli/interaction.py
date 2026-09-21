"""Minimal host-side :class:`InteractionProvider` using stdin/stdout."""

from __future__ import annotations

from collections.abc import Callable

from core import InteractionRequest, InteractionResponse

_CONFIRM_KINDS = {"confirm", "authorization", "destructive"}
_AFFIRMATIVE = {"y", "yes", "s", "sim", "true", "1"}


class TerminalInteractionProvider:
    """Asks the user in the terminal; the core never knows about it.

    Args:
        input_fn: function used to read a line (defaults to :func:`input`).
        output_fn: function used to print the prompt (defaults to :func:`print`).
    """

    def __init__(
        self,
        *,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ) -> None:
        self._input = input_fn
        self._output = output_fn

    def request(self, request: InteractionRequest) -> InteractionResponse:
        prompt = request.message
        if request.options:
            prompt = f"{prompt} [{', '.join(request.options)}]"
        if request.default is not None:
            prompt = f"{prompt} (default: {request.default})"
        answer = self._input(f"{prompt} ").strip()
        if not answer and request.default is not None:
            answer = request.default
        if request.kind in _CONFIRM_KINDS:
            return InteractionResponse(
                value=answer, approved=answer.lower() in _AFFIRMATIVE
            )
        return InteractionResponse(value=answer)
