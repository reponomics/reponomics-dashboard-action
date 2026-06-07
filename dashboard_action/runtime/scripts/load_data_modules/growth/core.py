"""Repository growth deltas and conversion analytics."""

from load_data_modules.constants import GROWTH_COUNTERS
from load_data_modules.daily import _empty_traffic_totals, _traffic_totals_by_repo
from load_data_modules.dates import _latest_date_from_rows, _window_cutoff
from load_data_modules.repo_metrics import (
    aggregate_repo_metrics,
    latest_repo_metrics_per_day,
    repo_growth_series,
)
from load_data_modules.types import Result, Rows

EMPTY_REPO_DELTA: Result = {
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
}


def repo_metric_deltas(metric_rows: Rows, recent_days: int = 14) -> Result:
    """Return per-repo and aggregate net counter changes in the recent window."""
    if not metric_rows:
        return _empty_delta_summary()

    cutoff = _window_cutoff(_latest_date_from_rows(metric_rows), recent_days)
    by_repo: dict[str, Result] = {}
    totals = _empty_delta_totals()
    for repo, rows in latest_repo_metrics_per_day(metric_rows).items():
        repo_delta = _repo_delta_for_window(rows, cutoff)
        if repo_delta is None:
            continue
        by_repo[repo] = repo_delta
        _add_repo_delta_totals(totals, repo_delta)

    return {"repos": by_repo, **totals}


def _empty_delta_totals() -> dict[str, int]:
    """Return zeroed aggregate delta counters."""
    return {
        "total_stargazers_delta": 0,
        "total_stars_delta": 0,
        "total_subscribers_delta": 0,
        "total_forks_delta": 0,
    }


def _empty_delta_summary() -> Result:
    return {"repos": {}, **_empty_delta_totals()}


def _repo_delta_for_window(rows: list[Result], cutoff: str | None) -> Result | None:
    """Compute observed counter deltas from the first and last rows in a window."""
    window_rows = [row for row in rows if not cutoff or row.get("ts", "") >= cutoff]
    if not window_rows:
        return None

    first = window_rows[0]
    last = window_rows[-1]
    return {
        "stargazers_delta": _observed_delta(window_rows, "stargazers_count"),
        "stars_delta": _observed_delta(window_rows, "stargazers_count"),
        "subscribers_delta": _observed_delta(window_rows, "subscribers_count"),
        "forks_delta": _observed_delta(window_rows, "forks_count"),
        "sample_count": len(window_rows),
        "start_date": first.get("ts", ""),
        "end_date": last.get("ts", ""),
        "current_stargazers": int(last.get("stargazers_count", 0) or 0),
        "current_stars": int(last.get("stargazers_count", 0) or 0),
        "current_subscribers": int(last.get("subscribers_count", 0) or 0),
        "current_forks": int(last.get("forks_count", 0) or 0),
    }


def _observed_delta(rows: list[Result], field: str) -> int:
    """Return the net delta using only rows where the source counter was observed."""
    observed = [row for row in rows if row.get(f"{field}_observed", True)]
    if len(observed) < 2:
        return 0
    return int(observed[-1].get(field, 0) or 0) - int(observed[0].get(field, 0) or 0)


def _add_repo_delta_totals(totals: dict[str, int], repo_delta: Result) -> None:
    totals["total_stargazers_delta"] += repo_delta["stargazers_delta"]
    totals["total_stars_delta"] += repo_delta["stars_delta"]
    totals["total_subscribers_delta"] += repo_delta["subscribers_delta"]
    totals["total_forks_delta"] += repo_delta["forks_delta"]


def _safe_ratio(
    numerator: int,
    preferred_denominator: int,
    fallback_denominator: int,
    *,
    min_denominator: int = 5,
) -> Result:
    """Compute conversion ratio, preferring visitors but falling back to views."""
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


def growth_analytics(daily_rows: Rows, metric_rows: Rows, recent_days: int = 14) -> Result:
    """Compute shared growth totals, deltas, ratios, and per-repo series."""
    latest_ts = _latest_date_from_rows(daily_rows, metric_rows)
    cutoff = _window_cutoff(latest_ts, recent_days)
    current = aggregate_repo_metrics(metric_rows)
    deltas = repo_metric_deltas(metric_rows, recent_days=recent_days)
    series = repo_growth_series(metric_rows)
    traffic = _traffic_totals_by_repo(daily_rows, cutoff=cutoff)

    return {
        "window_days": recent_days,
        "cutoff": cutoff,
        "latest_date": latest_ts,
        "current": current,
        "deltas": deltas,
        "series": series,
        "per_repo": _per_repo_growth(current, traffic, deltas, series),
        "totals": _growth_totals(current, deltas),
    }


def _per_repo_growth(
    current: Result,
    traffic: dict[str, dict[str, int]],
    deltas: Result,
    series: dict[str, Result],
) -> dict[str, Result]:
    repos = sorted(set(current["repos"]) | set(traffic) | set(deltas["repos"]))
    return {repo: _growth_row(repo, traffic, deltas, series) for repo in repos}


def _growth_row(
    repo: str,
    traffic: dict[str, dict[str, int]],
    deltas: Result,
    series: dict[str, Result],
) -> Result:
    """Join traffic, deltas, conversions, and time series for one repo."""
    repo_delta = deltas["repos"].get(repo, dict(EMPTY_REPO_DELTA))
    traffic_totals = traffic.get(repo, _empty_traffic_totals())
    return {
        "repo": repo,
        "traffic": traffic_totals,
        "deltas": repo_delta,
        "conversion": _growth_conversions(repo_delta, traffic_totals),
        "series": series.get(
            repo,
            {"dates": [], "stargazers": [], "subscribers": [], "forks": [], "samples": 0},
        ),
    }


def _growth_conversions(delta: Result, traffic_totals: dict[str, int]) -> Result:
    """Compute per-counter conversion ratios for a repo's growth deltas."""
    conversions = {
        metric: _safe_ratio(
            delta.get(f"{metric}_delta", 0),
            traffic_totals["uniques"],
            traffic_totals["views"],
        )
        for metric in GROWTH_COUNTERS
    }
    conversions["stars"] = conversions["stargazers"]
    return conversions


def _growth_totals(current: Result, deltas: Result) -> Result:
    return {
        "total_stargazers": current["total_stargazers"],
        "total_stars": current["total_stars"],
        "total_subscribers": current["total_subscribers"],
        "total_forks": current["total_forks"],
        "total_stargazers_delta": deltas["total_stargazers_delta"],
        "total_stars_delta": deltas["total_stars_delta"],
        "total_subscribers_delta": deltas["total_subscribers_delta"],
        "total_forks_delta": deltas["total_forks_delta"],
    }
