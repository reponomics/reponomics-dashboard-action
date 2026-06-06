"""Date helpers for dashboard artifact windows."""

from datetime import datetime, timedelta


def _latest_date_from_rows(*row_groups):
    dates = [
        row.get("ts", "")
        for rows in row_groups
        for row in rows
        if row.get("ts")
    ]
    return max(dates) if dates else ""


def _window_cutoff(latest_ts, recent_days):
    if not latest_ts or not recent_days:
        return None
    latest_date = datetime.strptime(latest_ts, "%Y-%m-%d").date()
    return (latest_date - timedelta(days=recent_days - 1)).isoformat()
