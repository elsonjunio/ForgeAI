"""The OpenCode Go plugin: exposes the LLM provider to the core."""

from __future__ import annotations

import os

from code_agent_plugin_opencode_go.provider import DEFAULT_BASE_URL, OpenCodeGoLLM
from core import Capability, Plugin, PluginContext

PLUGIN_ID = "code-agent-plugin-opencode-go"
DEFAULT_MODEL = "deepseek-v4.1-flash"


class OpenCodeGoPlugin(Plugin):
    """Contributes an :class:`OpenCodeGoLLM` provider.

    Settings (``CoreConfig.plugins["code-agent-plugin-opencode-go"].settings``):

    * ``model`` (default ``deepseek-v4.1-flash``)
    * ``api_key`` (default ``$OPENCODE_API_KEY``)
    * ``base_url`` (default ``https://opencode.ai/zen/go/v1``)
    * ``timeout`` (default ``60``)
    * ``session_id`` (default: generated per process)
    * ``reasoning_effort`` (optional: ``low``/``high``/``max``)
    """

    id = PLUGIN_ID
    version = "0.1.0"
    description = "LLM provider for the OpenCode Go API (OpenAI-compatible)."
    author = "ForgeAI"

    def __init__(self, *, model: str | None = None) -> None:
        self._model = model or DEFAULT_MODEL
        self._provider: OpenCodeGoLLM | None = None

    def initialize(self, context: PluginContext) -> None:
        self._provider = OpenCodeGoLLM(
            model=context.get_setting("model", self._model),
            api_key=context.get_setting(
                "api_key", os.environ.get("OPENCODE_API_KEY", "")
            ),
            base_url=context.get_setting("base_url", DEFAULT_BASE_URL),
            timeout=float(context.get_setting("timeout", 60.0)),
            session_id=context.get_setting("session_id"),
            reasoning_effort=context.get_setting("reasoning_effort"),
        )

    def shutdown(self) -> None:
        if self._provider is not None:
            self._provider.close()

    def declare_capabilities(self) -> list[Capability]:
        assert self._provider is not None
        return [self._provider]
