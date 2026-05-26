"""Shared data-loading path for README and HTML dashboard renderers.

Both renderers must derive from the same canonical CSV data to ensure
core totals agree. This module provides the single entry point for
loading and aggregating traffic data from the artifact-backed CSVs.
"""

import os
from collections import defaultdict
import math
import statistics
from typing import Any

from repo_config import load_repo_config
import storage

GROWTH_COUNTERS = {
    "stargazers": "stargazers_count",
    "subscribers": "subscribers_count",
    "forks": "forks_count",
}


def _int_or_none(value):
    """Return an integer for observed counter values, preserving missing data."""
    if value is None or value == "":
        return None
    return int(value)


def _counter_snapshot(row, field):
    value = _int_or_none(row.get(field))
    return value if value is not None else 0


def load_daily(data_dir=None):
    """Load canonical daily rows, falling back to traffic-log.csv for old artifacts."""
    d = data_dir or storage.DATA_DIR
    rows = storage.read_csv(os.path.join(d, "traffic-daily.csv"))
    if not rows:
        rows = storage.read_csv(os.path.join(d, "traffic-log.csv"))
    return _filter_excluded_rows(rows)


def load_referrers(data_dir=None):
    """Load traffic-referrers.csv and return the raw row list."""
    d = data_dir or storage.DATA_DIR
    return _filter_excluded_rows(storage.read_csv(os.path.join(d, "traffic-referrers.csv")))


def load_paths(data_dir=None):
    """Load traffic-paths.csv and return the raw row list."""
    d = data_dir or storage.DATA_DIR
    return _filter_excluded_rows(storage.read_csv(os.path.join(d, "traffic-paths.csv")))


def load_repo_metrics(data_dir=None):
    """Load repo-metrics.csv and return the raw row list."""
    d = data_dir or storage.DATA_DIR
    return _filter_excluded_rows(storage.read_csv(os.path.join(d, "repo-metrics.csv")))


def load_collection_status(data_dir=None):
    """Load collection-status.csv and return the raw row list."""
    d = data_dir or storage.DATA_DIR
    return _filter_excluded_rows(storage.read_csv(os.path.join(d, "collection-status.csv")))


def _excluded_repos():
    """Return excluded repos from config, ignoring missing config files."""
    return set(load_repo_config().get("exclude_repos", []))


def _filter_excluded_rows(rows):
    """Hide excluded repos from rendered outputs while retaining artifact history."""
    excluded = _excluded_repos()
    if not excluded:
        return rows
    return [row for row in rows if row.get("repo") not in excluded]


def _latest_snapshot_rows(rows):
    """Return only rows from the latest captured snapshot for each repo.

    Referrer and path endpoints are rolling snapshots rather than additive
    time series. Summing across captures overcounts the same 14-day window,
    so downstream views must aggregate only the most recent snapshot per repo.
    """
    if not rows:
        return []

    latest_by_repo = {}
    for row in rows:
        repo = row["repo"]
        captured_at = row.get("captured_at", "")
        if captured_at > latest_by_repo.get(repo, ""):
            latest_by_repo[repo] = captured_at

    return [
        row
        for row in rows
        if row.get("captured_at", "") == latest_by_repo.get(row["repo"], "")
    ]


def latest_repo_metrics(metric_rows):
    """Return latest aggregate repository counters keyed by repo."""
    latest = {}
    for row in metric_rows:
        repo = row.get("repo", "")
        captured_at = row.get("captured_at", "")
        if not repo:
            continue
        existing = latest.get(repo)
        if existing is None or captured_at >= existing.get("captured_at", ""):
            latest[repo] = {
                "repo": repo,
                "ts": row.get("ts", ""),
                "captured_at": captured_at,
                "stargazers_count": _counter_snapshot(row, "stargazers_count"),
                "subscribers_count": _counter_snapshot(row, "subscribers_count"),
                "forks_count": _counter_snapshot(row, "forks_count"),
            }
    return latest


def latest_repo_metrics_per_day(metric_rows):
    """Return latest repo metric snapshot for each repo/day.

    repo-metrics.csv may contain more than one capture for a repo on the same
    day. Downstream growth calculations should treat the CSV as canonical while
    still collapsing those captures to the final observed counter values for
    that day.
    """
    by_repo_day = {}
    for row in metric_rows:
        repo = row.get("repo", "")
        ts = row.get("ts", "")
        if not repo or not ts:
            continue
        key = (repo, ts)
        captured_at = row.get("captured_at", "")
        existing = by_repo_day.get(key)
        if existing is None or captured_at >= existing.get("captured_at", ""):
            by_repo_day[key] = {
                "repo": repo,
                "ts": ts,
                "captured_at": captured_at,
                "stargazers_count": _counter_snapshot(row, "stargazers_count"),
                "subscribers_count": _counter_snapshot(row, "subscribers_count"),
                "forks_count": _counter_snapshot(row, "forks_count"),
                "stargazers_count_observed": _int_or_none(row.get("stargazers_count")) is not None,
                "subscribers_count_observed": _int_or_none(row.get("subscribers_count")) is not None,
                "forks_count_observed": _int_or_none(row.get("forks_count")) is not None,
            }

    by_repo = defaultdict(list)
    for row in by_repo_day.values():
        by_repo[row["repo"]].append(row)
    return {
        repo: sorted(rows, key=lambda item: (item.get("ts", ""), item.get("captured_at", "")))
        for repo, rows in by_repo.items()
    }


def repo_growth_series(metric_rows):
    """Return per-repo growth counter series from normalized repo-metrics.csv."""
    series = {}
    for repo, rows in latest_repo_metrics_per_day(metric_rows).items():
        series[repo] = {
            "dates": [row["ts"] for row in rows],
            "stargazers": [row["stargazers_count"] for row in rows],
            "subscribers": [row["subscribers_count"] for row in rows],
            "forks": [row["forks_count"] for row in rows],
            "samples": len(rows),
        }
    return series


def aggregate_repo_metrics(metric_rows):
    """Compute current aggregate repository growth counters."""
    latest = latest_repo_metrics(metric_rows)
    return {
        "repos": set(latest),
        "total_stargazers": sum(row["stargazers_count"] for row in latest.values()),
        "total_stars": sum(row["stargazers_count"] for row in latest.values()),
        "total_subscribers": sum(row["subscribers_count"] for row in latest.values()),
        "total_forks": sum(row["forks_count"] for row in latest.values()),
    }


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
    from datetime import datetime, timedelta
    latest_date = datetime.strptime(latest_ts, "%Y-%m-%d").date()
    return (latest_date - timedelta(days=recent_days - 1)).isoformat()


def collection_quality(status_rows):
    """Summarize the latest collection run quality from collection-status.csv."""
    if not status_rows:
        return {
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

    latest_captured_at = max(row.get("captured_at", "") for row in status_rows if row.get("captured_at"))
    latest_rows = [row for row in status_rows if row.get("captured_at", "") == latest_captured_at]
    summary = _quality_summary_for_rows(latest_rows)

    status = "healthy"
    message = ""
    if summary["has_collection_gaps"]:
        status = "gaps_detected"
        message = (
            "Collection gaps detected in the latest run: "
            + f"{summary['skipped_repos']} skipped, {summary['error_repos']} error(s), "
            + f"{summary['observed_repos']}/{summary['tracked_repos']} repos collected."
        )
    elif summary["tracked_repos"] > 0 and summary["zero_traffic_repos"] == summary["tracked_repos"]:
        status = "all_zero"
        message = (
            "Latest collection succeeded but reported zero traffic "
            + f"for all {summary['tracked_repos']} tracked repos."
        )

    return {
        "available": True,
        "status": status,
        "message": message,
        "latest_captured_at": latest_captured_at,
        "tracked_repos": summary["tracked_repos"],
        "with_data_repos": summary["with_data_repos"],
        "zero_traffic_repos": summary["zero_traffic_repos"],
        "skipped_repos": summary["skipped_repos"],
        "error_repos": summary["error_repos"],
        "coverage_ratio": round(summary["coverage_ratio"], 4),
        "has_collection_gaps": summary["has_collection_gaps"],
        "repos": sorted(
            [
                {
                    "repo": repo,
                    "status": row.get("status", ""),
                    "metric_source": row.get("metric_source", ""),
                    "error_type": row.get("error_type", ""),
                }
                for repo, row in summary["by_repo"].items()
                if row.get("status", "").startswith("skipped") or row.get("status", "").startswith("error")
            ],
            key=lambda item: item["repo"],
        ),
        "days": collection_quality_days(status_rows),
    }


def _quality_summary_for_rows(rows):
    by_repo = {}
    for row in rows:
        repo = row.get("repo", "")
        if repo:
            by_repo[repo] = row

    counts = {
        "ok_with_data": 0,
        "ok_zero_data": 0,
        "skipped_unavailable": 0,
        "error": 0,
        "error_secondary_rate_limit": 0,
    }
    for row in by_repo.values():
        status = row.get("status", "")
        if status in counts:
            counts[status] += 1

    tracked_repos = len(by_repo)
    with_data_repos = counts["ok_with_data"]
    zero_traffic_repos = counts["ok_zero_data"]
    skipped_repos = counts["skipped_unavailable"]
    error_repos = counts["error"] + counts["error_secondary_rate_limit"]
    observed_repos = with_data_repos + zero_traffic_repos
    coverage_ratio = (observed_repos / tracked_repos) if tracked_repos else 1.0
    has_collection_gaps = skipped_repos > 0 or error_repos > 0

    return {
        "by_repo": by_repo,
        "tracked_repos": tracked_repos,
        "with_data_repos": with_data_repos,
        "zero_traffic_repos": zero_traffic_repos,
        "skipped_repos": skipped_repos,
        "error_repos": error_repos,
        "observed_repos": observed_repos,
        "coverage_ratio": coverage_ratio,
        "has_collection_gaps": has_collection_gaps,
    }


def collection_quality_days(status_rows):
    """Return daily quality summaries keyed from latest run per day."""
    if not status_rows:
        return []

    by_day = defaultdict(list)
    for row in status_rows:
        ts = row.get("ts", "")
        captured_at = row.get("captured_at", "")
        if not ts or not captured_at:
            continue
        by_day[ts].append(row)

    summaries = []
    for day, rows in by_day.items():
        run_timestamps = sorted({row.get("captured_at", "") for row in rows if row.get("captured_at")})
        if not run_timestamps:
            continue
        latest_captured_at = run_timestamps[-1]
        latest_rows = [row for row in rows if row.get("captured_at", "") == latest_captured_at]
        summary = _quality_summary_for_rows(latest_rows)
        status = "healthy"
        if summary["has_collection_gaps"]:
            status = "gaps_detected"
        elif summary["tracked_repos"] > 0 and summary["zero_traffic_repos"] == summary["tracked_repos"]:
            status = "all_zero"
        summaries.append(
            {
                "date": day,
                "status": status,
                "has_collection_gaps": summary["has_collection_gaps"],
                "latest_captured_at": latest_captured_at,
                "run_count": len(run_timestamps),
                "tracked_repos": summary["tracked_repos"],
                "with_data_repos": summary["with_data_repos"],
                "zero_traffic_repos": summary["zero_traffic_repos"],
                "skipped_repos": summary["skipped_repos"],
                "error_repos": summary["error_repos"],
                "coverage_ratio": round(summary["coverage_ratio"], 4),
            }
        )

    return sorted(summaries, key=lambda item: item["date"])


def repo_metric_deltas(metric_rows, recent_days=14):
    """Return per-repo and aggregate net counter changes in the recent window.

    The baseline is the earliest retained sample on or after the recent-window
    cutoff for each repo. If a repo has only one sample, its deltas are zero.
    """
    if not metric_rows:
        return {
            "repos": {},
            "total_stargazers_delta": 0,
            "total_stars_delta": 0,
            "total_subscribers_delta": 0,
            "total_forks_delta": 0,
        }

    latest_ts = _latest_date_from_rows(metric_rows)
    cutoff = _window_cutoff(latest_ts, recent_days)

    grouped = latest_repo_metrics_per_day(metric_rows)

    by_repo = {}
    totals = {
        "total_stargazers_delta": 0,
        "total_stars_delta": 0,
        "total_subscribers_delta": 0,
        "total_forks_delta": 0,
    }
    for repo, rows in grouped.items():
        if not repo:
            continue
        window_rows = [row for row in rows if not cutoff or row.get("ts", "") >= cutoff]
        if not window_rows:
            continue
        first = window_rows[0]
        last = window_rows[-1]

        def delta(field):
            observed = [
                row
                for row in window_rows
                if row.get(f"{field}_observed", True)
            ]
            if len(observed) < 2:
                return 0
            return int(observed[-1].get(field, 0) or 0) - int(observed[0].get(field, 0) or 0)

        repo_delta = {
            "stargazers_delta": delta("stargazers_count"),
            "stars_delta": delta("stargazers_count"),
            "subscribers_delta": delta("subscribers_count"),
            "forks_delta": delta("forks_count"),
            "sample_count": len(window_rows),
            "start_date": first.get("ts", ""),
            "end_date": last.get("ts", ""),
            "current_stargazers": int(last.get("stargazers_count", 0) or 0),
            "current_stars": int(last.get("stargazers_count", 0) or 0),
            "current_subscribers": int(last.get("subscribers_count", 0) or 0),
            "current_forks": int(last.get("forks_count", 0) or 0),
        }
        by_repo[repo] = repo_delta
        totals["total_stargazers_delta"] += repo_delta["stargazers_delta"]
        totals["total_stars_delta"] += repo_delta["stars_delta"]
        totals["total_subscribers_delta"] += repo_delta["subscribers_delta"]
        totals["total_forks_delta"] += repo_delta["forks_delta"]

    return {"repos": by_repo, **totals}


def _traffic_totals_by_repo(daily_rows, cutoff=None):
    by_repo = defaultdict(lambda: {
        "views": 0,
        "uniques": 0,
        "clones": 0,
        "clone_uniques": 0,
        "sample_count": 0,
    })
    for row in daily_rows:
        if cutoff and row.get("ts", "") < cutoff:
            continue
        repo = row.get("repo", "")
        if not repo:
            continue
        by_repo[repo]["views"] += int(row.get("views_count", 0) or 0)
        by_repo[repo]["uniques"] += int(row.get("views_uniques", 0) or 0)
        by_repo[repo]["clones"] += int(row.get("clones_count", 0) or 0)
        by_repo[repo]["clone_uniques"] += int(row.get("clones_uniques", 0) or 0)
        by_repo[repo]["sample_count"] += 1
    return dict(by_repo)


def _safe_ratio(numerator, preferred_denominator, fallback_denominator, *, min_denominator=5):
    if preferred_denominator >= min_denominator:
        return {
            "value": numerator / preferred_denominator,
            "denominator": preferred_denominator,
            "denominator_metric": "visitors",
        }
    if fallback_denominator >= min_denominator:
        return {
            "value": numerator / fallback_denominator,
            "denominator": fallback_denominator,
            "denominator_metric": "views",
        }
    return {"value": None, "denominator": 0, "denominator_metric": None}


def growth_analytics(daily_rows, metric_rows, recent_days=14):
    """Compute shared growth totals, deltas, ratios, and per-repo series.

    This is the canonical growth analytics entry point for README and HTML
    renderers. It derives repository counter movement only from repo-metrics.csv
    and traffic denominators only from traffic-daily.csv.
    """
    latest_ts = _latest_date_from_rows(daily_rows, metric_rows)
    cutoff = _window_cutoff(latest_ts, recent_days)
    current = aggregate_repo_metrics(metric_rows)
    deltas = repo_metric_deltas(metric_rows, recent_days=recent_days)
    series = repo_growth_series(metric_rows)
    traffic = _traffic_totals_by_repo(daily_rows, cutoff=cutoff)

    repos = sorted(set(current["repos"]) | set(traffic) | set(deltas["repos"]))
    per_repo = {}
    for repo in repos:
        delta = deltas["repos"].get(repo, {
            "stargazers_delta": 0,
            "stars_delta": 0,
            "subscribers_delta": 0,
            "forks_delta": 0,
            "sample_count": 0,
            "start_date": "",
            "end_date": "",
            "current_stargazers": 0,
            "current_stars": 0,
            "current_subscribers": 0,
            "current_forks": 0,
        })
        traffic_totals = traffic.get(repo, {
            "views": 0,
            "uniques": 0,
            "clones": 0,
            "clone_uniques": 0,
            "sample_count": 0,
        })
        conversions = {}
        for metric, _field in GROWTH_COUNTERS.items():
            delta_key = f"{metric}_delta"
            conversions[metric] = _safe_ratio(
                delta.get(delta_key, 0),
                traffic_totals["uniques"],
                traffic_totals["views"],
            )
        conversions["stars"] = conversions["stargazers"]
        per_repo[repo] = {
            "repo": repo,
            "traffic": traffic_totals,
            "deltas": delta,
            "conversion": conversions,
            "series": series.get(repo, {"dates": [], "stargazers": [], "subscribers": [], "forks": [], "samples": 0}),
        }

    return {
        "window_days": recent_days,
        "cutoff": cutoff,
        "latest_date": latest_ts,
        "current": current,
        "deltas": deltas,
        "series": series,
        "per_repo": per_repo,
        "totals": {
            "total_stargazers": current["total_stargazers"],
            "total_stars": current["total_stars"],
            "total_subscribers": current["total_subscribers"],
            "total_forks": current["total_forks"],
            "total_stargazers_delta": deltas["total_stargazers_delta"],
            "total_stars_delta": deltas["total_stars_delta"],
            "total_subscribers_delta": deltas["total_subscribers_delta"],
            "total_forks_delta": deltas["total_forks_delta"],
        },
    }


def aggregate_totals(daily_rows):
    """Compute grand totals from daily rows.

    Returns a dict with keys: repos (set), total_views, total_uniques,
    total_clones, total_clone_uniques, days_tracked (int).
    """
    repos = set()
    dates = set()
    total_views = 0
    total_uniques = 0
    total_clones = 0
    total_clone_uniques = 0

    for row in daily_rows:
        repos.add(row["repo"])
        dates.add(row["ts"])
        total_views += int(row.get("views_count", 0))
        total_uniques += int(row.get("views_uniques", 0))
        total_clones += int(row.get("clones_count", 0))
        total_clone_uniques += int(row.get("clones_uniques", 0))

    return {
        "repos": repos,
        "total_views": total_views,
        "total_uniques": total_uniques,
        "total_clones": total_clones,
        "total_clone_uniques": total_clone_uniques,
        "days_tracked": len(dates),
    }


def aggregate_by_date(daily_rows):
    """Group daily rows by date, summing across repos.

    Returns (sorted_dates, series_dict) where series_dict has keys:
    views, uniques, clones, clone_uniques — each a list aligned with
    sorted_dates.
    """
    by_date = defaultdict(lambda: {"views": 0, "uniques": 0,
                                    "clones": 0, "clone_uniques": 0})
    for row in daily_rows:
        ts = row["ts"]
        by_date[ts]["views"] += int(row.get("views_count", 0))
        by_date[ts]["uniques"] += int(row.get("views_uniques", 0))
        by_date[ts]["clones"] += int(row.get("clones_count", 0))
        by_date[ts]["clone_uniques"] += int(row.get("clones_uniques", 0))

    dates = sorted(by_date.keys())
    series = {
        "views": [by_date[d]["views"] for d in dates],
        "uniques": [by_date[d]["uniques"] for d in dates],
        "clones": [by_date[d]["clones"] for d in dates],
        "clone_uniques": [by_date[d]["clone_uniques"] for d in dates],
    }
    return dates, series


def aggregate_per_repo(daily_rows):
    """Compute per-repo totals from daily rows.

    Returns a list of dicts sorted by total_views descending, each with:
    repo, total_views, total_uniques, total_clones, total_clone_uniques.
    """
    by_repo = defaultdict(lambda: {"views": 0, "uniques": 0,
                                    "clones": 0, "clone_uniques": 0})
    for row in daily_rows:
        r = row["repo"]
        by_repo[r]["views"] += int(row.get("views_count", 0))
        by_repo[r]["uniques"] += int(row.get("views_uniques", 0))
        by_repo[r]["clones"] += int(row.get("clones_count", 0))
        by_repo[r]["clone_uniques"] += int(row.get("clones_uniques", 0))

    result = []
    for repo, totals in by_repo.items():
        result.append({
            "repo": repo,
            "total_views": totals["views"],
            "total_uniques": totals["uniques"],
            "total_clones": totals["clones"],
            "total_clone_uniques": totals["clone_uniques"],
        })
    result.sort(key=lambda x: x["total_views"], reverse=True)
    return result


def top_referrers(referrer_rows, limit=10):
    """Aggregate the latest referrer snapshot per repo and return top N.

    Uses only the latest captured snapshot for each repo, then sums
    count/uniques across repos for each referrer value.
    Returns a list of dicts: referrer, count, uniques.
    """
    by_ref = defaultdict(lambda: {"count": 0, "uniques": 0})
    for row in _latest_snapshot_rows(referrer_rows):
        ref = row["referrer"]
        by_ref[ref]["count"] += int(row.get("count", 0))
        by_ref[ref]["uniques"] += int(row.get("uniques", 0))

    result = [{"referrer": r, "count": v["count"], "uniques": v["uniques"]}
              for r, v in by_ref.items()]
    result.sort(key=lambda x: x["count"], reverse=True)
    return result[:limit]


def _content_label(row):
    """Return a display label for a GitHub traffic path row."""
    repo = row.get("repo", "")
    path = row.get("path", "")
    title = row.get("title", "")
    if repo and path.rstrip("/") == f"/{repo}".rstrip("/"):
        return "Repository overview"
    return title or path


def top_paths(path_rows, limit=10):
    """Return the top content paths from the latest snapshot for each repo.

    GitHub's popular-path endpoint returns path-level rows. A repository root
    path such as /owner/repo is a page view of the repository overview, not a
    repo-level aggregate. This function therefore keeps repository and content
    labels separate and ranks rows by their latest path-snapshot counts.

    Returns a list of dicts: repo, path, title, content, count, uniques.
    """
    by_path = defaultdict(lambda: {"count": 0, "uniques": 0, "title": "", "repo": ""})
    for row in _latest_snapshot_rows(path_rows):
        p = (row.get("repo", ""), row["path"])
        by_path[p]["repo"] = row.get("repo", "")
        by_path[p]["count"] += int(row.get("count", 0))
        by_path[p]["uniques"] += int(row.get("uniques", 0))
        if row.get("title"):
            by_path[p]["title"] = row["title"]

    result = [
        {
            "repo": v["repo"],
            "path": path,
            "title": v["title"],
            "content": _content_label({"repo": v["repo"], "path": path, "title": v["title"]}),
            "count": v["count"],
            "uniques": v["uniques"],
        }
        for (_repo, path), v in by_path.items()
    ]
    result.sort(key=lambda x: x["count"], reverse=True)
    return result[:limit]


def compute_momentum(daily_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate momentum stats from daily traffic rows.

    Returns a dict with:
        best_day: {date, views} (or None if no data)
        streak_days: int — consecutive trailing days where aggregate views beat the trailing-14d median
        baseline: float — the trailing-14d median used as the streak threshold
        days_since_peak: int | None
        top_single_day: {repo, date, views} | None — biggest single-repo single-day in the window
    """
    if not daily_rows:
        return {"best_day": None, "streak_days": 0, "baseline": 0.0, "days_since_peak": None, "top_single_day": None}

    by_date: dict[str, int] = defaultdict(int)
    top_single_day = None
    for row in daily_rows:
        ts = row.get("ts")
        v = int(row.get("views_count", 0) or 0)
        if not ts:
            continue
        by_date[ts] += v
        if top_single_day is None or v > top_single_day["views"]:
            top_single_day = {"repo": row.get("repo", ""), "date": ts, "views": v}

    if not by_date:
        return {"best_day": None, "streak_days": 0, "baseline": 0.0, "days_since_peak": None, "top_single_day": top_single_day}

    sorted_dates = sorted(by_date.keys())
    values = [by_date[d] for d in sorted_dates]

    best_idx = max(range(len(values)), key=lambda i: values[i])
    best_date = sorted_dates[best_idx]
    best_day = {"date": best_date, "views": values[best_idx]}

    tail_window = 14
    end_excl = max(0, len(values) - 1)
    start = max(0, end_excl - tail_window)
    tail = values[start:end_excl]
    baseline = statistics.median(tail) if tail else 0.0

    streak_days = 0
    for v in reversed(values):
        if v > baseline:
            streak_days += 1
        else:
            break

    days_since_peak = None
    try:
        from datetime import date as _date
        latest = _date.fromisoformat(sorted_dates[-1])
        peak = _date.fromisoformat(best_date)
        days_since_peak = (latest - peak).days
    except (ValueError, TypeError):
        days_since_peak = None

    return {
        "best_day": best_day,
        "streak_days": streak_days,
        "baseline": float(baseline),
        "days_since_peak": days_since_peak,
        "top_single_day": top_single_day,
    }


def actionable_insights(
    daily_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]] | int | None = None,
    limit: int = 3,
    growth: dict[str, Any] | None = None,
) -> list[str]:
    """Return ranked, lightweight insight bullets from per-repo daily metrics.

    Insights are generated from the same metric families for each repo:
    - views 7d-over-7d movement
    - clones 7d-over-7d movement
    - latest-day views spike/drop versus trailing median baseline
    - repo growth conversion and anomaly candidates when repo-metrics.csv data
      is provided.

    Returns up to ``limit`` strings. When there is not enough signal,
    callers should render a simple "needs more data" note.
    """
    if isinstance(metric_rows, int) and growth is None:
        limit = metric_rows
        metric_rows = None

    if limit <= 0:
        return []

    by_repo = defaultdict(list)
    for row in daily_rows:
        by_repo[row["repo"]].append(row)

    candidates = []
    for repo, rows in by_repo.items():
        rows = sorted(rows, key=lambda x: x["ts"])
        views = [int(r.get("views_count", 0)) for r in rows]
        clones = [int(r.get("clones_count", 0)) for r in rows]

        view_change = _window_change_candidate(
            repo=repo,
            metric="views",
            values=views,
            min_floor=10,
        )
        if view_change:
            candidates.append(view_change)

        clone_change = _window_change_candidate(
            repo=repo,
            metric="clones",
            values=clones,
            min_floor=4,
        )
        if clone_change:
            candidates.append(clone_change)

        spike = _spike_candidate(repo=repo, metric="views", values=views)
        if spike:
            candidates.append(spike)

    candidates.extend(_growth_insight_candidates(daily_rows, metric_rows, growth))

    candidates.sort(key=lambda x: x["score"], reverse=True)

    insights = []
    seen_text = set()
    seen_repos = set()

    # First pass: diversify across repos.
    for item in candidates:
        text = item["text"]
        repo = item["repo"]
        if text in seen_text or repo in seen_repos:
            continue
        insights.append(text)
        seen_text.add(text)
        seen_repos.add(repo)
        if len(insights) >= limit:
            return insights

    # Second pass: allow additional items from already-selected repos.
    for item in candidates:
        text = item["text"]
        if text in seen_text:
            continue
        insights.append(text)
        seen_text.add(text)
        if len(insights) >= limit:
            return insights

    return insights[:limit]


def actionable_insights_structured(
    daily_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]] | int | None = None,
    limit: int = 3,
    growth: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return ranked, structured insight objects for rich UIs.

    Mirrors actionable_insights() ranking and diversification but yields
    dicts with kind/metric/repo/delta/pct/etc. so dashboards can render
    them as cards rather than parsing pre-formatted strings.
    """
    if isinstance(metric_rows, int) and growth is None:
        limit = metric_rows
        metric_rows = None

    if limit <= 0:
        return []

    by_repo = defaultdict(list)
    for row in daily_rows:
        by_repo[row["repo"]].append(row)

    candidates = []
    for repo, rows in by_repo.items():
        rows = sorted(rows, key=lambda x: x["ts"])
        views = [int(r.get("views_count", 0)) for r in rows]
        clones = [int(r.get("clones_count", 0)) for r in rows]

        view_change = _window_change_candidate(repo=repo, metric="views", values=views, min_floor=10)
        if view_change:
            candidates.append(view_change)

        clone_change = _window_change_candidate(repo=repo, metric="clones", values=clones, min_floor=4)
        if clone_change:
            candidates.append(clone_change)

        spike = _spike_candidate(repo=repo, metric="views", values=views)
        if spike:
            candidates.append(spike)

    candidates.extend(_growth_insight_candidates(daily_rows, metric_rows, growth))

    candidates.sort(key=lambda x: x["score"], reverse=True)

    out: list[dict] = []
    seen_text: set[str] = set()
    seen_repos: set[str] = set()

    for item in candidates:
        if item["text"] in seen_text or item["repo"] in seen_repos:
            continue
        out.append(_strip_score(item))
        seen_text.add(item["text"])
        seen_repos.add(item["repo"])
        if len(out) >= limit:
            return out

    for item in candidates:
        if item["text"] in seen_text:
            continue
        out.append(_strip_score(item))
        seen_text.add(item["text"])
        if len(out) >= limit:
            return out

    return out[:limit]


def _strip_score(item: dict) -> dict:
    return {k: v for k, v in item.items() if k != "score"}


def _add_growth_candidate(candidates, *, repo, subtype, metric, score, text, **extra):
    candidates.append({
        "score": score,
        "repo": repo,
        "kind": "growth",
        "subtype": subtype,
        "metric": metric,
        "text": text,
        **extra,
    })


def _growth_insight_candidates(daily_rows, metric_rows=None, growth=None):
    """Return cross-signal insight candidates with volume/sample guards."""
    if growth is None:
        if metric_rows is None:
            return []
        growth = growth_analytics(daily_rows, metric_rows)

    candidates = []
    per_repo = growth.get("per_repo", {})
    for repo, row in per_repo.items():
        traffic = row.get("traffic", {})
        deltas = row.get("deltas", {})
        conversions = row.get("conversion", {})
        metric_samples = int(deltas.get("sample_count", 0) or 0)
        traffic_samples = int(traffic.get("sample_count", 0) or 0)
        views = int(traffic.get("views", 0) or 0)
        visitors = int(traffic.get("uniques", 0) or 0)
        clones = int(traffic.get("clones", 0) or 0)
        downstream = (
            int(deltas.get("stargazers_delta", 0) or 0)
            + int(deltas.get("subscribers_delta", 0) or 0)
            + int(deltas.get("forks_delta", 0) or 0)
        )

        enough_for_growth = metric_samples >= 2
        enough_for_cross_signal = enough_for_growth and traffic_samples >= 3

        if enough_for_cross_signal and views >= 50 and visitors >= 10 and downstream <= 0:
            score = math.log1p(views) + math.log1p(visitors)
            _add_growth_candidate(
                candidates,
                repo=repo,
                subtype="high_attention_low_interest",
                metric="growth",
                score=score,
                traffic=views,
                visitors=visitors,
                downstream_delta=downstream,
                text=(
                    f"`{repo}` drew {views:,} views and {visitors:,} visitors " +
                    "without downstream growth in the selected window."
                ),
            )

        if enough_for_cross_signal and downstream >= 2 and views < 30:
            score = math.log1p(downstream) * 2.0 + max(0, 30 - views) / 30
            _add_growth_candidate(
                candidates,
                repo=repo,
                subtype="quiet_resonance",
                metric="growth",
                score=score,
                traffic=views,
                downstream_delta=downstream,
                text=(
                    f"`{repo}` added {downstream:+,} downstream signals on only " +
                    f"{views:,} views."
                ),
            )

        star_delta = int(deltas.get("stargazers_delta", 0) or 0)
        clone_ratio = clones / max(views, 1)
        if enough_for_cross_signal and clones >= 12 and clone_ratio >= 0.35 and star_delta <= 0:
            score = math.log1p(clones) * (1.0 + min(clone_ratio, 2.0))
            _add_growth_candidate(
                candidates,
                repo=repo,
                subtype="clone_heavy_star_light",
                metric="clones",
                score=score,
                clones=clones,
                stargazers_delta=star_delta,
                text=(
                    f"`{repo}` is clone-heavy but star-light " +
                    f"({clones:,} clones, {star_delta:+,} stars)."
                ),
            )

        fork_delta = int(deltas.get("forks_delta", 0) or 0)
        fork_conversion = conversions.get("forks", {})
        if enough_for_growth and fork_delta >= 2:
            denom = fork_conversion.get("denominator", 0) or 0
            conversion = fork_conversion.get("value")
            score = math.log1p(fork_delta) * 2.4
            if denom >= 10 and conversion is not None:
                score *= 1.0 + min(abs(conversion), 0.5)
            _add_growth_candidate(
                candidates,
                repo=repo,
                subtype="fork_spike",
                metric="forks",
                score=score,
                delta=fork_delta,
                denominator=denom,
                text=f"`{repo}` forks jumped {fork_delta:+,} in the selected window.",
            )

        subscriber_delta = int(deltas.get("subscribers_delta", 0) or 0)
        subscriber_conversion = conversions.get("subscribers", {})
        if enough_for_growth and subscriber_delta >= 3:
            denom = subscriber_conversion.get("denominator", 0) or 0
            conversion = subscriber_conversion.get("value")
            score = math.log1p(subscriber_delta) * 2.0
            if denom >= 10 and conversion is not None:
                score *= 1.0 + min(abs(conversion), 0.4)
            _add_growth_candidate(
                candidates,
                repo=repo,
                subtype="watcher_subscriber_spike",
                metric="subscribers",
                score=score,
                delta=subscriber_delta,
                denominator=denom,
                text=(
                    f"`{repo}` watchers rose {subscriber_delta:+,} " +
                    "in the selected window."
                ),
            )

        if enough_for_cross_signal and views >= 80 and downstream <= 0:
            score = math.log1p(views) * 1.4
            _add_growth_candidate(
                candidates,
                repo=repo,
                subtype="traffic_without_downstream_growth",
                metric="views",
                score=score,
                traffic=views,
                downstream_delta=downstream,
                text=(
                    f"`{repo}` had a traffic spike shape ({views:,} views) " +
                    "without stars, watchers, or forks moving."
                ),
            )

        if enough_for_cross_signal and downstream >= 3 and views < 40:
            score = math.log1p(downstream) * 2.2
            _add_growth_candidate(
                candidates,
                repo=repo,
                subtype="downstream_without_traffic_spike",
                metric="growth",
                score=score,
                traffic=views,
                downstream_delta=downstream,
                text=(
                    f"`{repo}` gained {downstream:+,} downstream signals without " +
                    f"a matching traffic spike ({views:,} views)."
                ),
            )

        negatives = {
            "stars": star_delta,
            "subscribers": subscriber_delta,
            "forks": fork_delta,
        }
        for metric, delta in negatives.items():
            if enough_for_growth and delta < 0:
                _add_growth_candidate(
                    candidates,
                    repo=repo,
                    subtype="negative_counter_movement",
                    metric=metric,
                    score=math.log1p(abs(delta)) * 3.0,
                    delta=delta,
                    text=f"`{repo}` {metric} moved backward {delta:+,} in the selected window.",
                )

    return candidates


def _window_change_candidate(repo, metric, values, min_floor):
    """Build a 7d-over-7d candidate for one metric series."""
    if len(values) < 6:
        return None

    window = min(7, len(values) // 2)
    if window < 3:
        return None

    prev = sum(values[-2 * window:-window])
    curr = sum(values[-window:])
    delta = curr - prev
    abs_delta = abs(delta)
    total_floor = max(prev, curr)

    if abs_delta == 0:
        return None
    if total_floor < min_floor and abs_delta < max(2, min_floor // 2):
        return None

    if prev == 0:
        pct_text = "new activity"
        pct_factor = 1.5
        pct_value = None
    else:
        pct = (delta / prev) * 100.0
        pct_text = f"{pct:+.0f}%"
        pct_factor = 1.0 + min(abs(pct) / 100.0, 2.0)
        pct_value = pct

    score = math.log1p(abs_delta) * pct_factor
    return {
        "score": score,
        "repo": repo,
        "kind": "trend",
        "metric": metric,
        "window_days": window,
        "prior": prev,
        "current": curr,
        "delta": delta,
        "pct": pct_value,
        "text": (
            f"`{repo}` {metric} {pct_text} over the last {window}d " +
            f"({prev:,} -> {curr:,}, {delta:+,})."
        ),
    }


def _spike_candidate(repo, metric, values):
    """Build a daily spike/drop candidate using trailing median + MAD."""
    if len(values) < 8:
        return None

    latest = values[-1]
    baseline = values[-15:-1] if len(values) > 15 else values[:-1]
    if len(baseline) < 5:
        return None

    median = statistics.median(baseline)
    deviation = [abs(v - median) for v in baseline]
    mad = statistics.median(deviation) if deviation else 0
    delta = latest - median
    abs_delta = abs(delta)

    if abs_delta < max(5, median * 0.5):
        return None

    dispersion = mad if mad >= 1 else max(median, 1)
    z_like = abs_delta / dispersion
    if z_like < 2.0:
        return None

    direction = "spiked" if delta > 0 else "dropped"
    score = math.log1p(abs_delta) + z_like
    return {
        "score": score,
        "repo": repo,
        "kind": "spike",
        "metric": metric,
        "direction": direction,
        "current": latest,
        "baseline": median,
        "delta": delta,
        "text": (
            f"`{repo}` {metric} {direction} versus baseline " +
            f"(latest {latest:,} vs trailing median {median:.0f})."
        ),
    }
