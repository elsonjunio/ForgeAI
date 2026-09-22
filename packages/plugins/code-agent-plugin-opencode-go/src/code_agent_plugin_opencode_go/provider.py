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
import time
import uuid
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

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
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BASE_SECONDS = 0.5
DEFAULT_RETRY_MAX_SECONDS = 8.0

# Transient HTTP statuses worth retrying; other 4xx are not retried.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

_T = TypeVar("_T")


class _RetryableError(Exception):
    """Internal marker for a transient failure the provider should retry."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _retry_after(response: httpx.Response) -> float | None:
    """Parse a numeric ``Retry-After`` header (seconds), when present."""
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw.strip()))
    except ValueError:
        return None


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
        max_retries: retries for transient failures (timeouts, 429, 5xx).
        retry_base_seconds: base delay for exponential backoff.
        retry_max_seconds: cap for a single backoff delay.
        sleep: sleep function (injectable for tests).
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
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_base_seconds: float = DEFAULT_RETRY_BASE_SECONDS,
        retry_max_seconds: float = DEFAULT_RETRY_MAX_SECONDS,
        sleep: Callable[[float], None] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if retry_base_seconds < 0 or retry_max_seconds < 0:
            raise ValueError("retry delays must be >= 0")
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._session_id = session_id or uuid.uuid4().hex
        self._user_agent = user_agent
        self._reasoning_effort = reasoning_effort
        self._max_retries = max_retries
        self._retry_base_seconds = retry_base_seconds
        self._retry_max_seconds = retry_max_seconds
        self._sleep = sleep or time.sleep
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
        def attempt() -> LLMResponse:
            try:
                response = self._client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                raise _RetryableError(f"request failed: {exc}") from exc
            if response.status_code in _RETRYABLE_STATUS:
                raise _RetryableError(
                    f"HTTP {response.status_code}",
                    retry_after=_retry_after(response),
                )
            self._raise_for_status(response)
            return self._parse_once(response)

        return self._with_retries(attempt)

    def _parse_once(self, response: httpx.Response) -> LLMResponse:
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

        def attempt() -> None:
            nonlocal usage, finish_reason
            try:
                with self._client.stream(
                    "POST", url, json=payload, headers=headers
                ) as response:
                    if response.status_code in _RETRYABLE_STATUS:
                        raise _RetryableError(
                            f"HTTP {response.status_code}",
                            retry_after=_retry_after(response),
                        )
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
                                on_chunk(
                                    LLMChunk(content=piece, index=len(parts) - 1)
                                )
                            if choice.get("finish_reason"):
                                finish_reason = choice["finish_reason"]
            except httpx.HTTPError as exc:
                # Never retry once output has started: it would duplicate chunks.
                if parts:
                    raise OpenCodeGoError(
                        f"OpenCode Go stream failed after partial output: {exc}"
                    ) from exc
                raise _RetryableError(f"request failed: {exc}") from exc

        self._with_retries(attempt)
        return LLMResponse(
            message=Message(role="assistant", content="".join(parts)),
            usage=usage,
            metadata={"model": self._model, "finish_reason": finish_reason},
        )

    def _with_retries(self, operation: Callable[[], _T]) -> _T:
        """Run ``operation``, retrying transient failures with backoff."""
        attempt = 0
        while True:
            try:
                return operation()
            except _RetryableError as exc:
                if attempt >= self._max_retries:
                    raise OpenCodeGoError(
                        f"request to OpenCode Go failed after "
                        f"{attempt + 1} attempt(s): {exc}"
                    ) from exc
                self._sleep(self._backoff_delay(attempt, exc.retry_after))
                attempt += 1

    def _backoff_delay(self, attempt: int, retry_after: float | None) -> float:
        base = float(self._retry_base_seconds) * (2**attempt)
        delay = max(base, retry_after or 0.0)
        return float(min(delay, self._retry_max_seconds))

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
