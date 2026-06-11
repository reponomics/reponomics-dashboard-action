"""Data shaping for generated README SVG assets."""

from __future__ import annotations

from datetime import date, datetime, timedelta


def build_readme_asset_data(
    daily_rows: list[dict],
    per_repo: list[dict],
    totals: dict | None = None,
    traffic_reporting: dict | None = None,
) -> dict:
    """Build chart-ready data for README SVG assets."""
    daily_by_date: dict[str, int] = {}
    for row in daily_rows:
        ts = row["ts"]
        daily_by_date[ts] = daily_by_date.get(ts, 0) + int(row.get("views_count", 0))

    sorted_dates = _reported_or_collection_dates(daily_by_date, traffic_reporting or {})
    last_30_dates = sorted_dates[-30:]
    last_90_dates = sorted_dates[-90:]
    top_repo_rows = per_repo[:10]
    donut_rows = per_repo[:6]

    return {
        "daily_30_dates": last_30_dates,
        "daily_30_views": [daily_by_date.get(ts) for ts in last_30_dates],
        "daily_90_dates": last_90_dates,
        "daily_90_views": [daily_by_date.get(ts) for ts in last_90_dates],
        "top_repo_labels": [row["repo"] for row in top_repo_rows],
        "top_repo_views": [row["total_views"] for row in top_repo_rows],
        "share_repo_labels": [row["repo"] for row in donut_rows],
        "share_repo_views": [row["total_views"] for row in donut_rows],
        "totals": totals,
        "traffic_reporting": traffic_reporting or {},
    }


def _reported_or_collection_dates(
    daily_by_date: dict[str, int],
    traffic_reporting: dict,
) -> list[str]:
    sorted_dates = sorted(daily_by_date)
    latest_collection = str(traffic_reporting.get("latest_collection_date") or "")
    if not sorted_dates or not latest_collection:
        return sorted_dates
    latest_reported = sorted_dates[-1]
    if latest_collection <= latest_reported:
        return sorted_dates
    return sorted_dates + _date_range(_next_day(latest_reported), latest_collection)


def _date_range(start: str, end: str) -> list[str]:
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if not start_date or not end_date or start_date > end_date:
        return []
    results = []
    cursor = start_date
    while cursor <= end_date:
        results.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return results


def _next_day(ts: str) -> str:
    parsed = _parse_date(ts)
    if not parsed:
        return ts
    return (parsed + timedelta(days=1)).isoformat()


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
