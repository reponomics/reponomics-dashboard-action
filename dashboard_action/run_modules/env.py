"""Runtime environment and path setup helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .core import (
    DOCS_ACTION_VERSION_ENV,
    DOCS_STATE_STALE,
    DOCS_SYNC_STATE_ENV,
    DOCS_UPDATED_AT_ENV,
    MANAGED_DOCS_DASHBOARD_LINK_ENV,
    MANAGED_DOCS_NAMESPACE,
    MANAGED_DOCS_README_LINK_ENV,
    MIN_MASK_LENGTH,
    VERSION,
    RuntimeConfig,
)

import bootstrap  # noqa: E402
import collect as collect_mod  # noqa: E402
import load_data  # noqa: E402
import managed_docs  # noqa: E402
import merge  # noqa: E402
import render_dashboard  # noqa: E402
import render_readme  # noqa: E402
import repo_config  # noqa: E402
import storage  # noqa: E402
import version_status  # noqa: E402


def escape_workflow_data(raw: str) -> str:
    return raw.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _mask_secret(value: str) -> None:
    for line in value.splitlines():
        if len(line) >= MIN_MASK_LENGTH:
            # Emit the workflow command through fd-level stdout writes to avoid
            # log APIs that static analysis treats as clear-text secret logging.
            os.write(1, f"::add-mask::{escape_workflow_data(line)}\n".encode("utf-8"))


def _mask_config_secrets(config: RuntimeConfig) -> None:
    _mask_secret(config.collection_token)
    _mask_secret(config.github_token)
    _mask_secret(config.dashboard_secret)
    _mask_secret(config.dashboard_next_secret)
    _mask_secret(config.comparison_secret)


def _patch_runtime_paths(config: RuntimeConfig) -> None:
    data_dir = config.data_dir.as_posix()
    storage.DATA_DIR = data_dir
    storage.RETENTION_DAYS = config.retention_days
    storage.DATA_MODE = config.resolved_data_mode
    bootstrap.DATA_DIR = data_dir
    collect_mod.DATA_DIR = data_dir
    collect_mod.CONFIG_PATH = config.config_path.as_posix()
    merge.DATA_DIR = data_dir
    merge.RETENTION_DAYS = config.retention_days
    repo_config.CONFIG_PATH = config.config_path.as_posix()

    def load_config(config_path: str = config.config_path.as_posix()) -> dict[str, Any]:
        return repo_config.load_repo_config(config_path)

    load_data.load_repo_config = load_config

    assets_dir = config.pages_index_path.parent / "assets"
    readme_parent = config.readme_path.parent
    display_assets = Path(os.path.relpath(assets_dir, readme_parent))

    render_dashboard.PAGE_INDEX_OUTPUT_PATH = config.pages_index_path.as_posix()
    render_readme.OUTPUT_PATH = config.readme_path.as_posix()
    render_readme.ASSET_OUTPUT_DIR = assets_dir
    render_readme.ASSET_DISPLAY_DIR = display_assets


def _relative_link_if_present(target: Path, base_dir: Path) -> str:
    if not target.is_file():
        return ""
    return Path(os.path.relpath(target, base_dir)).as_posix()


def _set_managed_docs_link_env(config: RuntimeConfig) -> None:
    managed_index = MANAGED_DOCS_NAMESPACE / "README.md"
    readme_parent = config.readme_path.parent
    dashboard_parent = config.pages_index_path.parent
    os.environ[MANAGED_DOCS_README_LINK_ENV] = _relative_link_if_present(
        managed_index,
        readme_parent,
    )
    os.environ[MANAGED_DOCS_DASHBOARD_LINK_ENV] = _relative_link_if_present(
        managed_index,
        dashboard_parent,
    )
    _set_managed_docs_status_env()


def _set_empty_managed_docs_status_env() -> None:
    os.environ[DOCS_SYNC_STATE_ENV] = ""
    os.environ[DOCS_ACTION_VERSION_ENV] = ""
    os.environ[DOCS_UPDATED_AT_ENV] = ""


def _set_managed_docs_status_env() -> None:
    existing_state = os.environ.get(DOCS_SYNC_STATE_ENV, "").strip()
    manifest = _read_managed_docs_manifest(existing_state)
    if manifest is None:
        return

    manifest_action_version = str(manifest.get("action_version") or "")
    if not os.environ.get(DOCS_ACTION_VERSION_ENV, "").strip():
        os.environ[DOCS_ACTION_VERSION_ENV] = manifest_action_version
    if not os.environ.get(DOCS_UPDATED_AT_ENV, "").strip():
        os.environ[DOCS_UPDATED_AT_ENV] = str(manifest.get("updated_at") or "")
    if existing_state:
        return
    os.environ[DOCS_SYNC_STATE_ENV] = (
        managed_docs.STATE_UNCHANGED
        if manifest_action_version == VERSION
        else DOCS_STATE_STALE
    )


def _read_managed_docs_manifest(existing_state: str) -> dict[str, Any] | None:
    manifest_path = MANAGED_DOCS_NAMESPACE / managed_docs.MANIFEST_NAME
    if not manifest_path.is_file():
        if not existing_state:
            _set_empty_managed_docs_status_env()
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        if not existing_state:
            os.environ[DOCS_SYNC_STATE_ENV] = managed_docs.STATE_MANIFEST_INCONSISTENT
            os.environ[DOCS_ACTION_VERSION_ENV] = ""
            os.environ[DOCS_UPDATED_AT_ENV] = ""
        return None
    return manifest if isinstance(manifest, dict) else {}


def _set_runtime_env(config: RuntimeConfig, *, next_key: bool = False) -> None:
    os.environ["RETENTION_DAYS"] = str(config.retention_days)
    os.environ["DATA_DIR"] = config.data_dir.as_posix()
    os.environ["DATA_MODE"] = config.resolved_data_mode
    os.environ["PUBLISH_PAGES"] = str(config.publish_pages).lower()
    os.environ["DASHBOARD_ACCESS_MODE"] = (
        "public" if config.resolved_data_mode == "plaintext" else "encrypted"
    )
    if config.collection_token:
        os.environ["GH_TOKEN"] = config.collection_token
    os.environ["REPONOMICS_USE_GITHUB_APP"] = str(config.use_github_app).lower()
    if config.dashboard_secret:
        os.environ["DASHBOARD_SECRET_DO_NOT_REPLACE"] = config.dashboard_secret
    if config.dashboard_next_secret:
        os.environ["DASHBOARD_NEXT_SECRET"] = config.dashboard_next_secret
    dashboard_key = config.dashboard_next_secret if next_key else config.dashboard_secret
    if dashboard_key:
        os.environ["DASHBOARD_KEY"] = dashboard_key
    if config.action_ref:
        os.environ["REPONOMICS_ACTION_REF"] = config.action_ref
    if config.action_repository:
        os.environ["REPONOMICS_ACTION_REPOSITORY"] = config.action_repository
    _set_managed_docs_link_env(config)


def _set_version_status_env(config: RuntimeConfig) -> None:
    os.environ.pop("REPONOMICS_VERSION_STATUS_JSON", None)
    status = version_status.build_status_payload(
        current_version=VERSION,
        action_ref=config.action_ref,
        action_repository=config.action_repository,
        check_latest=True,
    )
    if not status:
        return
    os.environ["REPONOMICS_VERSION_STATUS_JSON"] = json.dumps(
        status,
        separators=(",", ":"),
    )
    if status.get("latest_version"):
        print(f"Version status available for {status['latest_version']}.")
    else:
        print("Version status available without latest-release details.")
