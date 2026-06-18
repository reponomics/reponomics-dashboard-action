"""Environment parsing and runtime configuration validation."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml
from yaml.nodes import MappingNode

from .core import (
    VALID_MODES,
    VALID_DATA_MODES,
    ActionError,
    RuntimeConfig,
)


REQUIRED_SETUP_CONFIG_KEYS = (
    "i_have_read_the_readme",
    "data_mode",
    "publish_pages_dashboard",
    "publish_readme_dashboard",
    "allow_docs_sync",
)
MIN_RETENTION_DAYS = 14
MAX_RETENTION_DAYS = 90


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: yaml.Loader,
    node: MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    loader.flatten_mapping(node)
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ActionError(f"config.yaml contains duplicate key {key!r}.")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
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


def _normalize_data_mode(value: str) -> str:
    return _choice(value, VALID_DATA_MODES, name="data-mode")


def _parse_retention_days(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ActionError(f"retention-days must be an integer, got {raw!r}.") from exc
    if value < MIN_RETENTION_DAYS or value > MAX_RETENTION_DAYS:
        raise ActionError(
            f"retention-days must be between {MIN_RETENTION_DAYS} and {MAX_RETENTION_DAYS}."
        )
    return value


def _validate_artifact_run_id(raw: str) -> str:
    if not raw:
        return ""
    if not re.fullmatch(r"[1-9]\d*", raw):
        raise ActionError(f"artifact-run-id must be a positive integer, got {raw!r}.")
    return raw


def _load_config_yaml(config_path: Path) -> dict[str, object]:
    if not config_path.exists():
        raise ActionError(f"Required config file is missing: {config_path}.")
    try:
        payload = yaml.load(
            config_path.read_text(encoding="utf-8"),
            Loader=_UniqueKeyLoader,
        )
    except ActionError:
        raise
    except (OSError, yaml.YAMLError) as exc:
        raise ActionError(f"Could not read runtime configuration from {config_path}.") from exc
    if not isinstance(payload, dict):
        raise ActionError(f"{config_path} must contain a YAML mapping.")
    if any(not isinstance(key, str) for key in payload):
        raise ActionError("config.yaml top-level keys must be strings.")
    return payload


def _config_bool(payload: dict[str, object], key: str) -> bool:
    value = payload[key]
    if isinstance(value, bool):
        return value
    raise ActionError(f"{key} in config.yaml must be a YAML boolean.")


def _config_data_mode(payload: dict[str, object]) -> str:
    value = payload["data_mode"]
    if not isinstance(value, str):
        raise ActionError("data_mode in config.yaml must be encrypted or plaintext.")
    return _normalize_data_mode(value)


def _config_retention_days(payload: dict[str, object]) -> int:
    value = payload["artifact_retention_days"]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ActionError("artifact_retention_days in config.yaml must be an integer.")
    return _parse_retention_days(str(value))


def _load_runtime_config_values(config_path: Path) -> dict[str, bool | int | str]:
    payload = _load_config_yaml(config_path)
    missing = [key for key in REQUIRED_SETUP_CONFIG_KEYS if key not in payload]
    if missing:
        raise ActionError(
            "config.yaml is missing required setup field(s): " + ", ".join(missing)
        )

    read_readme = _config_bool(payload, "i_have_read_the_readme")
    if not read_readme:
        raise ActionError("i_have_read_the_readme in config.yaml must be true.")

    return {
        "data_mode": _config_data_mode(payload),
        "publish_pages_dashboard": _config_bool(payload, "publish_pages_dashboard"),
        "publish_readme_dashboard": _config_bool(payload, "publish_readme_dashboard"),
        "allow_docs_sync": _config_bool(payload, "allow_docs_sync"),
        "artifact_retention_days": _config_retention_days(payload),
        "use_github_app": _config_bool(payload, "use_github_app"),
    }


def _config_allow_docs_sync(config_path: Path) -> bool:
    configured = _load_runtime_config_values(config_path)["allow_docs_sync"]
    if not isinstance(configured, bool):
        raise ActionError("allow_docs_sync in config.yaml must be a YAML boolean.")
    return configured


def _reject_config_mismatch(
    *,
    input_name: str,
    config_key: str,
    input_value: bool | int | str,
    config_value: bool | int | str,
) -> None:
    if input_value == config_value:
        return
    raise ActionError(
        f"{input_name}={input_value!r} does not match "
        + f"{config_key}={config_value!r} in config.yaml."
    )


def _bool_from_env_or_config(
    env_name: str,
    configured: dict[str, bool | int | str],
    *,
    config_key: str,
    input_name: str,
) -> bool:
    config_value = configured[config_key]
    if not isinstance(config_value, bool):
        raise ActionError(f"{config_key} in config.yaml must be a YAML boolean.")
    raw = _env(env_name)
    if raw:
        input_value = _parse_bool(raw, name=input_name)
        _reject_config_mismatch(
            input_name=input_name,
            config_key=config_key,
            input_value=input_value,
            config_value=config_value,
        )
    return config_value


def _data_mode_from_env_or_config(configured: dict[str, bool | int | str]) -> str:
    config_value = configured["data_mode"]
    if not isinstance(config_value, str):
        raise ActionError("data_mode in config.yaml must be encrypted or plaintext.")
    raw = _env("REPONOMICS_DATA_MODE")
    if raw:
        input_value = _normalize_data_mode(raw)
        _reject_config_mismatch(
            input_name="data-mode",
            config_key="data_mode",
            input_value=input_value,
            config_value=config_value,
        )
    return config_value


def _retention_days_from_env_or_config(configured: dict[str, bool | int | str]) -> int:
    config_value = configured["artifact_retention_days"]
    if isinstance(config_value, bool) or not isinstance(config_value, int):
        raise ActionError("artifact_retention_days in config.yaml must be an integer.")
    raw = _env("REPONOMICS_RETENTION_DAYS")
    if raw:
        input_value = _parse_retention_days(raw)
        _reject_config_mismatch(
            input_name="retention-days",
            config_key="artifact_retention_days",
            input_value=input_value,
            config_value=config_value,
        )
    return config_value


def _allow_docs_sync_from_env(configured: dict[str, bool | int | str]) -> bool:
    return _bool_from_env_or_config(
        "REPONOMICS_ALLOW_DOCS_SYNC",
        configured,
        config_key="allow_docs_sync",
        input_name="allow-docs-sync",
    )


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
    config_path = Path(_env("REPONOMICS_CONFIG_PATH", "config.yaml"))
    configured = _load_runtime_config_values(config_path)
    repo_is_public = _repo_is_public()
    data_mode = _data_mode_from_env_or_config(configured)
    return RuntimeConfig(
        mode=mode,
        collection_token=_first_env(
            "REPONOMICS_COLLECTION_TOKEN",
            "COLLECTION_TOKEN",
            "REPONOMICS_GITHUB_TOKEN",
            "GH_TOKEN",
        ),
        use_github_app=_bool_from_env_or_config(
            "REPONOMICS_USE_GITHUB_APP",
            configured,
            config_key="use_github_app",
            input_name="use-github-app",
        ),
        github_token=_first_env("REPONOMICS_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"),
        dashboard_secret=_first_env(
            "REPONOMICS_DASHBOARD_SECRET", "DASHBOARD_SECRET_DO_NOT_REPLACE"
        ),
        dashboard_next_secret=_first_env(
            "REPONOMICS_DASHBOARD_NEXT_SECRET",
            "DASHBOARD_NEXT_SECRET",
        ),
        comparison_secret=_first_env("REPONOMICS_COMPARISON_SECRET", "COMPARISON_SECRET"),
        data_mode=data_mode,
        repo_is_public=repo_is_public,
        config_path=config_path,
        data_dir=Path("data"),
        retention_days=_retention_days_from_env_or_config(configured),
        artifact_run_id=_validate_artifact_run_id(_env("REPONOMICS_ARTIFACT_RUN_ID")),
        publish_pages_requested=_bool_from_env_or_config(
            "REPONOMICS_PUBLISH_PAGES",
            configured,
            config_key="publish_pages_dashboard",
            input_name="publish-pages",
        ),
        generate_readme=_bool_from_env_or_config(
            "REPONOMICS_GENERATE_README",
            configured,
            config_key="publish_readme_dashboard",
            input_name="generate-readme",
        ),
        allow_docs_sync=_allow_docs_sync_from_env(configured),
        pages_index_path=Path("docs/index.html"),
        readme_path=Path(_env("REPONOMICS_README_PATH", "README.md")),
        incident_confirm_mode=_env("REPONOMICS_INCIDENT_CONFIRM_MODE"),
        incident_confirm_purge=_env("REPONOMICS_INCIDENT_CONFIRM_PURGE"),
        incident_confirm_next_secret=_env("REPONOMICS_INCIDENT_CONFIRM_NEXT_SECRET"),
        incident_confirm_irreversible=_env("REPONOMICS_INCIDENT_CONFIRM_IRREVERSIBLE"),
        action_ref=_env("REPONOMICS_ACTION_REF"),
        action_repository=_env("REPONOMICS_ACTION_REPOSITORY"),
    )
