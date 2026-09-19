from __future__ import annotations

import core


def test_all_public_names_resolve() -> None:
    missing = [name for name in core.__all__ if not hasattr(core, name)]
    assert missing == []


def test_all_names_are_unique() -> None:
    assert len(core.__all__) == len(set(core.__all__))
