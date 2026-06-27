"""Repository eligibility and explicit repository selection."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from typing import Any

from collect_modules.constants import CURRENT_REPOSITORY_ENV_KEYS
from collect_modules.types import Headers, RepoMetadata


def is_trackable_repo(repo: RepoMetadata, *, allow_pull: bool = False) -> bool:
    """Return whether a discovered repository is eligible for tracking."""
    permissions = repo.get("permissions") or {}
    return (
        bool(repo.get("full_name"))
        and not repo.get("fork", False)
        and not repo.get("archived", False)
        and not repo.get("disabled", False)
        and bool(
            permissions.get("push")
            or permissions.get("admin")
            or (allow_pull and permissions.get("pull"))
        )
    )


def current_repository() -> str:
    """Return the repository running the collector when available."""
    for env_key in CURRENT_REPOSITORY_ENV_KEYS:
        value = (os.environ.get(env_key) or "").strip()
        if "/" in value:
            return value
    return ""


def resolve_repositories(
    headers: Headers,
    config: dict[str, Any],
    manifest: dict[str, Any],
    *,
    discover_repositories: Callable[[Headers], list[RepoMetadata]],
    use_github_app_collection_token: Callable[[], bool],
    current_repository: Callable[[], str],
) -> tuple[list[str], dict[str, Any], dict[str, RepoMetadata]]:
    """Resolve the tracked repo set from the explicit collection registry."""
    discovered = discover_repositories(headers)
    eligible = _eligible_repositories(
        discovered,
        allow_pull=use_github_app_collection_token(),
    )
    resolved_repos, missing_repos = resolve_named_repos(
        config["collect_repositories"],
        eligible,
    )
    if missing_repos:
        _warn_missing_collect_repos(missing_repos)
    resolved = [repo["full_name"] for repo in resolved_repos]
    if not resolved:
        print("Error: no collect.repositories entries resolved to eligible repositories.")
        sys.exit(1)
    _print_selection_summary(discovered, eligible, resolved)
    return resolved, manifest, metadata_for_resolved(resolved, eligible)


def _eligible_repositories(
    discovered: list[RepoMetadata],
    *,
    allow_pull: bool,
) -> dict[str, RepoMetadata]:
    eligible: dict[str, RepoMetadata] = {}
    for repo in discovered:
        full_name = (repo.get("full_name") or "").strip()
        if full_name and full_name not in eligible and is_trackable_repo(repo, allow_pull=allow_pull):
            eligible[full_name] = repo
    return eligible


def resolve_named_repos(
    repo_names: list[str],
    eligible: dict[str, RepoMetadata],
) -> tuple[list[RepoMetadata], list[str]]:
    """Resolve a configured repo list against the discovered eligible set."""
    resolved = []
    missing = []
    seen = set()

    for repo_name in repo_names:
        if repo_name in seen:
            continue
        repo = eligible.get(repo_name)
        if repo is None:
            missing.append(repo_name)
            continue
        resolved.append(repo)
        seen.add(repo_name)

    return resolved, missing


def _warn_missing_collect_repos(missing: list[str]) -> None:
    print(
        "Warning: some configured collect.repositories repos were not eligible "
        + "for tracking (missing access, archived, forked, disabled, or "
        + "no push access): "
        + ", ".join(missing)
    )


def _print_selection_summary(
    discovered: list[RepoMetadata],
    eligible: dict[str, RepoMetadata],
    resolved: list[str],
) -> None:
    print(
        "Repository discovery: "
        + f"{len(discovered)} accessible, {len(eligible)} eligible after filters, "
        + f"tracking {len(resolved)} from collect.repositories."
    )


def metadata_for_resolved(
    resolved: list[str],
    eligible: dict[str, RepoMetadata],
) -> dict[str, RepoMetadata]:
    """Return discovery metadata for the selected repositories."""
    return {repo_name: eligible[repo_name] for repo_name in resolved if repo_name in eligible}
