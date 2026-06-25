"""Grouping helpers for retained narrative evidence rows."""

from __future__ import annotations

from collections import defaultdict

from load_data_modules.narrative_values import int_value
from load_data_modules.types import Row, Rows


def rows_by_repo(rows: Rows) -> dict[str, Rows]:
    """Group retained rows by repository."""
    grouped: dict[str, Rows] = defaultdict(list)
    for row in rows:
        repo = str(row.get("repo") or "")
        if repo:
            grouped[repo].append(row)
    return dict(grouped)


def latest_row_by_repo(rows: Rows) -> dict[str, Row]:
    """Return latest captured row for each repository."""
    latest: dict[str, Row] = {}
    latest_capture: dict[str, str] = {}
    for row in rows:
        repo = str(row.get("repo") or "")
        captured_at = str(row.get("captured_at") or row.get("ts") or "")
        if repo and captured_at >= latest_capture.get(repo, ""):
            latest[repo] = row
            latest_capture[repo] = captured_at
    return latest


def latest_snapshot_by_repo(rows: Rows) -> dict[str, Rows]:
    """Return latest snapshot row set for each repository."""
    latest_capture = latest_capture_by_repo(rows)
    grouped: dict[str, Rows] = defaultdict(list)
    for row in rows:
        repo = str(row.get("repo") or "")
        if repo and str(row.get("captured_at") or "") == latest_capture.get(repo):
            grouped[repo].append(row)
    return dict(grouped)


def previous_snapshot_by_repo(rows: Rows) -> dict[str, Rows]:
    """Return snapshot row set immediately before the latest capture per repo."""
    previous_capture = previous_capture_by_repo(rows)
    grouped: dict[str, Rows] = defaultdict(list)
    for row in rows:
        repo = str(row.get("repo") or "")
        if repo and str(row.get("captured_at") or "") == previous_capture.get(repo):
            grouped[repo].append(row)
    return dict(grouped)


def latest_capture_by_repo(rows: Rows) -> dict[str, str]:
    """Return latest captured_at value for each repository."""
    latest: dict[str, str] = {}
    for row in rows:
        repo = str(row.get("repo") or "")
        captured_at = str(row.get("captured_at") or "")
        if repo and captured_at >= latest.get(repo, ""):
            latest[repo] = captured_at
    return latest


def previous_capture_by_repo(rows: Rows) -> dict[str, str]:
    """Return the previous captured_at value for each repository."""
    captures: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        repo = str(row.get("repo") or "")
        captured_at = str(row.get("captured_at") or "")
        if repo and captured_at:
            captures[repo].add(captured_at)
    previous: dict[str, str] = {}
    for repo, values in captures.items():
        ordered = sorted(values)
        if len(ordered) >= 2:
            previous[repo] = ordered[-2]
    return previous


def rows_by_repo_week(rows: Rows) -> dict[str, Rows]:
    """Group weekly retained rows by repository in chronological order."""
    grouped = rows_by_repo(rows)
    return {
        repo: sorted(items, key=lambda row: str(row.get("week_start") or ""))
        for repo, items in grouped.items()
    }


def release_assets_by_release(rows: Rows) -> dict[tuple[str, str], Rows]:
    """Group release assets by repository and release id."""
    grouped: dict[tuple[str, str], Rows] = defaultdict(list)
    for row in rows:
        repo = str(row.get("repo") or "")
        release_id = str(row.get("release_id") or "")
        if repo and release_id:
            grouped[(repo, release_id)].append(row)
    return dict(grouped)


def latest_label_buckets(rows: Rows) -> dict[str, dict[str, int]]:
    """Return latest label-bucket counts keyed by repo."""
    latest = latest_snapshot_by_repo(rows)
    return {repo: label_bucket_counts(repo_rows) for repo, repo_rows in latest.items()}


def label_bucket_counts(rows: Rows) -> dict[str, int]:
    """Aggregate sampled issue/PR label buckets."""
    buckets: dict[str, int] = defaultdict(int)
    for row in rows:
        bucket = str(row.get("label_bucket") or "")
        if bucket:
            buckets[bucket] += int_value(row.get("labeled_item_count"))
    return dict(buckets)
