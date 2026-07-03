"""Collector exception types."""

from __future__ import annotations


class CollectionAbort(RuntimeError):
    """Intentional collector abort that should fail the action cleanly."""

    def __init__(self, message: str = "collection failed", *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code
