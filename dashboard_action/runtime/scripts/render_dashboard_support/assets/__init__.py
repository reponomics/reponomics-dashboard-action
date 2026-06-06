"""Static dashboard assets used by the runtime renderer."""

from __future__ import annotations

from importlib.resources import files


def load_asset(name: str) -> str:
    """Return a bundled static dashboard asset as UTF-8 text."""
    package = __package__ or __name__
    return (files(package) / "static" / name).read_text(encoding="utf-8")
