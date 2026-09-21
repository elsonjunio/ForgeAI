"""OpenCode Go LLM provider (OpenAI-compatible chat completions).

Endpoint: ``{base_url}/chat/completions`` where the default base URL is
``https://opencode.ai/zen/go/v1``. Authentication uses
``Authorization: Bearer $OPENCODE_API_KEY``.

The API follows the OpenAI chat-completions format for coding models (e.g.
``deepseek-v4.1-flash``). This provider maps :class:`core.Message` to the wire
format, supports optional SSE streaming via the observational ``on_chunk``
callback, and reports token usage when available.

It also sends a custom ``User-Agent`` and a stable ``x-opencode-session`` header,
as recommended by the OpenCode Go docs for routing/prompt caching.

Only models served over ``chat/completions`` are supported; some OpenCode Go
models use other dialects (``/v1/messages`` or ``/v1/responses``).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from typing import Any

import httpx

from core import (
    CoreError,
    LLMChunk,
    LLMChunkCallback,
    LLMProvider,
    LLMResponse,
    LLMUsage,
    Message,
)

DEFAULT_BASE_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_USER_AGENT = "forgeai-core-agent/0.1.0"
DEFAULT_TIMEOUT = 60.0


class OpenCodeGoError(CoreError):
    """Raised when the OpenCode Go API cannot be used or returns an error."""


class OpenCodeGoLLM(LLMProvider):
    """LLM provider backed by the OpenCode Go API.

    Args:
        model: model id (e.g. ``deepseek-v4.1-flash``).
        api_key: OpenCode API key. When empty, ``complete`` raises a clear error.
        base_url: API base URL (without the trailing ``/chat/completions``).
        timeout: HTTP timeout in seconds.
        session_id: stable session id sent as ``x-opencode-session``; a random
            one is generated when omitted.
        user_agent: custom User-Agent (the docs recommend not using a generic one).
        reasoning_effort: optional reasoning effort (``low``/``high``/``max``).
        client: optional pre-built ``httpx.Client`` (used by tests).
    """

    groups = ("llm",)

    def __init__(
        self,
        *,
        model: str,
        api_key: str = "",
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        session_id: str | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        reasoning_effort: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._session_id = session_id or uuid.uuid4().hex
        self._user_agent = user_agent
        self._reasoning_effort = reasoning_effort
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    @property
    def name(self) -> str:
        return "opencode-go"

    def close(self) -> None:
        """Close the underlying HTTP client when this provider owns it."""
        if self._owns_client:
            self._client.close()

    def complete(
        self,
        messages: Sequence[Message],
        *,
        on_chunk: LLMChunkCallback | None = None,
        **options: Any,
    ) -> LLMResponse:
        """Call ``chat/completions`` and return the accumulated response."""
        if not self._api_key:
            raise OpenCodeGoError(
                "missing OpenCode API key: set OPENCODE_API_KEY or the plugin's "
                "settings.api_key"
            )

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [self._to_wire(message) for message in messages],
        }
        if self._reasoning_effort is not None:
            payload["reasoning_effort"] = self._reasoning_effort
        payload.update(options)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": self._user_agent,
            "x-opencode-session": self._session_id,
        }
        url = f"{self._base_url}/chat/completions"

        if on_chunk is not None:
            payload["stream"] = True
            return self._complete_streaming(url, payload, headers, on_chunk)
        return self._complete_once(url, payload, headers)

    def _complete_once(
        self, url: str, payload: dict[str, Any], headers: dict[str, str]
    ) -> LLMResponse:
        try:
            response = self._client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise OpenCodeGoError(f"request to OpenCode Go failed: {exc}") from exc
        self._raise_for_status(response)
        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        return LLMResponse(
            message=Message(role="assistant", content=content),
            usage=self._usage(data.get("usage")),
            metadata={
                "model": data.get("model", self._model),
                "finish_reason": choice.get("finish_reason"),
            },
        )

    def _complete_streaming(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        on_chunk: LLMChunkCallback,
    ) -> LLMResponse:
        parts: list[str] = []
        usage: LLMUsage | None = None
        finish_reason: str | None = None
        try:
            with self._client.stream(
                "POST", url, json=payload, headers=headers
            ) as response:
                if response.status_code >= 400:
                    body = response.read().decode("utf-8", "replace")
                    raise OpenCodeGoError(
                        f"OpenCode Go returned HTTP {response.status_code}: {body}"
                    )
                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        line = line[len("data:") :].strip()
                    if line == "[DONE]":
                        break
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("usage"):
                        usage = self._usage(chunk["usage"])
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta") or {}
                        piece = delta.get("content")
                        if piece:
                            parts.append(piece)
                            on_chunk(LLMChunk(content=piece, index=len(parts) - 1))
                        if choice.get("finish_reason"):
                            finish_reason = choice["finish_reason"]
        except httpx.HTTPError as exc:
            raise OpenCodeGoError(f"request to OpenCode Go failed: {exc}") from exc

        return LLMResponse(
            message=Message(role="assistant", content="".join(parts)),
            usage=usage,
            metadata={"model": self._model, "finish_reason": finish_reason},
        )

    @staticmethod
    def _usage(raw: Any) -> LLMUsage | None:
        if not raw:
            return None
        return LLMUsage(
            prompt_tokens=raw.get("prompt_tokens"),
            completion_tokens=raw.get("completion_tokens"),
            total_tokens=raw.get("total_tokens"),
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise OpenCodeGoError(
                f"OpenCode Go returned HTTP {response.status_code}: {response.text}"
            )

    @staticmethod
    def _to_wire(message: Message) -> dict[str, Any]:
        wire: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.name:
            wire["name"] = message.name
        if message.tool_call_id:
            wire["tool_call_id"] = message.tool_call_id
        return wire
