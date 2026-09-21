"""Safe path resolution within a configured root."""

from __future__ import annotations

from pathlib import Path

from core import CoreError


class PathSecurityError(CoreError):
    """Raised when a path escapes the allowed root."""


def resolve_path(root: Path, raw: str, *, allow_outside: bool = False) -> Path:
    """Resolve ``raw`` (relative to ``root``) and enforce containment.

    Args:
        root: the allowed base directory.
        raw: the path supplied by a plan node.
        allow_outside: when true, containment is not enforced.

    Raises:
        PathSecurityError: for an empty path or when the resolved path is
            outside ``root`` and ``allow_outside`` is false.
    """
    if not raw:
        raise PathSecurityError("path must be a non-empty string")
    candidate = Path(raw)
    resolved = (
        candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    )
    if allow_outside:
        return resolved
    root_resolved = root.resolve()
    if resolved != root_resolved and not resolved.is_relative_to(root_resolved):
        raise PathSecurityError(
            f"path {raw!r} resolves outside the allowed root {str(root_resolved)!r}"
        )
    return resolved
