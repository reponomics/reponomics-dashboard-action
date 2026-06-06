"""Repository detail and community metric endpoint shaping."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import requests

from collect_modules.types import Headers, RepoMetadata
from storage import SCHEMA_VERSION


def collect_repo_detail(
    repo: str,
    headers: Headers,
    *,
    fetch_json: Callable[..., Any],
) -> RepoMetadata:
    """Fetch the canonical repository profile used for growth metrics."""
    url = f"https://api.github.com/repos/{repo}"
    data = fetch_json(url, headers)
    if not isinstance(data, dict):
        raise requests.HTTPError(
            f"Unexpected repository detail response for {repo}: {type(data).__name__}"
        )
    return data


def collect_repo_community_profile(
    repo: str,
    headers: Headers,
    *,
    fetch_json: Callable[..., Any],
) -> RepoMetadata:
    """Fetch repository community profile metrics."""
    url = f"https://api.github.com/repos/{repo}/community/profile"
    data = fetch_json(url, headers)
    if not isinstance(data, dict):
        raise requests.HTTPError(
            f"Unexpected community profile response for {repo}: {type(data).__name__}"
        )
    return data


def collect_repo_metrics(
    repo: str,
    repo_detail: RepoMetadata,
    community_profile: RepoMetadata,
    captured_at: str,
    *,
    source: str = "repo-detail",
) -> list[dict[str, Any]]:
    """Return aggregate repository growth counters from repository detail data."""
    files = community_profile.get("files")
    if not isinstance(files, dict):
        files = {}
    return [
        {
            "repo": repo,
            "repo_id": repo_detail.get("id", ""),
            "node_id": repo_detail.get("node_id", ""),
            "ts": captured_at[:10],
            "captured_at": captured_at,
            "stargazers_count": int(repo_detail.get("stargazers_count", 0) or 0),
            "subscribers_count": int(repo_detail.get("subscribers_count", 0) or 0),
            "forks_count": int(repo_detail.get("forks_count", 0) or 0),
            "open_issues_count": int(repo_detail.get("open_issues_count", 0) or 0),
            "size_kb": int(repo_detail.get("size", 0) or 0),
            "created_at": repo_detail.get("created_at", ""),
            "pushed_at": repo_detail.get("pushed_at", ""),
            "updated_at": repo_detail.get("updated_at", ""),
            "language": repo_detail.get("language", ""),
            "visibility": repo_detail.get("visibility", ""),
            "default_branch": repo_detail.get("default_branch", ""),
            "has_pages": repo_detail.get("has_pages", ""),
            "has_discussions": repo_detail.get("has_discussions", ""),
            "archived": repo_detail.get("archived", ""),
            "disabled": repo_detail.get("disabled", ""),
            "community_health_percentage": community_health_percentage(community_profile),
            "community_documentation": community_profile.get("documentation", "") or "",
            "community_updated_at": community_profile.get("updated_at", "") or "",
            "community_content_reports_enabled": community_profile.get(
                "content_reports_enabled",
                "",
            ),
            "community_has_code_of_conduct": community_has_file(files, "code_of_conduct"),
            "community_has_contributing": community_has_file(files, "contributing"),
            "community_has_issue_template": community_has_file(files, "issue_template"),
            "community_has_pull_request_template": community_has_file(
                files,
                "pull_request_template",
            ),
            "community_has_readme": community_has_file(files, "readme"),
            "community_has_license": community_has_file(files, "license"),
            "source": source,
            "schema_version": SCHEMA_VERSION,
        }
    ]


def community_has_file(files: RepoMetadata, key: str) -> bool | str:
    if key not in files:
        return ""
    return bool(files.get(key))


def community_health_percentage(profile: RepoMetadata) -> int | str:
    value = profile.get("health_percentage")
    if value in (None, ""):
        return ""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return ""


def fallback_repo_detail_warning(repo: str, exc: Exception) -> str:
    return (
        f"{repo}: repository detail request failed ({exc}); "
        + "traffic collection continued and repo metrics used discovery fallback."
    )


def fallback_repo_community_warning(repo: str, exc: Exception) -> str:
    return (
        f"{repo}: community profile request failed ({exc}); "
        + "collection continued and community metrics were left blank."
    )
