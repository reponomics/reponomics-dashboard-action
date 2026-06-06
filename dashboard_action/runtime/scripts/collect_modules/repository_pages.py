"""Repository listing pagination for GitHub user and app tokens."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import requests

from collect_modules.constants import (
    APP_REPO_DISCOVERY_URL,
    REPO_DISCOVERY_PAGE_SIZE,
    REPO_DISCOVERY_URL,
)
from collect_modules.types import Headers, RepoMetadata


def discover_repositories(
    headers: Headers,
    *,
    fetch_json: Callable[[str, Headers], Any],
    use_github_app_collection_token: Callable[[], bool],
) -> list[RepoMetadata]:
    """Return all accessible repositories visible to the authenticated user."""
    use_github_app = use_github_app_collection_token()
    page = 1
    discovered: list[RepoMetadata] = []
    while True:
        page_rows = _repository_page(headers, page, use_github_app, fetch_json)
        if not page_rows:
            break
        discovered.extend(page_rows)
        if len(page_rows) < REPO_DISCOVERY_PAGE_SIZE:
            break
        page += 1
    return discovered


def _repository_page(
    headers: Headers,
    page: int,
    use_github_app: bool,
    fetch_json: Callable[[str, Headers], Any],
) -> list[RepoMetadata]:
    if use_github_app:
        return _app_repository_page(headers, page, fetch_json)
    url = (
        f"{REPO_DISCOVERY_URL}?affiliation=owner,collaborator,organization_member"
        + f"&sort=updated&direction=desc&per_page={REPO_DISCOVERY_PAGE_SIZE}"
        + f"&page={page}"
    )
    return fetch_json(url, headers)


def _app_repository_page(
    headers: Headers,
    page: int,
    fetch_json: Callable[[str, Headers], Any],
) -> list[RepoMetadata]:
    url = f"{APP_REPO_DISCOVERY_URL}?per_page={REPO_DISCOVERY_PAGE_SIZE}&page={page}"
    response = fetch_json(url, headers)
    if not isinstance(response, dict):
        raise requests.HTTPError(
            "Expected JSON object from app installation repository listing"
        )
    page_rows = response.get("repositories")
    if not isinstance(page_rows, list):
        raise requests.HTTPError(
            "App installation repository listing response did not include repositories"
        )
    return page_rows
