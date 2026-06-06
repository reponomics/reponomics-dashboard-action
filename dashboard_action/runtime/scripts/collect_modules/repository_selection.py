"""Repository eligibility and stable auto-selection."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from datetime import datetime, timezone
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


def selection_state(manifest: dict[str, Any]) -> dict[str, str]:
    """Return the persisted automatic-selection state."""
    state = manifest.get("selection_state")
    if not isinstance(state, dict):
        state = {}
        manifest["selection_state"] = state
    state.setdefault("auto_seeded_at", "")
    state.setdefault("auto_cutoff_created_at", "")
    return state


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
    """Resolve the tracked repo set from explicit config plus stable auto-fill."""
    discovered = discover_repositories(headers)
    eligible = _eligible_repositories(
        discovered,
        allow_pull=use_github_app_collection_token(),
    )

    if config["include_only"]:
        return _resolve_include_only(config, manifest, discovered, eligible)

    return _resolve_mixed_selection(
        config,
        manifest,
        discovered,
        eligible,
        current_repository=current_repository(),
    )


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


def _resolve_include_only(
    config: dict[str, Any],
    manifest: dict[str, Any],
    discovered: list[RepoMetadata],
    eligible: dict[str, RepoMetadata],
) -> tuple[list[str], dict[str, Any], dict[str, RepoMetadata]]:
    include_only_repos, missing_include_only = resolve_named_repos(
        config["include_only"],
        eligible,
    )
    if missing_include_only:
        _warn_missing_repos("include_only", missing_include_only)
    resolved = [repo["full_name"] for repo in include_only_repos[: config["max_repos"]]]
    if not resolved:
        print("Error: no eligible repositories remain in 'include_only'.")
        sys.exit(1)
    print(
        "Repository discovery: "
        + f"{len(discovered)} accessible, {len(eligible)} eligible after filters, "
        + f"tracking {len(resolved)} from include_only."
    )
    return resolved, manifest, metadata_for_resolved(resolved, eligible)


def _resolve_mixed_selection(
    config: dict[str, Any],
    manifest: dict[str, Any],
    discovered: list[RepoMetadata],
    eligible: dict[str, RepoMetadata],
    *,
    current_repository: str,
) -> tuple[list[str], dict[str, Any], dict[str, RepoMetadata]]:
    include_repos, missing_include = resolve_named_repos(config["include"], eligible)
    if missing_include:
        _warn_missing_repos("include", missing_include)

    resolved = [repo["full_name"] for repo in include_repos]
    explicit_count = len(resolved)
    auto_count = _add_auto_selection(config, manifest, eligible, resolved, current_repository)
    _print_selection_summary(discovered, eligible, resolved, explicit_count, auto_count)
    _exit_if_empty_selection(resolved)
    return resolved, manifest, metadata_for_resolved(resolved, eligible)


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


def _warn_missing_repos(config_key: str, missing: list[str]) -> None:
    print(
        f"Warning: some configured {config_key} repos were not eligible "
        + "for tracking (missing access, archived, forked, disabled, or "
        + "no push access): "
        + ", ".join(missing)
    )


def _add_auto_selection(
    config: dict[str, Any],
    manifest: dict[str, Any],
    eligible: dict[str, RepoMetadata],
    resolved: list[str],
    current_repository: str,
) -> int:
    state = selection_state(manifest)
    if not config["include_others"] or len(resolved) >= config["max_repos"]:
        state["auto_cutoff_created_at"] = ""
        return 0
    if not state["auto_seeded_at"]:
        state["auto_seeded_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    selected_auto = build_auto_candidates(
        eligible=eligible,
        excluded=set(config["exclude"]),
        selected_names=set(resolved),
        current_repository=current_repository,
        include_private=config["include_private"],
        include_new=config["include_new"],
        auto_seeded_at=state["auto_seeded_at"],
    )[: config["max_repos"] - len(resolved)]
    resolved.extend(repo["full_name"] for repo in selected_auto)
    state["auto_cutoff_created_at"] = (
        selected_auto[-1].get("created_at") or "" if selected_auto else ""
    )
    return len(selected_auto)


def build_auto_candidates(
    eligible: dict[str, RepoMetadata],
    excluded: set[str],
    selected_names: set[str],
    current_repository: str,
    include_private: bool,
    include_new: bool,
    auto_seeded_at: str,
) -> list[RepoMetadata]:
    """Return automatic candidates after applying explicit selection rules."""
    candidates = [
        repo
        for repo_name, repo in eligible.items()
        if _is_auto_candidate(
            repo_name,
            repo,
            excluded,
            selected_names,
            current_repository,
            include_private,
            include_new,
            auto_seeded_at,
        )
    ]
    return sort_auto_candidates(candidates)


def _is_auto_candidate(
    repo_name: str,
    repo: RepoMetadata,
    excluded: set[str],
    selected_names: set[str],
    current_repository: str,
    include_private: bool,
    include_new: bool,
    auto_seeded_at: str,
) -> bool:
    if repo_name in selected_names or repo_name in excluded:
        return False
    if current_repository and repo_name == current_repository:
        return False
    if not include_private and repo.get("private", False):
        return False
    return not (
        auto_seeded_at
        and not include_new
        and (repo.get("created_at") or "") > auto_seeded_at
    )


def sort_auto_candidates(repos: list[RepoMetadata]) -> list[RepoMetadata]:
    """Sort automatic candidates by creation date descending, then name."""
    repos = sorted(repos, key=lambda repo: repo.get("full_name") or "")
    return sorted(repos, key=lambda repo: repo.get("created_at") or "", reverse=True)


def _print_selection_summary(
    discovered: list[RepoMetadata],
    eligible: dict[str, RepoMetadata],
    resolved: list[str],
    explicit_count: int,
    auto_count: int,
) -> None:
    print(
        "Repository discovery: "
        + f"{len(discovered)} accessible, {len(eligible)} eligible after filters, "
        + f"tracking {len(resolved)} "
        + f"({explicit_count} explicit, {auto_count} automatic)."
    )


def _exit_if_empty_selection(resolved: list[str]) -> None:
    if resolved:
        return
    print("Error: no eligible repositories found for traffic collection.")
    print(
        "Check your config or token access. Explicit includes must be "
        + "accessible, and automatic tracking excludes forks, archived repos, "
        + "disabled repos, and repos without push access."
    )
    sys.exit(1)


def metadata_for_resolved(
    resolved: list[str],
    eligible: dict[str, RepoMetadata],
) -> dict[str, RepoMetadata]:
    """Return discovery metadata for the selected repositories."""
    return {repo_name: eligible[repo_name] for repo_name in resolved if repo_name in eligible}
