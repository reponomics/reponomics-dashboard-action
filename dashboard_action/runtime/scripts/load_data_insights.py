"""Actionable insight ranking for dashboard data."""

from collections import defaultdict
from typing import Any

from load_data_growth_insights import _growth_insight_candidates
from load_data_trend_insights import _spike_candidate, _window_change_candidate


def actionable_insights(
    daily_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]] | int | None = None,
    limit: int = 3,
    growth: dict[str, Any] | None = None,
) -> list[str]:
    """Return ranked, lightweight insight bullets from per-repo daily metrics."""
    metric_rows, limit = _normalize_insight_args(metric_rows, limit, growth)
    if limit <= 0:
        return []

    candidates = _ranked_insight_candidates(daily_rows, metric_rows, growth)
    return [item["text"] for item in _diversified_candidates(candidates, limit)]


def actionable_insights_structured(
    daily_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]] | int | None = None,
    limit: int = 3,
    growth: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return ranked, structured insight objects for rich UIs."""
    metric_rows, limit = _normalize_insight_args(metric_rows, limit, growth)
    if limit <= 0:
        return []

    candidates = _ranked_insight_candidates(daily_rows, metric_rows, growth)
    return [_strip_score(item) for item in _diversified_candidates(candidates, limit)]


def _normalize_insight_args(metric_rows, limit, growth):
    if isinstance(metric_rows, int) and growth is None:
        return None, metric_rows
    return metric_rows, limit


def _ranked_insight_candidates(daily_rows, metric_rows, growth):
    candidates = _traffic_insight_candidates(daily_rows)
    candidates.extend(_growth_insight_candidates(daily_rows, metric_rows, growth))
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates


def _traffic_insight_candidates(daily_rows):
    candidates = []
    for repo, rows in _daily_rows_by_repo(daily_rows).items():
        candidates.extend(_repo_traffic_candidates(repo, rows))
    return candidates


def _daily_rows_by_repo(daily_rows):
    by_repo = defaultdict(list)
    for row in daily_rows:
        by_repo[row["repo"]].append(row)
    return by_repo


def _repo_traffic_candidates(repo, rows):
    rows = sorted(rows, key=lambda x: x["ts"])
    views = [int(row.get("views_count", 0)) for row in rows]
    clones = [int(row.get("clones_count", 0)) for row in rows]
    return [
        item
        for item in (
            _window_change_candidate(repo, "views", views, min_floor=10),
            _window_change_candidate(repo, "clones", clones, min_floor=4),
            _spike_candidate(repo, "views", views),
        )
        if item
    ]


def _diversified_candidates(candidates, limit):
    selected = []
    seen_text = set()
    seen_repos = set()
    _select_diverse_candidates(candidates, selected, seen_text, seen_repos, limit)
    _select_remaining_candidates(candidates, selected, seen_text, limit)
    return selected[:limit]


def _select_diverse_candidates(candidates, selected, seen_text, seen_repos, limit):
    for item in candidates:
        if item["text"] in seen_text or item["repo"] in seen_repos:
            continue
        selected.append(item)
        seen_text.add(item["text"])
        seen_repos.add(item["repo"])
        if len(selected) >= limit:
            return


def _select_remaining_candidates(candidates, selected, seen_text, limit):
    for item in candidates:
        if item["text"] in seen_text:
            continue
        selected.append(item)
        seen_text.add(item["text"])
        if len(selected) >= limit:
            return


def _strip_score(item: dict) -> dict:
    return {key: value for key, value in item.items() if key != "score"}
