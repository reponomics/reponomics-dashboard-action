"""Parsing helpers for artifact-backed CSV values."""


def _int_or_none(value):
    """Return an integer for observed counter values, preserving missing data."""
    if value is None or value == "":
        return None
    return int(value)


def _bool_or_none(value):
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


def _counter_snapshot(row, field):
    value = _int_or_none(row.get(field))
    return value if value is not None else 0
