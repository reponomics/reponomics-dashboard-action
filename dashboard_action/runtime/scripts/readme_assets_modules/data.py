"""Data shaping for generated README SVG assets."""

from __future__ import annotations


def build_readme_asset_data(
    daily_rows: list[dict],
    per_repo: list[dict],
    totals: dict | None = None,
) -> dict:
    """Build chart-ready data for README SVG assets."""
    daily_by_date: dict[str, int] = {}
    for row in daily_rows:
        ts = row["ts"]
        daily_by_date[ts] = daily_by_date.get(ts, 0) + int(row.get("views_count", 0))

    sorted_dates = sorted(daily_by_date)
    last_30_dates = sorted_dates[-30:]
    last_90_dates = sorted_dates[-90:]
    top_repo_rows = per_repo[:10]
    donut_rows = per_repo[:6]

    return {
        "daily_30_dates": last_30_dates,
        "daily_30_views": [daily_by_date[ts] for ts in last_30_dates],
        "daily_90_dates": last_90_dates,
        "daily_90_views": [daily_by_date[ts] for ts in last_90_dates],
        "top_repo_labels": [row["repo"] for row in top_repo_rows],
        "top_repo_views": [row["total_views"] for row in top_repo_rows],
        "share_repo_labels": [row["repo"] for row in donut_rows],
        "share_repo_views": [row["total_views"] for row in donut_rows],
        "totals": totals,
    }
