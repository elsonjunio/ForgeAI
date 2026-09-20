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
