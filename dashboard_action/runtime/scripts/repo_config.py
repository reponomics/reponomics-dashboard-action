"""Shared repository selection config helpers."""

from __future__ import annotations

import os
import re
from typing import Any

import yaml


CONFIG_PATH = "config.yaml"
DEFAULT_MAX_COLLECT_REPOS = 100
MAX_PUBLISH_REPOS = 8
MAX_OWNER_LENGTH = 39
MAX_REPO_NAME_LENGTH = 100
MAX_FULL_NAME_LENGTH = MAX_OWNER_LENGTH + 1 + MAX_REPO_NAME_LENGTH
OWNER_RE = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
REPO_NAME_RE = r"[A-Za-z0-9_.-]{1,100}"
REPO_NAME_ONLY_RE = re.compile(rf"^{REPO_NAME_RE}$")
FULL_REPO_NAME_RE = re.compile(rf"^({OWNER_RE})/({REPO_NAME_RE})$")
CURRENT_REPOSITORY_ENV_KEYS = ("GITHUB_REPOSITORY", "GH_REPO")
REMOVED_SELECTION_KEYS = frozenset(
    {
        "include_only",
        "include",
        "repos",
        "exclude",
        "exclude_repos",
        "include_others",
        "include_new",
        "include_private",
        "max_repos",
    }
)


def load_repo_config(config_path: str = CONFIG_PATH) -> dict[str, Any]:
    """Load repository-selection settings from config.yaml."""
    if not os.path.exists(config_path):
        return _default_config()

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    if not isinstance(config, dict):
        raise ValueError(f"'{config_path}' must contain a YAML mapping.")

    removed_keys = sorted(REMOVED_SELECTION_KEYS.intersection(config))
    if removed_keys:
        raise ValueError(
            f"'{config_path}' uses removed repository-selection key(s): "
            + ", ".join(removed_keys)
            + ". Use collect.repositories and publish.repositories."
        )

    default_owner = _current_repository_owner()
    collect_repos = _normalize_nested_repo_list(
        config_path,
        "collect",
        config.get("collect"),
        "repositories",
        default_owner=default_owner,
    )
    publish_repos = _normalize_nested_repo_list(
        config_path,
        "publish",
        config.get("publish"),
        "repositories",
        default_owner=default_owner,
    )

    if not collect_repos:
        raise ValueError(
            f"'{config_path}' key 'collect.repositories' must contain at least "
            + "one repository."
        )
    if not publish_repos:
        raise ValueError(
            f"'{config_path}' key 'publish.repositories' must contain at least "
            + "one repository."
        )
    if len(collect_repos) > DEFAULT_MAX_COLLECT_REPOS:
        raise ValueError(
            f"'{config_path}' key 'collect.repositories' contains "
            + f"{len(collect_repos)} repositories but the beta cap is "
            + f"{DEFAULT_MAX_COLLECT_REPOS}."
        )
    if len(publish_repos) > MAX_PUBLISH_REPOS:
        raise ValueError(
            f"'{config_path}' key 'publish.repositories' contains "
            + f"{len(publish_repos)} repositories but the dashboard cap is "
            + f"{MAX_PUBLISH_REPOS}."
        )

    collect_set = set(collect_repos)
    missing_from_collect = [repo for repo in publish_repos if repo not in collect_set]
    if missing_from_collect:
        raise ValueError(
            f"'{config_path}' key 'publish.repositories' includes repos that "
            + "are not listed in 'collect.repositories': "
            + ", ".join(missing_from_collect)
        )

    return {
        "max_collect_repos": DEFAULT_MAX_COLLECT_REPOS,
        "max_publish_repos": MAX_PUBLISH_REPOS,
        "collect_repositories": collect_repos,
        "publish_repositories": publish_repos,
    }


def _normalize_nested_repo_list(
    config_path: str,
    parent_key: str,
    parent_value: Any,
    child_key: str,
    *,
    default_owner: str,
) -> list[str]:
    """Normalize a repository list from a nested config mapping."""
    full_key = f"{parent_key}.{child_key}"
    if not isinstance(parent_value, dict):
        raise ValueError(f"'{config_path}' key '{parent_key}' must be a mapping.")
    if any(not isinstance(key, str) for key in parent_value):
        raise ValueError(f"'{config_path}' key '{parent_key}' must contain string keys.")
    return _normalize_repo_list(
        config_path,
        full_key,
        parent_value.get(child_key),
        default_owner=default_owner,
    )


def _normalize_repo_list(
    config_path: str,
    key: str,
    value: Any,
    *,
    default_owner: str,
) -> list[str]:
    """Normalize repo entries and validate GitHub repository formatting."""
    value = value or []
    if not isinstance(value, list):
        raise ValueError(f"'{config_path}' key '{key}' must be a list.")

    normalized = []
    seen = set()
    for raw_repo in value:
        if not isinstance(raw_repo, str):
            raise ValueError(
                f"invalid repository entry {raw_repo!r} under '{key}' in " +
                f"{config_path}; repository entries must be strings."
            )
        repo = raw_repo.strip()
        if not repo:
            continue
        normalized_repo = _normalize_repo_name(
            config_path,
            key,
            repo,
            default_owner=default_owner,
        )
        if normalized_repo not in seen:
            normalized.append(normalized_repo)
            seen.add(normalized_repo)
    return normalized


def _normalize_repo_name(
    config_path: str,
    key: str,
    repo: str,
    *,
    default_owner: str,
) -> str:
    """Return a full owner/repo name for a configured repository entry."""
    if "/" in repo:
        _validate_repo_full_name(config_path, key, repo)
        return repo
    _validate_repo_short_name(config_path, key, repo)
    if not default_owner:
        raise ValueError(
            f"invalid repository entry {repo!r} under '{key}' in {config_path}; "
            + "bare repository names require GITHUB_REPOSITORY or GH_REPO so "
            + "the dashboard repository owner can be inferred."
        )
    full_name = f"{default_owner}/{repo}"
    _validate_repo_full_name(config_path, key, full_name)
    return full_name


def _validate_repo_full_name(config_path: str, key: str, repo: str) -> None:
    """Validate a GitHub owner/repository full name."""
    if len(repo) > MAX_FULL_NAME_LENGTH:
        raise ValueError(
            f"invalid repository entry {repo!r} under '{key}' in {config_path}; " +
            f"full names must be at most {MAX_FULL_NAME_LENGTH} characters."
        )
    match = FULL_REPO_NAME_RE.fullmatch(repo)
    if not match:
        raise ValueError(
            f"invalid repository entry {repo!r} under '{key}' in {config_path}; " +
            "use 'owner/repo' with a GitHub owner name and a repository name " +
            "containing only ASCII letters, digits, '.', '-', or '_'."
        )
    _, repo_name = match.groups()
    if repo_name in {".", ".."}:
        raise ValueError(
            f"invalid repository entry {repo!r} under '{key}' in {config_path}; " +
            "repository name cannot be '.' or '..'."
        )
    if repo_name.lower().endswith((".git", ".wiki")):
        raise ValueError(
            f"invalid repository entry {repo!r} under '{key}' in {config_path}; " +
            "repository name cannot end with '.git' or '.wiki'."
        )


def _validate_repo_short_name(config_path: str, key: str, repo_name: str) -> None:
    """Validate a bare GitHub repository name."""
    if len(repo_name) > MAX_REPO_NAME_LENGTH:
        raise ValueError(
            f"invalid repository entry {repo_name!r} under '{key}' in {config_path}; "
            + f"repository names must be at most {MAX_REPO_NAME_LENGTH} characters."
        )
    if not REPO_NAME_ONLY_RE.fullmatch(repo_name):
        raise ValueError(
            f"invalid repository entry {repo_name!r} under '{key}' in {config_path}; "
            + "use 'repo' or 'owner/repo' with names containing only ASCII "
            + "letters, digits, '.', '-', or '_'."
        )
    if repo_name in {".", ".."}:
        raise ValueError(
            f"invalid repository entry {repo_name!r} under '{key}' in {config_path}; "
            + "repository name cannot be '.' or '..'."
        )
    if repo_name.lower().endswith((".git", ".wiki")):
        raise ValueError(
            f"invalid repository entry {repo_name!r} under '{key}' in {config_path}; "
            + "repository name cannot end with '.git' or '.wiki'."
        )


def _current_repository_owner() -> str:
    """Return the owner of the dashboard repository from the workflow env."""
    for env_key in CURRENT_REPOSITORY_ENV_KEYS:
        full_name = (os.environ.get(env_key) or "").strip()
        if "/" in full_name:
            owner = full_name.split("/", 1)[0].strip()
            if owner:
                return owner
    return ""


def _default_config() -> dict[str, Any]:
    return {
        "max_collect_repos": DEFAULT_MAX_COLLECT_REPOS,
        "max_publish_repos": MAX_PUBLISH_REPOS,
        "collect_repositories": [],
        "publish_repositories": [],
    }
