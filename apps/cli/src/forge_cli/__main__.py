"""Allow ``python -m forge_cli``."""

from __future__ import annotations

from forge_cli.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
