"""Date helpers for dashboard artifact windows."""

from collections.abc import Iterable
from datetime import datetime, timedelta

from load_data_modules.types import Row


def _latest_date_from_rows(*row_groups: Iterable[Row]) -> str:
    """Return the latest non-empty ``ts`` value across row collections."""
    dates = [
        row.get("ts", "")
        for rows in row_groups
        for row in rows
        if row.get("ts")
    ]
    return max(dates) if dates else ""


def _window_cutoff(latest_ts: str, recent_days: int | None) -> str | None:
    """Return the inclusive ISO date cutoff for a trailing window."""
    if not latest_ts or not recent_days:
        return None
    latest_date = datetime.strptime(latest_ts, "%Y-%m-%d").date()
    return (latest_date - timedelta(days=recent_days - 1)).isoformat()
