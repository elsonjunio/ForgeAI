"""Configuration loading infrastructure.

Supported sources: ``None`` (all defaults), a mapping, or a path to a JSON file.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from os import PathLike
from pathlib import Path
from typing import Any

from core.config.schema import CoreConfig
from core.errors import ConfigError


def load_config(
    source: Mapping[str, Any] | str | PathLike[str] | None = None,
) -> CoreConfig:
    """Build a :class:`CoreConfig` from the given source.

    Args:
        source: a mapping, or a string/path to a JSON file. ``None`` yields
            the default configuration.

    Raises:
        ConfigError: if the source cannot be read or is not a valid object.
    """
    if source is None:
        return CoreConfig()
    if isinstance(source, Mapping):
        return CoreConfig.model_validate(dict(source))

    path = Path(source)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot load config from {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"config file {path} must contain a JSON object")
    return CoreConfig.model_validate(raw)