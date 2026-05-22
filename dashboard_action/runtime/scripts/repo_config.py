"""Shared repository selection config helpers."""

from __future__ import annotations

import os
from typing import Any

import yaml


CONFIG_PATH = "config.yaml"
DEFAULT_MAX_REPOS = 50


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
        repo = str(raw_repo).strip()
        if not repo:
            continue
        if "/" not in repo:
            raise ValueError(
                f"invalid repository entry {raw_repo!r} under '{key}' in " +
                f"{config_path}; use the 'owner/repo' format."
            )
        if repo not in seen:
            normalized.append(repo)
            seen.add(repo)
    return normalized


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
