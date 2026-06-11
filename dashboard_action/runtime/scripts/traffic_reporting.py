"""Collection cadence and traffic reporting coverage derivation."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from storage import SCHEMA_VERSION

Rows = list[dict[str, Any]]

OK_STATUSES = {"ok_with_data", "ok_zero_data"}
SKIPPED_STATUSES = {"skipped_unavailable"}
ERROR_STATUSES = {"error", "error_secondary_rate_limit"}


def collection_day_rows(status_rows: Rows) -> Rows:
    """Materialize one collection cadence row for every retained calendar day."""
    rows_by_day = _status_rows_by_day(status_rows)
    if not rows_by_day:
        return []

    days = sorted(rows_by_day)
    results = []
    for ts in _date_range(days[0], days[-1]):
        rows = rows_by_day.get(ts, [])
        if not rows:
            results.append(_no_run_day(ts))
            continue
        results.append(_collection_day_summary(ts, rows))
    return results


def traffic_coverage_rows(daily_rows: Rows, status_rows: Rows) -> Rows:
    """Materialize per-repo/per-date traffic reporting coverage rows."""
    reported: dict[tuple[str, str], dict[str, Any]] = {}
    reported_dates_by_repo: defaultdict[str, set[str]] = defaultdict(set)
    latest_collection_by_repo = _latest_collection_date_by_repo(status_rows)

    for row in daily_rows:
        repo = row.get("repo", "")
        ts = row.get("ts", "")
        if not repo or not ts:
            continue
        key = (repo, ts)
        reported_dates_by_repo[repo].add(ts)
        existing = reported.get(key)
        if existing is None or row.get("captured_at", "") >= existing.get("reported_at", ""):
            reported[key] = {
                "repo": repo,
                "ts": ts,
                "coverage_state": "reported",
                "reported_at": row.get("captured_at", ""),
                "latest_collection_ts": latest_collection_by_repo.get(repo, ""),
                "latest_captured_at": row.get("captured_at", ""),
                "reason": "traffic row present",
                "schema_version": SCHEMA_VERSION,
            }

    coverage = dict(reported)
    for row in _latest_status_rows_by_repo_day(status_rows).values():
        repo = row.get("repo", "")
        collection_ts = row.get("ts", "")
        if not repo or not collection_ts:
            continue
        status = row.get("status", "")
        if status in OK_STATUSES:
            latest_reported = _latest_reported_on_or_before(
                reported_dates_by_repo.get(repo, set()),
                collection_ts,
            )
            if not latest_reported or latest_reported >= collection_ts:
                continue
            for missing_ts in _date_range(_next_day(latest_reported), collection_ts):
                key = (repo, missing_ts)
                if key in reported:
                    continue
                coverage[key] = _coverage_state_row(
                    row,
                    missing_ts,
                    "not_reported_by_api",
                    "traffic endpoint did not report this trailing day",
                )
        elif status in SKIPPED_STATUSES:
            key = (repo, collection_ts)
            if key not in reported:
                coverage[key] = _coverage_state_row(
                    row,
                    collection_ts,
                    "repo_skipped",
                    "repository was skipped during collection",
                )
        elif status in ERROR_STATUSES:
            key = (repo, collection_ts)
            if key not in reported:
                coverage[key] = _coverage_state_row(
                    row,
                    collection_ts,
                    "collection_failed",
                    "repository collection failed",
                )

    return sorted(coverage.values(), key=lambda item: (item["repo"], item["ts"]))


def traffic_reporting_summary(coverage_rows: Rows, collection_days: Rows) -> dict[str, Any]:
    """Summarize coverage rows for dashboard rendering and warnings."""
    latest_collection_date = _latest_collection_date(collection_days)
    latest_reported_date = max(
        (
            row.get("ts", "")
            for row in coverage_rows
            if row.get("coverage_state") == "reported" and row.get("ts")
        ),
        default="",
    )
    not_reported = [
        row
        for row in coverage_rows
        if row.get("coverage_state") == "not_reported_by_api"
    ]
    unreported_dates = sorted(
        {
            row.get("ts", "")
            for row in not_reported
            if row.get("ts")
        }
    )
    lag_days = (
        len(unreported_dates)
        if unreported_dates
        else _days_between(latest_reported_date, latest_collection_date)
    )
    counts = _coverage_counts(coverage_rows)

    return {
        "available": bool(coverage_rows or collection_days),
        "latest_collection_date": latest_collection_date,
        "latest_reported_traffic_date": latest_reported_date,
        "lag_days": max(0, lag_days),
        "has_lag": bool(not_reported),
        "affected_repos": sorted({row.get("repo", "") for row in not_reported if row.get("repo")}),
        "unreported_ranges": _coverage_ranges(not_reported),
        "unreported_start_date": unreported_dates[0] if unreported_dates else "",
        "unreported_end_date": unreported_dates[-1] if unreported_dates else "",
        "unreported_days": len(unreported_dates),
        "coverage_counts": counts,
    }


def collection_quality_days_from_rows(day_rows: Rows) -> Rows:
    """Return collection quality day payloads from materialized collection-day rows."""
    results = []
    for row in day_rows:
        status = row.get("status", "")
        results.append(
            {
                "date": row.get("ts", ""),
                "status": status,
                "has_collection_gaps": status == "gaps_detected",
                "latest_captured_at": row.get("latest_captured_at", ""),
                "run_count": _int(row.get("run_count", 0)),
                "tracked_repos": _int(row.get("tracked_repos", 0)),
                "with_data_repos": _int(row.get("with_data_repos", 0)),
                "zero_traffic_repos": _int(row.get("zero_traffic_repos", 0)),
                "skipped_repos": _int(row.get("skipped_repos", 0)),
                "error_repos": _int(row.get("error_repos", 0)),
                "coverage_ratio": _coverage_ratio(
                    _int(row.get("with_data_repos", 0)) + _int(row.get("zero_traffic_repos", 0)),
                    _int(row.get("tracked_repos", 0)),
                ),
                "repos": [],
            }
        )
    return results


def _status_rows_by_day(status_rows: Rows) -> dict[str, Rows]:
    by_day: defaultdict[str, Rows] = defaultdict(list)
    for row in status_rows:
        ts = row.get("ts", "")
        captured_at = row.get("captured_at", "")
        if ts and captured_at:
            by_day[ts].append(row)
    return by_day


def _collection_day_summary(ts: str, rows: Rows) -> dict[str, Any]:
    captures = sorted({row.get("captured_at", "") for row in rows if row.get("captured_at")})
    latest_captured_at = captures[-1] if captures else ""
    latest_rows = [
        row for row in rows if row.get("captured_at", "") == latest_captured_at
    ]
    counts = _status_counts(_latest_status_by_repo(latest_rows).values())
    tracked = sum(counts.values())
    skipped = counts["skipped_unavailable"]
    errors = counts["error"] + counts["error_secondary_rate_limit"]
    zero = counts["ok_zero_data"]
    status = "healthy"
    if skipped or errors:
        status = "gaps_detected"
    elif tracked and zero == tracked:
        status = "all_zero"
    return {
        "ts": ts,
        "status": status,
        "latest_captured_at": latest_captured_at,
        "run_count": len(captures),
        "tracked_repos": tracked,
        "with_data_repos": counts["ok_with_data"],
        "zero_traffic_repos": zero,
        "skipped_repos": skipped,
        "error_repos": errors,
        "schema_version": SCHEMA_VERSION,
    }


def _no_run_day(ts: str) -> dict[str, Any]:
    return {
        "ts": ts,
        "status": "no_run",
        "latest_captured_at": "",
        "run_count": 0,
        "tracked_repos": 0,
        "with_data_repos": 0,
        "zero_traffic_repos": 0,
        "skipped_repos": 0,
        "error_repos": 0,
        "schema_version": SCHEMA_VERSION,
    }


def _latest_status_rows_by_repo_day(status_rows: Rows) -> dict[tuple[str, str], dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in status_rows:
        repo = row.get("repo", "")
        ts = row.get("ts", "")
        if not repo or not ts:
            continue
        key = (repo, ts)
        if row.get("captured_at", "") >= latest.get(key, {}).get("captured_at", ""):
            latest[key] = row
    return latest


def _latest_collection_date_by_repo(status_rows: Rows) -> dict[str, str]:
    dates: dict[str, str] = {}
    for row in status_rows:
        repo = row.get("repo", "")
        ts = row.get("ts", "")
        if repo and ts and ts >= dates.get(repo, ""):
            dates[repo] = ts
    return dates


def _latest_status_by_repo(rows: Rows) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        repo = row.get("repo", "")
        if repo:
            latest[repo] = row
    return latest


def _status_counts(rows: Any) -> dict[str, int]:
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


def _coverage_state_row(
    status_row: dict[str, Any],
    ts: str,
    state: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "repo": status_row.get("repo", ""),
        "ts": ts,
        "coverage_state": state,
        "reported_at": "",
        "latest_collection_ts": status_row.get("ts", ""),
        "latest_captured_at": status_row.get("captured_at", ""),
        "reason": reason,
        "schema_version": SCHEMA_VERSION,
    }


def _latest_reported_on_or_before(reported_dates: set[str], collection_ts: str) -> str:
    return max((ts for ts in reported_dates if ts <= collection_ts), default="")


def _latest_collection_date(collection_days: Rows) -> str:
    return max(
        (
            row.get("ts", "")
            for row in collection_days
            if row.get("ts") and row.get("status") != "no_run"
        ),
        default=max((row.get("ts", "") for row in collection_days if row.get("ts")), default=""),
    )


def _coverage_counts(coverage_rows: Rows) -> dict[str, int]:
    counts = {
        "reported": 0,
        "not_reported_by_api": 0,
        "collection_failed": 0,
        "repo_skipped": 0,
    }
    for row in coverage_rows:
        state = row.get("coverage_state", "")
        if state in counts:
            counts[state] += 1
    return counts


def _coverage_ranges(rows: Rows) -> Rows:
    by_repo: defaultdict[str, list[str]] = defaultdict(list)
    for row in rows:
        repo = row.get("repo", "")
        ts = row.get("ts", "")
        if repo and ts:
            by_repo[repo].append(ts)

    ranges = []
    for repo, dates in sorted(by_repo.items()):
        sorted_dates = sorted(set(dates))
        start = previous = sorted_dates[0]
        for ts in sorted_dates[1:]:
            if ts != _next_day(previous):
                ranges.append(_range_row(repo, start, previous))
                start = ts
            previous = ts
        ranges.append(_range_row(repo, start, previous))
    return ranges


def _range_row(repo: str, start: str, end: str) -> dict[str, Any]:
    return {
        "repo": repo,
        "start": start,
        "end": end,
        "days": _days_between(start, end) + 1,
    }


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


def _days_between(start: str, end: str) -> int:
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if not start_date or not end_date:
        return 0
    return (end_date - start_date).days


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _coverage_ratio(observed_repos: int, tracked_repos: int) -> float:
    return round((observed_repos / tracked_repos) if tracked_repos else 1.0, 4)
