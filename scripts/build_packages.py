#!/usr/bin/env python3
"""Build every package in the monorepo and zip its artifacts.

Discovers projects under ``packages/`` and ``apps/`` that have a
``pyproject.toml`` with both ``[build-system]`` and ``[project]``, builds a wheel
and an sdist for each (via ``python -m build``), and writes one zip per package
under the output directory. No package index (PyPI) is involved.

Usage::

    python scripts/build_packages.py --tag v0.1.0

Requires the ``build`` package (``pip install build``) and Python 3.11+ (or
``tomli`` on 3.10).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parent.parent
SEARCH_DIRS = ("packages", "apps")


@dataclass(frozen=True)
class Package:
    """A buildable project discovered in the monorepo."""

    name: str
    directory: Path


def discover_packages(root: Path = ROOT) -> list[Package]:
    """Return every project under ``packages/`` and ``apps/``."""
    packages: list[Package] = []
    for base in SEARCH_DIRS:
        for pyproject in sorted((root / base).rglob("pyproject.toml")):
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            project = data.get("project")
            if data.get("build-system") is None or project is None:
                continue
            packages.append(Package(name=str(project["name"]), directory=pyproject.parent))
    return packages


def build_package(package: Package, *, outdir: Path, tag: str) -> Path:
    """Build ``package`` and return the path to its zip archive."""
    artifact_dir = outdir / package.name
    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            str(package.directory),
            "--outdir",
            str(artifact_dir),
        ],
        check=True,
    )
    zip_path = outdir / f"{package.name}-{tag}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for artifact in sorted(artifact_dir.iterdir()):
            archive.write(artifact, arcname=artifact.name)
    return zip_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=ROOT / "dist")
    parser.add_argument("--tag", default="dev", help="suffix for the zip file names")
    args = parser.parse_args(argv)

    packages = discover_packages()
    if not packages:
        print("no packages found under packages/ or apps/", file=sys.stderr)
        return 1

    args.outdir.mkdir(parents=True, exist_ok=True)
    for package in packages:
        zip_path = build_package(package, outdir=args.outdir, tag=args.tag)
        print(f"built {package.name}: {zip_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
