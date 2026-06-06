"""Traffic endpoint row shaping for views, clones, referrers, and paths."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from collect_modules.types import Headers
from storage import SCHEMA_VERSION


def collect_views_clones(
    repo: str,
    headers: Headers,
    captured_at: str,
    *,
    fetch_json: Callable[..., Any],
) -> list[dict[str, Any]]:
    """Fetch views and clones and return per-day rows for the log."""
    base = f"https://api.github.com/repos/{repo}/traffic"
    views_data = fetch_json(f"{base}/views", headers, allow_not_found=True)
    clones_data = fetch_json(f"{base}/clones", headers, allow_not_found=True)
    return _traffic_rows(repo, captured_at, views_data, clones_data)


def _traffic_rows(
    repo: str,
    captured_at: str,
    views_data: dict[str, Any],
    clones_data: dict[str, Any],
) -> list[dict[str, Any]]:
    clones_by_date = _clones_by_date(clones_data)
    rows = [
        _traffic_row(repo, entry["timestamp"][:10], captured_at, entry, clones_by_date)
        for entry in views_data.get("views", [])
    ]
    rows.extend(
        _clone_only_row(repo, ts, captured_at, clone_entry)
        for ts, clone_entry in clones_by_date.items()
    )
    return rows


def _clones_by_date(clones_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["timestamp"][:10]: entry for entry in clones_data.get("clones", [])}


def _traffic_row(
    repo: str,
    ts: str,
    captured_at: str,
    view_entry: dict[str, Any],
    clones_by_date: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    clone_entry = clones_by_date.pop(ts, {})
    return _traffic_artifact_row(
        repo,
        ts,
        captured_at,
        views_count=view_entry.get("count", 0),
        views_uniques=view_entry.get("uniques", 0),
        clones_count=clone_entry.get("count", 0),
        clones_uniques=clone_entry.get("uniques", 0),
    )


def _clone_only_row(
    repo: str,
    ts: str,
    captured_at: str,
    clone_entry: dict[str, Any],
) -> dict[str, Any]:
    return _traffic_artifact_row(
        repo,
        ts,
        captured_at,
        views_count=0,
        views_uniques=0,
        clones_count=clone_entry.get("count", 0),
        clones_uniques=clone_entry.get("uniques", 0),
    )


def _traffic_artifact_row(
    repo: str,
    ts: str,
    captured_at: str,
    *,
    views_count: int,
    views_uniques: int,
    clones_count: int,
    clones_uniques: int,
) -> dict[str, Any]:
    return {
        "repo": repo,
        "ts": ts,
        "views_count": views_count,
        "views_uniques": views_uniques,
        "clones_count": clones_count,
        "clones_uniques": clones_uniques,
        "captured_at": captured_at,
        "source": "api",
        "schema_version": SCHEMA_VERSION,
    }


def collect_referrers(
    repo: str,
    headers: Headers,
    captured_at: str,
    *,
    fetch_json: Callable[..., Any],
) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/traffic/popular/referrers"
    data = fetch_json(url, headers, allow_not_found=True)
    return [
        {
            "repo": repo,
            "captured_at": captured_at,
            "referrer": item.get("referrer", ""),
            "count": item.get("count", 0),
            "uniques": item.get("uniques", 0),
            "schema_version": SCHEMA_VERSION,
        }
        for item in data
    ]


def collect_paths(
    repo: str,
    headers: Headers,
    captured_at: str,
    *,
    fetch_json: Callable[..., Any],
) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/traffic/popular/paths"
    data = fetch_json(url, headers, allow_not_found=True)
    return [
        {
            "repo": repo,
            "captured_at": captured_at,
            "path": item.get("path", ""),
            "title": item.get("title", ""),
            "count": item.get("count", 0),
            "uniques": item.get("uniques", 0),
            "schema_version": SCHEMA_VERSION,
        }
        for item in data
    ]
