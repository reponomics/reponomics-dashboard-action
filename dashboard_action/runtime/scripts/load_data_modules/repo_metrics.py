"""Repository metric snapshots from repo-metrics.csv rows."""

from collections import defaultdict
from collections.abc import Iterable

from load_data_modules.parse import _bool_or_none, _counter_snapshot, _int_or_none
from load_data_modules.types import Result, Row, Rows


def latest_repo_metrics(metric_rows: Rows) -> dict[str, Result]:
    """Return latest aggregate repository counters keyed by repo."""
    latest: dict[str, Result] = {}
    for row in metric_rows:
        repo = row.get("repo", "")
        captured_at = row.get("captured_at", "")
        if not repo:
            continue
        existing = latest.get(repo)
        if existing is None or captured_at >= existing.get("captured_at", ""):
            latest[repo] = _repo_metric_snapshot(row)
    return latest


def latest_repo_metadata(metric_rows: Rows) -> dict[str, Result]:
    """Return latest repository metadata keyed by repo."""
    latest: dict[str, Result] = {}
    for row in metric_rows:
        repo = row.get("repo", "")
        captured_at = row.get("captured_at", "")
        if not repo:
            continue
        existing = latest.get(repo)
        if existing is None or captured_at >= existing.get("captured_at", ""):
            latest[repo] = {
                "captured_at": captured_at,
                "created_at": row.get("created_at", "") or "",
                "pushed_at": row.get("pushed_at", "") or "",
                "updated_at": row.get("updated_at", "") or "",
            }
    return latest


def _repo_metric_snapshot(row: Row) -> Result:
    """Normalize a repo-metrics row to the counter fields used downstream."""
    return {
        "repo": row.get("repo", ""),
        "ts": row.get("ts", ""),
        "captured_at": row.get("captured_at", ""),
        "stargazers_count": _counter_snapshot(row, "stargazers_count"),
        "subscribers_count": _counter_snapshot(row, "subscribers_count"),
        "forks_count": _counter_snapshot(row, "forks_count"),
    }


def latest_repo_community_profiles(metric_rows: Rows) -> dict[str, Result]:
    """Return latest community health metrics keyed by repo."""
    latest: dict[str, Result] = {}
    for row in metric_rows:
        repo = row.get("repo", "")
        captured_at = row.get("captured_at", "")
        if not repo:
            continue
        existing = latest.get(repo)
        if existing is not None and captured_at < existing.get("captured_at", ""):
            continue
        latest[repo] = _community_profile(row, captured_at)
    return latest


def _community_profile(row: Row, captured_at: str) -> Result:
    """Normalize optional GitHub community profile fields."""
    health = _int_or_none(row.get("community_health_percentage"))
    return {
        "captured_at": captured_at,
        "available": health is not None,
        "health_percentage": health,
        "documentation": row.get("community_documentation", "") or "",
        "updated_at": row.get("community_updated_at", "") or "",
        "content_reports_enabled": _bool_or_none(
            row.get("community_content_reports_enabled")
        ),
        "has_code_of_conduct": _bool_or_none(row.get("community_has_code_of_conduct")),
        "has_contributing": _bool_or_none(row.get("community_has_contributing")),
        "has_issue_template": _bool_or_none(row.get("community_has_issue_template")),
        "has_pull_request_template": _bool_or_none(
            row.get("community_has_pull_request_template")
        ),
        "has_readme": _bool_or_none(row.get("community_has_readme")),
        "has_license": _bool_or_none(row.get("community_has_license")),
    }


def latest_repo_metrics_per_day(metric_rows: Rows) -> dict[str, list[Result]]:
    """Return latest repo metric snapshot for each repo/day."""
    by_repo_day: dict[tuple[str, str], Result] = {}
    for row in metric_rows:
        repo = row.get("repo", "")
        ts = row.get("ts", "")
        if not repo or not ts:
            continue
        _store_latest_repo_day(by_repo_day, row, repo, ts)
    return _group_repo_day_rows(by_repo_day.values())


def _store_latest_repo_day(
    by_repo_day: dict[tuple[str, str], Result], row: Row, repo: str, ts: str
) -> None:
    """Keep the latest capture for a single repo/date key."""
    key = (repo, ts)
    captured_at = row.get("captured_at", "")
    existing = by_repo_day.get(key)
    if existing is None or captured_at >= existing.get("captured_at", ""):
        by_repo_day[key] = {
            **_repo_metric_snapshot(row),
            "stargazers_count_observed": _int_or_none(row.get("stargazers_count")) is not None,
            "subscribers_count_observed": _int_or_none(row.get("subscribers_count")) is not None,
            "forks_count_observed": _int_or_none(row.get("forks_count")) is not None,
        }


def _group_repo_day_rows(rows: Iterable[Result]) -> dict[str, list[Result]]:
    """Group normalized repo/day snapshots by repo in chronological order."""
    by_repo: defaultdict[str, list[Result]] = defaultdict(list)
    for row in rows:
        by_repo[row["repo"]].append(row)
    return {
        repo: sorted(rows, key=lambda item: (item.get("ts", ""), item.get("captured_at", "")))
        for repo, rows in by_repo.items()
    }


def repo_growth_series(metric_rows: Rows) -> dict[str, Result]:
    """Return per-repo growth counter series from normalized repo-metrics.csv."""
    return {
        repo: {
            "dates": [row["ts"] for row in rows],
            "stargazers": [row["stargazers_count"] for row in rows],
            "subscribers": [row["subscribers_count"] for row in rows],
            "forks": [row["forks_count"] for row in rows],
            "samples": len(rows),
        }
        for repo, rows in latest_repo_metrics_per_day(metric_rows).items()
    }


def aggregate_repo_metrics(metric_rows: Rows) -> Result:
    """Compute current aggregate repository growth counters."""
    latest = latest_repo_metrics(metric_rows)
    stargazers = sum(row["stargazers_count"] for row in latest.values())
    return {
        "repos": set(latest),
        "total_stargazers": stargazers,
        "total_stars": stargazers,
        "total_subscribers": sum(row["subscribers_count"] for row in latest.values()),
        "total_forks": sum(row["forks_count"] for row in latest.values()),
    }
