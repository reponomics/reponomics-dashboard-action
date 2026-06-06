"""Collection quality summaries for dashboard data."""

from load_data_modules.quality_days import collection_quality_days
from load_data_modules.quality_summary import (
    UNKNOWN_COLLECTION_QUALITY,
    _gap_repos,
    _quality_message,
    _quality_status,
    _quality_summary_for_rows,
    _rows_for_capture,
)
from load_data_modules.types import Result, Rows


def collection_quality(status_rows: Rows) -> Result:
    """Summarize the latest collection run quality from collection-status.csv."""
    if not status_rows:
        return dict(UNKNOWN_COLLECTION_QUALITY)

    latest_captured_at = max(
        row.get("captured_at", "") for row in status_rows if row.get("captured_at")
    )
    latest_rows = _rows_for_capture(status_rows, latest_captured_at)
    summary = _quality_summary_for_rows(latest_rows)
    status = _quality_status(summary)

    return {
        "available": True,
        "status": status,
        "message": _quality_message(status, summary),
        "latest_captured_at": latest_captured_at,
        "tracked_repos": summary["tracked_repos"],
        "with_data_repos": summary["with_data_repos"],
        "zero_traffic_repos": summary["zero_traffic_repos"],
        "skipped_repos": summary["skipped_repos"],
        "error_repos": summary["error_repos"],
        "coverage_ratio": round(summary["coverage_ratio"], 4),
        "has_collection_gaps": summary["has_collection_gaps"],
        "repos": _gap_repos(summary),
        "days": collection_quality_days(status_rows),
    }
