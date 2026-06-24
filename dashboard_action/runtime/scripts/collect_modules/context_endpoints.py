"""GitHub context endpoint shaping for richer repository narratives."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests

from collect_modules.git_history import _associated_pr_number, _classify_commit
from collect_modules.types import Headers
from storage import SCHEMA_VERSION


def collect_commit_history(
    repo: str,
    headers: Headers,
    captured_at: str,
    *,
    default_branch: str = "",
    fetch_json: Callable[..., Any],
) -> list[dict[str, Any]]:
    """Fetch a lightweight default-branch commit spine from the GitHub API."""
    url = f"https://api.github.com/repos/{repo}/commits?per_page=100"
    if default_branch:
        url += f"&sha={quote(default_branch, safe='')}"
    data = fetch_json(url, headers)
    if not isinstance(data, list):
        raise requests.HTTPError(
            f"Unexpected commits response for {repo}: {type(data).__name__}"
        )
    return [
        _commit_history_row(repo, commit, captured_at)
        for commit in reversed(data)
        if isinstance(commit, dict)
    ]


def _commit_history_row(
    repo: str,
    commit: dict[str, Any],
    captured_at: str,
) -> dict[str, Any]:
    commit_payload = commit.get("commit")
    if not isinstance(commit_payload, dict):
        commit_payload = {}
    author = commit_payload.get("author")
    if not isinstance(author, dict):
        author = {}
    committer = commit_payload.get("committer")
    if not isinstance(committer, dict):
        committer = {}
    subject, body = _split_commit_message(str(commit_payload.get("message") or ""))
    return {
        "repo": repo,
        "sha": commit.get("sha", ""),
        "parent_sha": _parent_sha(commit.get("parents")),
        "committed_at": committer.get("date", ""),
        "authored_at": author.get("date", ""),
        "author_name": author.get("name", ""),
        "author_email_hash": _hash_text(str(author.get("email") or "").lower().strip()),
        "author_login": _login(commit.get("author")),
        "committer_login": _login(commit.get("committer")),
        "message_subject": subject,
        "message_body_hash": _hash_text(body.strip()),
        "files_changed": "",
        "additions": "",
        "deletions": "",
        "changed_paths_sample": "",
        "classification": _classify_commit(subject, []),
        "associated_pr_number": _associated_pr_number(subject, body),
        "source": "github-commits-api",
        "captured_at": captured_at,
        "schema_version": SCHEMA_VERSION,
    }


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


def collect_code_frequency_weekly(
    repo: str,
    headers: Headers,
    captured_at: str,
    *,
    fetch_json: Callable[..., Any],
) -> list[dict[str, Any]]:
    """Fetch weekly code-frequency rows from GitHub repository statistics."""
    url = f"https://api.github.com/repos/{repo}/stats/code_frequency"
    data = fetch_json(url, headers)
    if not isinstance(data, list):
        raise requests.HTTPError(
            f"Unexpected code frequency response for {repo}: {type(data).__name__}"
        )
    return [
        {
            "repo": repo,
            "week_start": _epoch_week(row[0]),
            "additions": _int(row[1]),
            "deletions": abs(_int(row[2])),
            "captured_at": captured_at,
            "source_status": "api",
            "schema_version": SCHEMA_VERSION,
        }
        for row in data
        if _is_week_tuple(row, 3)
    ]


def collect_contributor_activity_weekly(
    repo: str,
    headers: Headers,
    captured_at: str,
    *,
    fetch_json: Callable[..., Any],
) -> list[dict[str, Any]]:
    """Fetch non-zero weekly contributor activity rows."""
    url = f"https://api.github.com/repos/{repo}/stats/contributors"
    data = fetch_json(url, headers)
    if not isinstance(data, list):
        raise requests.HTTPError(
            f"Unexpected contributor activity response for {repo}: {type(data).__name__}"
        )
    rows: list[dict[str, Any]] = []
    for contributor in data:
        if not isinstance(contributor, dict):
            continue
        author = contributor.get("author")
        if not isinstance(author, dict):
            author = {}
        weeks = contributor.get("weeks")
        if not isinstance(weeks, list):
            continue
        for week in weeks:
            if not isinstance(week, dict):
                continue
            commits = _int(week.get("c"))
            additions = _int(week.get("a"))
            deletions = _int(week.get("d"))
            if commits == 0 and additions == 0 and deletions == 0:
                continue
            rows.append(
                {
                    "repo": repo,
                    "author_id": author.get("id", ""),
                    "author_login": author.get("login", ""),
                    "week_start": _epoch_week(week.get("w")),
                    "commits": commits,
                    "additions": additions,
                    "deletions": deletions,
                    "captured_at": captured_at,
                    "source_status": "api",
                    "schema_version": SCHEMA_VERSION,
                }
            )
    return rows


def _login(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("login") or "")
    return ""


def _parent_sha(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return ""
    parent = value[0]
    if not isinstance(parent, dict):
        return ""
    return str(parent.get("sha") or "")


def _split_commit_message(message: str) -> tuple[str, str]:
    lines = message.replace("\r\n", "\n").splitlines()
    if not lines:
        return "", ""
    return lines[0], "\n".join(lines[1:]).strip()


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


def _is_week_tuple(value: Any, length: int) -> bool:
    return isinstance(value, (list, tuple)) and len(value) >= length


def _epoch_week(value: Any) -> str:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
