"""Shared collection quality summary helpers."""

UNKNOWN_COLLECTION_QUALITY = {
    "available": False,
    "status": "unknown",
    "message": "",
    "latest_captured_at": "",
    "tracked_repos": 0,
    "with_data_repos": 0,
    "zero_traffic_repos": 0,
    "skipped_repos": 0,
    "error_repos": 0,
    "coverage_ratio": 1.0,
    "has_collection_gaps": False,
    "repos": [],
    "days": [],
}


def _rows_for_capture(rows, captured_at):
    return [row for row in rows if row.get("captured_at", "") == captured_at]


def _quality_status(summary):
    if summary["has_collection_gaps"]:
        return "gaps_detected"
    if _all_tracked_repos_report_zero(summary):
        return "all_zero"
    return "healthy"


def _all_tracked_repos_report_zero(summary):
    return (
        summary["tracked_repos"] > 0
        and summary["zero_traffic_repos"] == summary["tracked_repos"]
    )


def _quality_message(status, summary):
    if status == "gaps_detected":
        return (
            "Collection gaps detected in the latest run: "
            + f"{summary['skipped_repos']} skipped, {summary['error_repos']} error(s), "
            + f"{summary['observed_repos']}/{summary['tracked_repos']} repos collected."
        )
    if status == "all_zero":
        return (
            "Latest collection succeeded but reported zero traffic "
            + f"for all {summary['tracked_repos']} tracked repos."
        )
    return ""


def _repo_status_entry(repo, row):
    return {
        "repo": repo,
        "status": row.get("status", ""),
        "metric_source": row.get("metric_source", ""),
        "error_type": row.get("error_type", ""),
    }


def _gap_repos(summary):
    return sorted(
        [
            _repo_status_entry(repo, row)
            for repo, row in summary["by_repo"].items()
            if _is_gap_status(row.get("status", ""))
        ],
        key=lambda item: item["repo"],
    )


def _is_gap_status(status):
    return status.startswith("skipped") or status.startswith("error")


def _all_quality_repos(summary):
    return sorted(
        [
            _repo_status_entry(repo, row)
            for repo, row in summary["by_repo"].items()
            if repo
        ],
        key=lambda item: item["repo"],
    )


def _quality_summary_for_rows(rows):
    by_repo = _latest_row_by_repo(rows)
    counts = _status_counts(by_repo.values())
    tracked_repos = len(by_repo)
    with_data_repos = counts["ok_with_data"]
    zero_traffic_repos = counts["ok_zero_data"]
    skipped_repos = counts["skipped_unavailable"]
    error_repos = counts["error"] + counts["error_secondary_rate_limit"]
    observed_repos = with_data_repos + zero_traffic_repos

    return {
        "by_repo": by_repo,
        "tracked_repos": tracked_repos,
        "with_data_repos": with_data_repos,
        "zero_traffic_repos": zero_traffic_repos,
        "skipped_repos": skipped_repos,
        "error_repos": error_repos,
        "observed_repos": observed_repos,
        "coverage_ratio": _coverage_ratio(observed_repos, tracked_repos),
        "has_collection_gaps": skipped_repos > 0 or error_repos > 0,
    }


def _latest_row_by_repo(rows):
    by_repo = {}
    for row in rows:
        repo = row.get("repo", "")
        if repo:
            by_repo[repo] = row
    return by_repo


def _status_counts(rows):
    counts = {
        "ok_with_data": 0,
        "ok_zero_data": 0,
        "skipped_unavailable": 0,
        "error": 0,
        "error_secondary_rate_limit": 0,
    }
    for row in rows:
        status = row.get("status", "")
        if status in counts:
            counts[status] += 1
    return counts


def _coverage_ratio(observed_repos, tracked_repos):
    return (observed_repos / tracked_repos) if tracked_repos else 1.0
