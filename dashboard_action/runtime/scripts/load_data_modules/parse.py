"""Parsing helpers for artifact-backed CSV values."""

from typing import Any

from load_data_modules.types import Row


def _int_or_none(value: Any) -> int | None:
    """Return an integer for observed counter values, preserving missing data."""
    if value is None or value == "":
        return None
    return int(value)


def _bool_or_none(value: Any) -> bool | None:
    """Return a boolean when parseable, preserving missing values."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return None


def _counter_snapshot(row: Row, field: str) -> int:
    """Return a numeric counter value, normalizing unobserved data to zero."""
    value = _int_or_none(row.get(field))
    return value if value is not None else 0
