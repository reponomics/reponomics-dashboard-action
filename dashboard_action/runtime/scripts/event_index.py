"""Derived repository event spine for contextual dashboard insights."""

from __future__ import annotations

from typing import Any

from storage import SCHEMA_VERSION

Rows = list[dict[str, Any]]


def event_index_rows(commit_rows: Rows, release_rows: Rows) -> Rows:
    """Return normalized event rows derived from retained context tables."""
    rows = [
        *(_commit_event(row) for row in commit_rows if row.get("repo") and row.get("sha")),
        *(
            _release_event(row)
            for row in release_rows
            if row.get("repo") and row.get("release_id")
        ),
    ]
    return sorted(rows, key=lambda row: (row["repo"], row["event_date"], row["event_id"]))


def _commit_event(row: dict[str, Any]) -> dict[str, Any]:
    sha = str(row.get("sha", ""))
    repo = str(row.get("repo", ""))
    event_ts = str(row.get("committed_at") or row.get("captured_at") or "")
    return _event_row(
        repo=repo,
        event_id=f"commit:{sha}",
        event_type="commit",
        event_ts=event_ts,
        title=str(row.get("message_subject") or sha[:12]),
        url=f"https://github.com/{repo}/commit/{sha}" if repo and sha else "",
        primary_sha=sha,
        release_id="",
        issue_or_pr_number=str(row.get("associated_pr_number") or ""),
        magnitude=_int(row.get("additions")) + _int(row.get("deletions")),
        classification=str(row.get("classification") or "unknown"),
        source_table="repo-commits.csv",
        captured_at=str(row.get("captured_at") or ""),
    )


def _release_event(row: dict[str, Any]) -> dict[str, Any]:
    release_id = str(row.get("release_id", ""))
    tag_name = str(row.get("tag_name") or "")
    event_ts = str(row.get("published_at") or row.get("created_at") or row.get("captured_at") or "")
    return _event_row(
        repo=str(row.get("repo") or ""),
        event_id=f"release:{release_id}",
        event_type="release",
        event_ts=event_ts,
        title=str(row.get("name") or tag_name or f"Release {release_id}"),
        url=str(row.get("html_url") or ""),
        primary_sha=str(row.get("target_sha") or ""),
        release_id=release_id,
        issue_or_pr_number="",
        magnitude=_int(row.get("asset_download_count")) or _int(row.get("asset_count")),
        classification="release",
        source_table="repo-releases.csv",
        captured_at=str(row.get("captured_at") or ""),
    )


def _event_row(
    *,
    repo: str,
    event_id: str,
    event_type: str,
    event_ts: str,
    title: str,
    url: str,
    primary_sha: str,
    release_id: str,
    issue_or_pr_number: str,
    magnitude: int,
    classification: str,
    source_table: str,
    captured_at: str,
) -> dict[str, Any]:
    return {
        "repo": repo,
        "event_id": event_id,
        "event_type": event_type,
        "event_ts": event_ts,
        "event_date": event_ts[:10] if event_ts else "",
        "title": title,
        "url": url,
        "primary_sha": primary_sha,
        "release_id": release_id,
        "issue_or_pr_number": issue_or_pr_number,
        "magnitude": magnitude,
        "classification": classification,
        "source_table": source_table,
        "captured_at": captured_at,
        "schema_version": SCHEMA_VERSION,
    }


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
