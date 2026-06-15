"""Shared repository selection config helpers."""

from __future__ import annotations

import os
import re
from typing import Any

import yaml


CONFIG_PATH = "config.yaml"
DEFAULT_MAX_REPOS = 200
MAX_OWNER_LENGTH = 39
MAX_REPO_NAME_LENGTH = 100
MAX_FULL_NAME_LENGTH = MAX_OWNER_LENGTH + 1 + MAX_REPO_NAME_LENGTH
OWNER_RE = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
REPO_NAME_RE = r"[A-Za-z0-9_.-]{1,100}"
FULL_REPO_NAME_RE = re.compile(rf"^({OWNER_RE})/({REPO_NAME_RE})$")


def load_repo_config(config_path: str = CONFIG_PATH) -> dict[str, Any]:
    """Load repository-selection settings from config.yaml."""
    if not os.path.exists(config_path):
        return _default_config()

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    if not isinstance(config, dict):
        raise ValueError(f"'{config_path}' must contain a YAML mapping.")

    include_only = _normalize_repo_list(
        config_path,
        "include_only",
        config.get("include_only"),
    )
    include = _normalize_repo_list(
        config_path,
        "include",
        config.get("include", config.get("repos")),
    )
    exclude = _normalize_repo_list(
        config_path,
        "exclude",
        config.get("exclude", config.get("exclude_repos")),
    )
    max_repos = _normalize_positive_int(
        config_path,
        "max_repos",
        config.get("max_repos", DEFAULT_MAX_REPOS),
    )

    if len(include_only) > max_repos:
        raise ValueError(
            f"'{config_path}' key 'include_only' contains {len(include_only)} " +
            f"repositories but 'max_repos' is {max_repos}."
        )
    if len(include) > max_repos:
        raise ValueError(
            f"'{config_path}' key 'include' contains {len(include)} " +
            f"repositories but 'max_repos' is {max_repos}."
        )

    return {
        "max_repos": max_repos,
        "include_only": include_only,
        "include": include,
        "exclude": exclude,
        "include_others": _normalize_bool(
            config_path,
            "include_others",
            config.get("include_others", True),
        ),
        "include_new": _normalize_bool(
            config_path,
            "include_new",
            config.get("include_new", False),
        ),
        "include_private": _normalize_bool(
            config_path,
            "include_private",
            config.get("include_private", True),
        ),
    }


def _normalize_repo_list(config_path: str, key: str, value) -> list[str]:
    """Normalize a repo list and validate owner/repo formatting."""
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
        _validate_repo_full_name(config_path, key, repo)
        if repo not in seen:
            normalized.append(repo)
            seen.add(repo)
    return normalized


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


def _normalize_bool(config_path: str, key: str, value: Any) -> bool:
    """Validate a YAML boolean setting."""
    if isinstance(value, bool):
        return value
    raise ValueError(
        f"'{config_path}' key '{key}' must be true or false, got {value!r}."
    )


def _normalize_positive_int(config_path: str, key: str, value: Any) -> int:
    """Validate a positive integer setting."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(
            f"'{config_path}' key '{key}' must be a positive integer, " +
            f"got {value!r}."
        )
    return value


def _default_config() -> dict[str, Any]:
    return {
        "max_repos": DEFAULT_MAX_REPOS,
        "include_only": [],
        "include": [],
        "exclude": [],
        "include_others": True,
        "include_new": False,
        "include_private": True,
    }
