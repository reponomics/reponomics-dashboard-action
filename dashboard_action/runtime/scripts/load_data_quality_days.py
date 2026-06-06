"""Daily collection quality summaries."""

from collections import defaultdict

from load_data_quality_summary import (
    _all_quality_repos,
    _quality_status,
    _quality_summary_for_rows,
    _rows_for_capture,
)


def collection_quality_days(status_rows):
    """Return daily quality summaries keyed from latest run per day."""
    return [
        _quality_day_summary(day, rows)
        for day, rows in sorted(_status_rows_by_day(status_rows).items())
    ]


def _status_rows_by_day(status_rows):
    by_day = defaultdict(list)
    for row in status_rows:
        ts = row.get("ts", "")
        captured_at = row.get("captured_at", "")
        if ts and captured_at:
            by_day[ts].append(row)
    return by_day


def _quality_day_summary(day, rows):
    run_timestamps = sorted({row.get("captured_at", "") for row in rows})
    latest_captured_at = run_timestamps[-1]
    summary = _quality_summary_for_rows(_rows_for_capture(rows, latest_captured_at))

    return {
        "date": day,
        "status": _quality_status(summary),
        "has_collection_gaps": summary["has_collection_gaps"],
        "latest_captured_at": latest_captured_at,
        "run_count": len(run_timestamps),
        "tracked_repos": summary["tracked_repos"],
        "with_data_repos": summary["with_data_repos"],
        "zero_traffic_repos": summary["zero_traffic_repos"],
        "skipped_repos": summary["skipped_repos"],
        "error_repos": summary["error_repos"],
        "coverage_ratio": round(summary["coverage_ratio"], 4),
        "repos": _all_quality_repos(summary),
    }
