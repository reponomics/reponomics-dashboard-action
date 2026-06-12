"""Shared repository path helpers for maintainer scripts."""

from __future__ import annotations

from pathlib import Path


PROJECT_MARKER = "pyproject.toml"


def find_repo_root(start: Path) -> Path:
    """Return the nearest ancestor containing the project marker."""
    resolved = start.resolve()
    if resolved.is_file():
        resolved = resolved.parent
    for path in (resolved, *resolved.parents):
        if (path / PROJECT_MARKER).is_file():
            return path
    raise RuntimeError(f"Could not find repository root containing {PROJECT_MARKER}")
