from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from code_agent_plugin_opencode_go import OpenCodeGoError, OpenCodeGoLLM
from core import LLMChunk, Message

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_complete_non_streaming() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4.1-flash",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "hi"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 2,
                    "total_tokens": 3,
                },
            },
        )

    provider = OpenCodeGoLLM(
        model="deepseek-v4.1-flash", api_key="secret", client=_client(handler)
    )
    response = provider.complete([Message(role="user", content="hello")])

    assert response.content == "hi"
    assert response.usage is not None
    assert response.usage.total_tokens == 3
    assert captured["url"] == "https://opencode.ai/zen/go/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer secret"
    assert "x-opencode-session" in captured["headers"]
    assert captured["body"]["messages"] == [{"role": "user", "content": "hello"}]
    assert "stream" not in captured["body"]


def test_complete_streaming_emits_chunks() -> None:
    sse = (
        'data: {"choices":[{"delta":{"content":"he"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"llo"},"finish_reason":"stop"}]}\n\n'
        'data: {"usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3}}\n\n'
        "data: [DONE]\n\n"
    )
    streamed: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        streamed["body"] = json.loads(request.content)
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=sse
        )

    provider = OpenCodeGoLLM(model="m", api_key="k", client=_client(handler))
    chunks: list[LLMChunk] = []
    response = provider.complete(
        [Message(role="user", content="x")], on_chunk=chunks.append
    )

    assert [chunk.content for chunk in chunks] == ["he", "llo"]
    assert response.content == "hello"
    assert response.usage is not None
    assert response.usage.total_tokens == 3
    assert streamed["body"]["stream"] is True


def test_http_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Missing API key."}})

    provider = OpenCodeGoLLM(model="m", api_key="k", client=_client(handler))
    with pytest.raises(OpenCodeGoError):
        provider.complete([Message(role="user", content="x")])


def test_missing_api_key_raises_clearly() -> None:
    provider = OpenCodeGoLLM(model="m")
    with pytest.raises(OpenCodeGoError):
        provider.complete([Message(role="user", content="x")])


def _ok_response() -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
    )


def test_retries_on_transient_status_then_succeeds() -> None:
    attempts = {"count": 0}
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(503, json={"error": "busy"})
        return _ok_response()

    provider = OpenCodeGoLLM(
        model="m", api_key="k", client=_client(handler), sleep=delays.append
    )
    response = provider.complete([Message(role="user", content="x")])

    assert response.content == "ok"
    assert attempts["count"] == 2
    assert delays == [0.5]


def test_retries_on_timeout_then_succeeds() -> None:
    attempts = {"count": 0}
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.TimeoutException("timeout")
        return _ok_response()

    provider = OpenCodeGoLLM(
        model="m", api_key="k", client=_client(handler), sleep=delays.append
    )
    response = provider.complete([Message(role="user", content="x")])

    assert response.content == "ok"
    assert attempts["count"] == 2
    assert delays == [0.5]


def test_honors_retry_after_header() -> None:
    attempts = {"count": 0}
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(429, headers={"retry-after": "2"}, json={})
        return _ok_response()

    provider = OpenCodeGoLLM(
        model="m", api_key="k", client=_client(handler), sleep=delays.append
    )
    provider.complete([Message(role="user", content="x")])

    assert delays == [2.0]


def test_does_not_retry_client_errors() -> None:
    attempts = {"count": 0}
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(400, json={"error": "bad"})

    provider = OpenCodeGoLLM(
        model="m", api_key="k", client=_client(handler), sleep=delays.append
    )
    with pytest.raises(OpenCodeGoError):
        provider.complete([Message(role="user", content="x")])

    assert attempts["count"] == 1
    assert delays == []


def test_retries_exhausted_raises() -> None:
    attempts = {"count": 0}
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(500, json={})

    provider = OpenCodeGoLLM(
        model="m",
        api_key="k",
        max_retries=1,
        client=_client(handler),
        sleep=delays.append,
    )
    with pytest.raises(OpenCodeGoError):
        provider.complete([Message(role="user", content="x")])

    assert attempts["count"] == 2
    assert delays == [0.5]


def test_streaming_retries_before_output() -> None:
    attempts = {"count": 0}
    delays: list[float] = []
    sse = 'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n'

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(503, json={})
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=sse
        )

    provider = OpenCodeGoLLM(
        model="m", api_key="k", client=_client(handler), sleep=delays.append
    )
    chunks: list[LLMChunk] = []
    response = provider.complete([Message(role="user", content="x")], on_chunk=chunks.append)

    assert response.content == "hi"
    assert attempts["count"] == 2
    assert delays == [0.5]
