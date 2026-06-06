"""Actionable insight ranking for dashboard data."""

from collections import defaultdict

from load_data_modules.growth.insights import _growth_insight_candidates
from load_data_modules.types import Candidate, Rows
from load_data_modules.trend_insights import _spike_candidate, _window_change_candidate


def actionable_insights(
    daily_rows: Rows,
    metric_rows: Rows | int | None = None,
    limit: int = 3,
    growth: Candidate | None = None,
) -> list[str]:
    """Return ranked, lightweight insight bullets from per-repo daily metrics."""
    metric_rows, limit = _normalize_insight_args(metric_rows, limit, growth)
    if limit <= 0:
        return []

    candidates = _ranked_insight_candidates(daily_rows, metric_rows, growth)
    return [item["text"] for item in _diversified_candidates(candidates, limit)]


def actionable_insights_structured(
    daily_rows: Rows,
    metric_rows: Rows | int | None = None,
    limit: int = 3,
    growth: Candidate | None = None,
) -> list[Candidate]:
    """Return ranked, structured insight objects for rich UIs."""
    metric_rows, limit = _normalize_insight_args(metric_rows, limit, growth)
    if limit <= 0:
        return []

    candidates = _ranked_insight_candidates(daily_rows, metric_rows, growth)
    return [_strip_score(item) for item in _diversified_candidates(candidates, limit)]


def _normalize_insight_args(
    metric_rows: Rows | int | None, limit: int, growth: Candidate | None
) -> tuple[Rows | None, int]:
    """Preserve the legacy ``actionable_insights(rows, limit)`` call shape."""
    if isinstance(metric_rows, int) and growth is None:
        return None, metric_rows
    if isinstance(metric_rows, int):
        return None, limit
    return metric_rows, limit


def _ranked_insight_candidates(
    daily_rows: Rows, metric_rows: Rows | None, growth: Candidate | None
) -> list[Candidate]:
    """Build and sort traffic and growth candidates by descending score."""
    candidates = _traffic_insight_candidates(daily_rows)
    candidates.extend(_growth_insight_candidates(daily_rows, metric_rows, growth))
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates


def _traffic_insight_candidates(daily_rows: Rows) -> list[Candidate]:
    candidates: list[Candidate] = []
    for repo, rows in _daily_rows_by_repo(daily_rows).items():
        candidates.extend(_repo_traffic_candidates(repo, rows))
    return candidates


def _daily_rows_by_repo(daily_rows: Rows) -> dict[str, Rows]:
    by_repo: defaultdict[str, Rows] = defaultdict(list)
    for row in daily_rows:
        by_repo[row["repo"]].append(row)
    return by_repo


def _repo_traffic_candidates(repo: str, rows: Rows) -> list[Candidate]:
    """Return traffic trend/spike candidates for one repo's ordered daily rows."""
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


def _diversified_candidates(candidates: list[Candidate], limit: int) -> list[Candidate]:
    """Prefer distinct repos first, then backfill by score without duplicate text."""
    selected: list[Candidate] = []
    seen_text: set[str] = set()
    seen_repos: set[str] = set()
    _select_diverse_candidates(candidates, selected, seen_text, seen_repos, limit)
    _select_remaining_candidates(candidates, selected, seen_text, limit)
    return selected[:limit]


def _select_diverse_candidates(
    candidates: list[Candidate],
    selected: list[Candidate],
    seen_text: set[str],
    seen_repos: set[str],
    limit: int,
) -> None:
    for item in candidates:
        if item["text"] in seen_text or item["repo"] in seen_repos:
            continue
        selected.append(item)
        seen_text.add(item["text"])
        seen_repos.add(item["repo"])
        if len(selected) >= limit:
            return


def _select_remaining_candidates(
    candidates: list[Candidate],
    selected: list[Candidate],
    seen_text: set[str],
    limit: int,
) -> None:
    for item in candidates:
        if item["text"] in seen_text:
            continue
        selected.append(item)
        seen_text.add(item["text"])
        if len(selected) >= limit:
            return


def _strip_score(item: Candidate) -> Candidate:
    return {key: value for key, value in item.items() if key != "score"}
