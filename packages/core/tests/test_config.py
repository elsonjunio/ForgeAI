from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.config.loader import load_config
from core.config.schema import CoreConfig, PluginSlot
from core.errors import ConfigError


def test_config_defaults() -> None:
    config = CoreConfig()
    assert config.app_name == "core-agent"
    assert config.version
    assert config.environment == "development"
    assert config.plugins == {}
    assert config.langgraph.recursion_limit == 25
    assert config.budgets.max_iterations == 5
    assert config.budgets.max_recoveries == 3
    assert config.budgets.max_nodes is None
    assert config.budgets.deadline_seconds is None
    assert config.budgets.max_total_tokens is None


def test_budgets_validate_bounds() -> None:
    from pydantic import ValidationError

    from core.config.schema import ExecutionBudgets

    budgets = ExecutionBudgets(max_iterations=2, max_nodes=4, deadline_seconds=1.5)
    assert budgets.max_iterations == 2
    assert budgets.max_nodes == 4
    assert budgets.deadline_seconds == 1.5

    with pytest.raises(ValidationError):
        ExecutionBudgets(max_iterations=0)
    with pytest.raises(ValidationError):
        ExecutionBudgets(max_recoveries=-1)
    with pytest.raises(ValidationError):
        ExecutionBudgets(deadline_seconds=0)


def test_load_config_reads_budgets() -> None:
    config = load_config({"budgets": {"max_iterations": 9, "max_nodes": 3}})
    assert config.budgets.max_iterations == 9
    assert config.budgets.max_nodes == 3


def test_load_config_from_mapping() -> None:
    config = load_config(
        {
            "environment": "test",
            "plugins": {"greet": {"enabled": True, "settings": {"lang": "pt"}}},
        }
    )
    assert config.environment == "test"
    assert config.plugins["greet"].settings == {"lang": "pt"}


def test_load_config_from_json_file(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "app_name": "my-app",
                "plugins": {"a": {"enabled": False}},
            }
        ),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.app_name == "my-app"
    assert config.plugins["a"].enabled is False


def test_load_config_none_returns_defaults() -> None:
    config = load_config()
    assert config == CoreConfig()


def test_load_config_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.json")


def test_load_config_raises_on_non_object_json(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_slot_defaults_when_missing() -> None:
    config = CoreConfig()
    slot = config.slot("unknown")
    assert isinstance(slot, PluginSlot)
    assert slot.enabled is True
    assert slot.settings == {}


def test_is_enabled_default_true_for_unknown_plugins() -> None:
    config = CoreConfig(plugins={"a": PluginSlot(enabled=False)})
    assert config.is_enabled("a") is False
    assert config.is_enabled("b") is True