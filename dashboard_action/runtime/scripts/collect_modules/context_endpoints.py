"""GitHub context endpoint shaping for richer repository narratives."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

import requests

from collect_modules.types import Headers
from storage import SCHEMA_VERSION


def collect_release_context(
    repo: str,
    headers: Headers,
    captured_at: str,
    *,
    fetch_json: Callable[..., Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch releases and return release plus release-asset rows."""
    url = f"https://api.github.com/repos/{repo}/releases?per_page=100"
    data = fetch_json(url, headers)
    if not isinstance(data, list):
        raise requests.HTTPError(
            f"Unexpected releases response for {repo}: {type(data).__name__}"
        )
    release_rows: list[dict[str, Any]] = []
    asset_rows: list[dict[str, Any]] = []
    for release in data:
        if not isinstance(release, dict):
            continue
        release_rows.append(_release_row(repo, release, captured_at))
        asset_rows.extend(_release_asset_rows(repo, release, captured_at))
    return release_rows, asset_rows


def _release_row(repo: str, release: dict[str, Any], captured_at: str) -> dict[str, Any]:
    assets = release.get("assets")
    if not isinstance(assets, list):
        assets = []
    return {
        "repo": repo,
        "release_id": release.get("id", ""),
        "node_id": release.get("node_id", ""),
        "tag_name": release.get("tag_name", ""),
        "target_commitish": release.get("target_commitish", ""),
        "target_sha": "",
        "name": release.get("name", ""),
        "draft": release.get("draft", ""),
        "prerelease": release.get("prerelease", ""),
        "immutable": release.get("immutable", ""),
        "created_at": release.get("created_at", ""),
        "published_at": release.get("published_at", ""),
        "author_login": _login(release.get("author")),
        "html_url": release.get("html_url", ""),
        "asset_count": len(assets),
        "asset_download_count": sum(_int(asset.get("download_count")) for asset in assets),
        "body_hash": _hash_text(str(release.get("body") or "").strip()),
        "captured_at": captured_at,
        "schema_version": SCHEMA_VERSION,
    }


def _release_asset_rows(
    repo: str,
    release: dict[str, Any],
    captured_at: str,
) -> list[dict[str, Any]]:
    release_id = release.get("id", "")
    assets = release.get("assets")
    if not isinstance(assets, list):
        return []
    return [
        {
            "repo": repo,
            "release_id": release_id,
            "asset_id": asset.get("id", ""),
            "name": asset.get("name", ""),
            "label": asset.get("label", ""),
            "content_type": asset.get("content_type", ""),
            "state": asset.get("state", ""),
            "size_bytes": asset.get("size", ""),
            "download_count": asset.get("download_count", 0),
            "created_at": asset.get("created_at", ""),
            "updated_at": asset.get("updated_at", ""),
            "browser_download_url": asset.get("browser_download_url", ""),
            "captured_at": captured_at,
            "schema_version": SCHEMA_VERSION,
        }
        for asset in assets
        if isinstance(asset, dict)
    ]


def collect_languages(
    repo: str,
    headers: Headers,
    captured_at: str,
    *,
    fetch_json: Callable[..., Any],
) -> list[dict[str, Any]]:
    """Fetch repository language byte distribution rows."""
    url = f"https://api.github.com/repos/{repo}/languages"
    data = fetch_json(url, headers)
    if not isinstance(data, dict):
        raise requests.HTTPError(
            f"Unexpected languages response for {repo}: {type(data).__name__}"
        )
    total = sum(_int(value) for value in data.values())
    return [
        {
            "repo": repo,
            "captured_at": captured_at,
            "language": language,
            "bytes": _int(value),
            "share": _share(_int(value), total),
            "schema_version": SCHEMA_VERSION,
        }
        for language, value in sorted(data.items())
    ]


def collect_topics(
    repo: str,
    headers: Headers,
    captured_at: str,
    *,
    fetch_json: Callable[..., Any],
) -> list[dict[str, Any]]:
    """Fetch repository topic rows."""
    url = f"https://api.github.com/repos/{repo}/topics?per_page=100"
    data = fetch_json(url, headers)
    if not isinstance(data, dict) or not isinstance(data.get("names"), list):
        raise requests.HTTPError(
            f"Unexpected topics response for {repo}: {type(data).__name__}"
        )
    return [
        {
            "repo": repo,
            "captured_at": captured_at,
            "topic": str(topic),
            "schema_version": SCHEMA_VERSION,
        }
        for topic in sorted(data["names"])
    ]


def collect_issue_pr_snapshot(
    repo: str,
    headers: Headers,
    captured_at: str,
    *,
    fetch_json: Callable[..., Any],
) -> list[dict[str, Any]]:
    """Fetch a cheap open issue and pull request snapshot."""
    issue_url = f"https://api.github.com/repos/{repo}/issues?state=open&per_page=100"
    pull_url = f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=100"
    issue_data = fetch_json(issue_url, headers)
    pull_data = fetch_json(pull_url, headers)
    if not isinstance(issue_data, list):
        raise requests.HTTPError(
            f"Unexpected issues response for {repo}: {type(issue_data).__name__}"
        )
    if not isinstance(pull_data, list):
        raise requests.HTTPError(
            f"Unexpected pulls response for {repo}: {type(pull_data).__name__}"
        )
    open_issue_count = sum(
        1
        for issue in issue_data
        if isinstance(issue, dict) and "pull_request" not in issue
    )
    return [
        {
            "repo": repo,
            "ts": captured_at[:10],
            "captured_at": captured_at,
            "open_issues_count": open_issue_count,
            "open_prs_count": sum(1 for pull in pull_data if isinstance(pull, dict)),
            "closed_issues_recent": "",
            "merged_prs_recent": "",
            "stale_open_issues_count": "",
            "stale_open_prs_count": "",
            "unanswered_issue_count": "",
            "issue_sample_count": sum(1 for issue in issue_data if isinstance(issue, dict)),
            "pr_sample_count": sum(1 for pull in pull_data if isinstance(pull, dict)),
            "source": "api-sample",
            "schema_version": SCHEMA_VERSION,
        }
    ]


def _login(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("login") or "")
    return ""


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _share(value: int, total: int) -> str:
    if total <= 0:
        return "0.000000"
    return f"{value / total:.6f}"


def _hash_text(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
