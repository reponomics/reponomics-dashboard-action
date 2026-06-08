"""Orchestrate the bundled Reponomics runtime for GitHub Actions."""
# ruff: noqa: F401

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from typing import Callable

import requests

from .run_modules import docs as docs_mod
from .run_modules import env as env_mod
from .run_modules import github as github_mod
from .run_modules import github_artifacts as github_artifacts_mod
from .run_modules import io as io_mod
from .run_modules import provenance as provenance_mod
from .run_modules import summaries as summaries_mod
from .run_modules.validation import (
    _validate_incident_confirmations,
    _validate_secret,
    validate_collect_cleanup_config,
    validate_config,
)
from .run_modules.config import (
    _choice,
    _config_allow_docs_sync,
    _env,
    _first_env,
    _normalize_privacy_mode,
    _parse_bool,
    _parse_retention_days,
    _repo_is_public,
    _validate_artifact_run_id,
    load_config_from_env,
)
from .run_modules.core import (
    COLLECT_ROLLBACK_ARTIFACTS,
    COLLECT_PROVENANCE_ARTIFACT_NAME,
    COLLECT_PROVENANCE_DIR,
    COLLECT_PROVENANCE_PATH,
    DOCS_ACTION_VERSION_ENV,
    DOCS_STATE_STALE,
    DOCS_SYNC_STATE_ENV,
    DOCS_UPDATED_AT_ENV,
    INCIDENT_API_MAX_RETRIES,
    INCIDENT_API_TIMEOUT_SECONDS,
    INCIDENT_CONFIRM_IRREVERSIBLE,
    INCIDENT_CONFIRM_MODE,
    INCIDENT_CONFIRM_PURGE,
    MANAGED_DOCS_BUNDLE_DIR,
    MANAGED_DOCS_DASHBOARD_LINK_ENV,
    MANAGED_DOCS_NAMESPACE,
    MANAGED_DOCS_README_LINK_ENV,
    MIN_MASK_LENGTH,
    MIN_SECRET_LENGTH,
    ROOT,
    SCRIPTS_DIR,
    VALID_MODES,
    VALID_PRIVACY_MODES,
    VERSION as _CORE_VERSION,
    ActionError,
    ActiveRetentionCleanupResult,
    DashboardDataArtifactRef,
    IncidentPurgeResult,
    RuntimeConfig,
)
from .run_modules.docs import (
    _docs_result_with_state,
    _git_failure_text,
    _is_permission_failure,
    _is_push_race,
    _push_managed_docs_with_retry,
    _run_git_capture,
)
from .run_modules.env import (
    _mask_config_secrets,
    _mask_secret,
    _patch_runtime_paths,
    _relative_link_if_present,
    _set_empty_managed_docs_status_env,
    _set_managed_docs_link_env,
)
from .run_modules.github import _current_workflow_id, _github_api_headers, _github_delete
from .run_modules.github import _github_repository, _github_run_id
from .run_modules.github_artifacts import _artifact_sort_key
from .run_modules.io import (
    _decrypt_if_needed,
    _docs_sync_output_values,
    _encrypt_if_needed,
    _git_commit_readme,
    _manifest_value,
    _prepare_data_schema,
    _readme_svg_asset_paths,
    _render_outputs,
    _restore_artifact,
    _sha,
    _snapshot_outputs,
    _tracked_repos,
)
from .run_modules.summaries import (
    _summarize_active_retention_cleanup,
    _summarize_incident_reset_prepared,
    _summarize_incident_reset_purge,
    _summarize_rotation,
)

import bootstrap  # noqa: E402
import collect as collect_mod  # noqa: E402
import crypto_artifact  # noqa: E402
import lineage  # noqa: E402
import load_data  # noqa: E402
import managed_docs  # noqa: E402
import merge  # noqa: E402
import render_dashboard  # noqa: E402
import render_readme  # noqa: E402
import repo_config  # noqa: E402
import storage  # noqa: E402
import version_status  # noqa: E402


VERSION = _CORE_VERSION
_RUN_SET_MANAGED_DOCS_LINK_ENV = _set_managed_docs_link_env


def _sync_version() -> None:
    """Keep extracted helpers compatible with tests that patch run.VERSION."""
    env_mod.VERSION = VERSION
    io_mod.VERSION = VERSION
    docs_mod.VERSION = VERSION
    summaries_mod.VERSION = VERSION
    provenance_mod.VERSION = VERSION


def _set_managed_docs_status_env() -> None:
    _sync_version()
    env_mod._set_managed_docs_status_env()


def _set_runtime_env(config: RuntimeConfig, *, next_key: bool = False) -> None:
    _sync_version()
    patched_link_env = globals()["_set_managed_docs_link_env"]
    original_link_env = env_mod._set_managed_docs_link_env
    if patched_link_env is not _RUN_SET_MANAGED_DOCS_LINK_ENV:
        env_mod._set_managed_docs_link_env = patched_link_env
    try:
        env_mod._set_runtime_env(config, next_key=next_key)
    finally:
        env_mod._set_managed_docs_link_env = original_link_env


def _set_version_status_env(config: RuntimeConfig) -> None:
    _sync_version()
    env_mod._set_version_status_env(config)


def _git_commit_managed_docs(
    config: RuntimeConfig,
    result: managed_docs.ManagedDocsResult,
) -> managed_docs.ManagedDocsResult:
    _sync_version()
    return docs_mod._git_commit_managed_docs(config, result)


def _summarize_docs_sync(result: managed_docs.ManagedDocsResult) -> None:
    _sync_version()
    summaries_mod._summarize_docs_sync(result)


def _write_outputs(
    config: RuntimeConfig,
    before: dict[str, str],
    *,
    docs_result: managed_docs.ManagedDocsResult | None = None,
) -> None:
    _sync_version()
    io_mod._write_outputs(config, before, docs_result=docs_result)


def _purge_workflow_history(config: RuntimeConfig) -> IncidentPurgeResult:
    return github_artifacts_mod._purge_workflow_history(config)


def _cleanup_superseded_collect_artifacts(config: RuntimeConfig) -> ActiveRetentionCleanupResult:
    return github_artifacts_mod._cleanup_superseded_collect_artifacts(config)


def _github_fetch_json(url: str, headers: dict[str, str]) -> object:
    return github_mod._github_fetch_json(url, headers)


_RUN_GITHUB_FETCH_JSON = _github_fetch_json


def _list_workflow_run_ids(
    owner: str,
    repo: str,
    workflow_id: int,
    *,
    current_run_id: int,
    headers: dict[str, str],
) -> list[int]:
    patched_fetch_json = globals()["_github_fetch_json"]
    original_fetch_json = github_mod._github_fetch_json
    if patched_fetch_json is not _RUN_GITHUB_FETCH_JSON:
        github_mod._github_fetch_json = patched_fetch_json
    try:
        return github_mod._list_workflow_run_ids(
            owner,
            repo,
            workflow_id,
            current_run_id=current_run_id,
            headers=headers,
        )
    finally:
        github_mod._github_fetch_json = original_fetch_json


def _list_old_dashboard_data_artifacts(
    owner: str,
    repo: str,
    *,
    current_run_id: int,
    headers: dict[str, str],
) -> list[DashboardDataArtifactRef]:
    patched_fetch_json = globals()["_github_fetch_json"]
    original_fetch_json = github_mod._github_fetch_json
    if patched_fetch_json is not _RUN_GITHUB_FETCH_JSON:
        github_mod._github_fetch_json = patched_fetch_json
    try:
        return github_mod._list_old_dashboard_data_artifacts(
            owner,
            repo,
            current_run_id=current_run_id,
            headers=headers,
        )
    finally:
        github_mod._github_fetch_json = original_fetch_json


def _write_verified_lineage(
    config: RuntimeConfig,
    parent: lineage.PayloadSnapshot,
    *,
    operation: str,
) -> None:
    try:
        child = lineage.write_verified_lineage(
            config.data_dir,
            parent=parent,
            retention_days=config.retention_days,
            action_version=VERSION,
            operation=operation,
        )
    except lineage.LineageError as exc:
        raise ActionError(str(exc)) from exc
    print(
        "Verified dashboard-data lineage "
        + f"({operation}); payload digest {child.payload_digest[:12]}, semantic root {child.semantic_root_digest[:12]}."
    )


def _validate_parent_lineage(parent: lineage.PayloadSnapshot) -> None:
    try:
        lineage.validate_snapshot_lineage(parent)
    except lineage.LineageError as exc:
        raise ActionError(str(exc)) from exc


def run_collect(
    config: RuntimeConfig,
    *,
    restore_artifact: bool = True,
    execute_collect: bool = True,
) -> None:
    _patch_runtime_paths(config)
    _set_runtime_env(config)
    before = _snapshot_outputs(config)
    if restore_artifact:
        _restore_artifact(config)
    _decrypt_if_needed(config, secret_env="DASHBOARD_SECRET_DO_NOT_REPLACE")
    restored_parent = lineage.snapshot_payload(config.data_dir)
    _validate_parent_lineage(restored_parent)
    _prepare_data_schema(config)
    parent = lineage.snapshot_payload(config.data_dir)
    if execute_collect:
        collect_mod.main()
    merge.main()
    _write_verified_lineage(config, parent, operation="collect")
    _encrypt_if_needed(config, secret_env="DASHBOARD_SECRET_DO_NOT_REPLACE")
    if provenance_mod.should_write_collect_provenance():
        provenance_mod.write_collect_provenance(config)
    else:
        print("Skipping collect provenance outside GitHub Actions run context.")
    _write_outputs(config, before)


def run_publish(config: RuntimeConfig, *, restore_artifact: bool = True) -> None:
    _patch_runtime_paths(config)
    _set_runtime_env(config)
    before = _snapshot_outputs(config)
    require_collect_provenance = bool(config.artifact_run_id) or _parse_bool(
        _env("REPONOMICS_REQUIRE_COLLECT_PROVENANCE", "false"),
        name="require-collect-provenance",
    )
    if restore_artifact:
        _restore_artifact(
            config,
            artifact_name=COLLECT_PROVENANCE_ARTIFACT_NAME,
            data_dir=COLLECT_PROVENANCE_DIR,
            required=require_collect_provenance,
        )
    provenance = None
    if COLLECT_PROVENANCE_PATH.is_file():
        provenance = provenance_mod.read_collect_provenance()
        provenance_mod.validate_collect_provenance(
            provenance,
            config,
            require_current_runtime=True,
        )
        if config.artifact_run_id and provenance.workflow_run_id != config.artifact_run_id:
            raise ActionError(
                "Collect provenance workflow run ID "
                + f"{provenance.workflow_run_id} does not match requested artifact-run-id "
                + f"{config.artifact_run_id}."
            )
    elif require_collect_provenance:
        raise ActionError("Publish requires collect provenance for the requested artifact run.")
    if restore_artifact:
        if provenance is not None and not config.artifact_run_id:
            _restore_artifact(config, artifact_run_id=provenance.workflow_run_id)
        else:
            _restore_artifact(config)
    _decrypt_if_needed(config, secret_env="DASHBOARD_SECRET_DO_NOT_REPLACE")
    _prepare_data_schema(config)
    _set_version_status_env(config)
    _render_outputs(config, generate_readme=config.generate_readme)
    _git_commit_readme(config, "chore: publish Reponomics README dashboard [skip ci]")
    _write_outputs(config, before)


def run_rotate_key(config: RuntimeConfig, *, restore_artifact: bool = True) -> None:
    _patch_runtime_paths(config)
    _set_runtime_env(config)
    before = _snapshot_outputs(config)
    if restore_artifact:
        _restore_artifact(config)
    _decrypt_if_needed(config, secret_env="DASHBOARD_SECRET_DO_NOT_REPLACE")
    restored_parent = lineage.snapshot_payload(config.data_dir)
    _validate_parent_lineage(restored_parent)
    _prepare_data_schema(config)
    parent = lineage.snapshot_payload(config.data_dir)
    _write_verified_lineage(config, parent, operation="rotate-key")
    _set_runtime_env(config, next_key=True)
    _render_outputs(config, generate_readme=config.generate_readme)
    _encrypt_if_needed(config, secret_env="DASHBOARD_NEXT_SECRET")
    _git_commit_readme(config, "chore: rotate Reponomics README dashboard key [skip ci]")
    _summarize_rotation()
    _write_outputs(config, before)


def run_incident_reset(config: RuntimeConfig, *, restore_artifact: bool = True) -> None:
    _patch_runtime_paths(config)
    _set_runtime_env(config)
    before = _snapshot_outputs(config)
    if restore_artifact:
        _restore_artifact(config)
    _decrypt_if_needed(config, secret_env="DASHBOARD_SECRET_DO_NOT_REPLACE")
    restored_parent = lineage.snapshot_payload(config.data_dir)
    _validate_parent_lineage(restored_parent)
    _prepare_data_schema(config)
    parent = lineage.snapshot_payload(config.data_dir)
    _set_runtime_env(config, next_key=True)
    _write_verified_lineage(config, parent, operation="incident-reset")
    _encrypt_if_needed(config, secret_env="DASHBOARD_NEXT_SECRET")
    _summarize_incident_reset_prepared()
    _write_outputs(config, before)


def run_incident_reset_purge(config: RuntimeConfig) -> None:
    result = _purge_workflow_history(config)
    _summarize_incident_reset_purge(result)


def run_collect_retention_cleanup(config: RuntimeConfig) -> None:
    result = _cleanup_superseded_collect_artifacts(config)
    _summarize_active_retention_cleanup(result)


def run_docs_sync(config: RuntimeConfig) -> None:
    _sync_version()
    _patch_runtime_paths(config)
    before = _snapshot_outputs(config)
    try:
        result = managed_docs.sync_managed_docs(
            namespace=MANAGED_DOCS_NAMESPACE,
            bundle_dir=MANAGED_DOCS_BUNDLE_DIR,
            action_repository=config.action_repository or version_status.ACTION_REPOSITORY,
            action_version=VERSION,
            allowed=config.allow_docs_sync,
        )
    except managed_docs.ManagedDocsError as exc:
        raise ActionError(str(exc)) from exc
    result = _git_commit_managed_docs(config, result)
    _summarize_docs_sync(result)
    _write_outputs(config, before, docs_result=result)


def main(loader: Callable[[], RuntimeConfig] = load_config_from_env) -> None:
    try:
        config = loader()
        _mask_config_secrets(config)
        if _parse_bool(
            _env("REPONOMICS_COLLECT_RETENTION_CLEANUP_ONLY", "false"),
            name="collect-retention-cleanup-only",
        ):
            validate_collect_cleanup_config(config)
            run_collect_retention_cleanup(config)
            return
        validate_config(config)
        _dispatch(config)
    except ActionError as exc:
        print(f"Reponomics action error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _dispatch(config: RuntimeConfig) -> None:
    if config.mode == "collect":
        run_collect(config)
    elif config.mode == "publish":
        run_publish(config)
    elif config.mode == "rotate-key":
        run_rotate_key(config)
    elif config.mode == "docs-sync":
        run_docs_sync(config)
    elif _parse_bool(
        _env("REPONOMICS_INCIDENT_RESET_PURGE_ONLY", "false"),
        name="incident-reset-purge-only",
    ):
        run_incident_reset_purge(config)
    else:
        run_incident_reset(config)


if __name__ == "__main__":
    main()
