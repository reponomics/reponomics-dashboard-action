"""Environment parsing and runtime configuration validation."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml

from .core import (
    VALID_MODES,
    VALID_PRIVACY_MODES,
    ActionError,
    RuntimeConfig,
)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _first_env(*names: str) -> str:
    for name in names:
        value = _env(name)
        if value:
            return value
    return ""


def _parse_bool(raw: str, *, name: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ActionError(f"{name} must be true or false, got {raw!r}.")


def _choice(value: str, choices: set[str], *, name: str) -> str:
    normalized = value.strip().lower()
    if normalized not in choices:
        allowed = ", ".join(sorted(choices))
        raise ActionError(f"{name} must be one of: {allowed}.")
    return normalized


def _normalize_privacy_mode(value: str, *, repo_is_public: bool) -> str:
    normalized = value.strip().lower()
    if normalized == "encrypted":
        return "strong"
    if normalized == "auto":
        return "strong" if repo_is_public else "plain"
    return _choice(normalized, VALID_PRIVACY_MODES, name="privacy-mode")


def _parse_retention_days(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ActionError(f"retention-days must be an integer, got {raw!r}.") from exc
    if value < 1 or value > 90:
        raise ActionError("retention-days must be between 1 and 90.")
    return value


def _validate_artifact_run_id(raw: str) -> str:
    if not raw:
        return ""
    if not re.fullmatch(r"[1-9]\d*", raw):
        raise ActionError(f"artifact-run-id must be a positive integer, got {raw!r}.")
    return raw


def _config_allow_docs_sync(config_path: Path) -> bool | None:
    if not config_path.exists():
        return None
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ActionError(f"Could not read allow_docs_sync from {config_path}.") from exc
    if not isinstance(payload, dict) or "allow_docs_sync" not in payload:
        return None
    value = payload["allow_docs_sync"]
    if isinstance(value, bool):
        return value
    raise ActionError("allow_docs_sync in config.yaml must be a YAML boolean.")


def _allow_docs_sync_from_env(config_path: Path) -> bool:
    raw = _env("REPONOMICS_ALLOW_DOCS_SYNC")
    if raw:
        return _parse_bool(raw, name="allow-docs-sync")
    configured = _config_allow_docs_sync(config_path)
    if configured is not None:
        return configured
    return True


def _repo_is_public() -> bool:
    value = _env("GITHUB_EVENT_REPOSITORY_PRIVATE")
    if value:
        normalized = value.lower()
        if normalized == "true":
            return False
        if normalized == "false":
            return True
        raise ActionError(
            "Could not determine repository visibility: "
            + f"GITHUB_EVENT_REPOSITORY_PRIVATE={value!r} is not a boolean."
        )
    event_path = _env("GITHUB_EVENT_PATH")
    if event_path:
        try:
            payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
            private = payload.get("repository", {}).get("private")
            if isinstance(private, bool):
                return not private
        except (OSError, ValueError):
            raise ActionError(
                "Could not determine repository visibility from GITHUB_EVENT_PATH."
            ) from None
        raise ActionError(
            "Could not determine repository visibility: "
            + "repository.private is missing from the event payload."
        )
    raise ActionError(
        "Could not determine repository visibility: missing GitHub event context."
    )


def load_config_from_env() -> RuntimeConfig:
    mode = _choice(_env("REPONOMICS_MODE", "collect"), VALID_MODES, name="mode")
    repo_is_public = _repo_is_public()
    privacy_mode = _normalize_privacy_mode(
        _first_env("REPONOMICS_PRIVACY_MODE", "REPONOMICS_ARTIFACT_SECURITY_MODE") or "strong",
        repo_is_public=repo_is_public,
    )
    config_path = Path(_env("REPONOMICS_CONFIG_PATH", "config.yaml"))
    return RuntimeConfig(
        mode=mode,
        collection_token=_first_env(
            "REPONOMICS_COLLECTION_TOKEN",
            "COLLECTION_TOKEN",
            "REPONOMICS_GITHUB_TOKEN",
            "GH_TOKEN",
        ),
        use_github_app=_parse_bool(
            _env("REPONOMICS_USE_GITHUB_APP", "false"),
            name="use-github-app",
        ),
        github_token=_first_env("REPONOMICS_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"),
        dashboard_secret=_first_env("REPONOMICS_DASHBOARD_SECRET", "DASHBOARD_SECRET_DO_NOT_REPLACE"),
        dashboard_next_secret=_first_env(
            "REPONOMICS_DASHBOARD_NEXT_SECRET",
            "DASHBOARD_NEXT_SECRET",
        ),
        comparison_secret=_first_env("REPONOMICS_COMPARISON_SECRET", "COMPARISON_SECRET"),
        privacy_mode=privacy_mode,
        repo_is_public=repo_is_public,
        config_path=config_path,
        data_dir=Path("data"),
        retention_days=_parse_retention_days(_env("REPONOMICS_RETENTION_DAYS", "90")),
        artifact_run_id=_validate_artifact_run_id(_env("REPONOMICS_ARTIFACT_RUN_ID")),
        publish_pages_requested=_parse_bool(
            _env("REPONOMICS_PUBLISH_PAGES", "true"),
            name="publish-pages",
        ),
        generate_readme=_parse_bool(
            _env("REPONOMICS_GENERATE_README", "false"),
            name="generate-readme",
        ),
        allow_docs_sync=_allow_docs_sync_from_env(config_path),
        pages_index_path=Path("docs/index.html"),
        readme_path=Path(_env("REPONOMICS_README_PATH", "README.md")),
        incident_confirm_mode=_env("REPONOMICS_INCIDENT_CONFIRM_MODE"),
        incident_confirm_purge=_env("REPONOMICS_INCIDENT_CONFIRM_PURGE"),
        incident_confirm_irreversible=_env("REPONOMICS_INCIDENT_CONFIRM_IRREVERSIBLE"),
        action_ref=_env("REPONOMICS_ACTION_REF"),
        action_repository=_env("REPONOMICS_ACTION_REPOSITORY"),
    )
