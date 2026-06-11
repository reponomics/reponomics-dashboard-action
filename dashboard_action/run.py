"""Orchestrate the bundled Reponomics runtime for GitHub Actions."""
# ruff: noqa: F401

from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
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
    escape_workflow_data,
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
import doctor as doctor_mod  # noqa: E402
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
    merge.materialize_reporting_coverage()
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


def _summary_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _doctor_stage_status(stages: list[doctor_mod.DoctorStage], name: str) -> str:
    for stage in stages:
        if stage.name == name:
            return stage.status
    return "skipped"


def _doctor_stage_detail(stages: list[doctor_mod.DoctorStage], name: str) -> str:
    for stage in stages:
        if stage.name == name:
            return stage.detail
    return ""


def _write_doctor_report_output(report_path: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"doctor-report-path={report_path}\n")


def _doctor_platform_stage(
    name: str,
    status: doctor_mod.DoctorStageStatus,
    detail: str,
) -> doctor_mod.DoctorStage:
    return doctor_mod.DoctorStage(
        name=name,
        status=status,
        subject="GitHub Pages",
        detail=detail,
    )


def _doctor_skipped_pages_stages(detail: str) -> list[doctor_mod.DoctorStage]:
    return [
        _doctor_platform_stage("pages_configuration_found", "skipped", detail),
        _doctor_platform_stage("pages_source_valid", "skipped", detail),
        _doctor_platform_stage("pages_deployment_permission_valid", "skipped", detail),
        _doctor_platform_stage("pages_latest_deployment_valid", "skipped", detail),
    ]


def _doctor_pages_status(stages: list[doctor_mod.DoctorStage]) -> str:
    page_stages = [stage for stage in stages if stage.name.startswith("pages_")]
    if not page_stages:
        return "skipped"
    if any(stage.status == "failed" for stage in page_stages):
        return "failed"
    if any(stage.status == "warning" for stage in page_stages):
        return "warning"
    if any(stage.status == "passed" for stage in page_stages):
        return "passed"
    return "skipped"


def _doctor_pages_preflight_stages(config: RuntimeConfig) -> list[doctor_mod.DoctorStage]:
    if not config.publish_pages:
        return _doctor_skipped_pages_stages("publish-pages is disabled for this artifact mode")
    if not config.github_token:
        return _doctor_skipped_pages_stages("github-token was not provided; Pages API preflight was not run")

    try:
        owner, repo = _github_repository()
    except ActionError as exc:
        return _doctor_skipped_pages_stages(f"GITHUB_REPOSITORY was unavailable: {exc}")

    url = f"https://api.github.com/repos/{owner}/{repo}/pages"
    try:
        response = requests.get(
            url,
            headers=_github_api_headers(config.github_token),
            timeout=INCIDENT_API_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return [
            _doctor_platform_stage(
                "pages_configuration_found",
                "warning",
                f"Pages API request failed: {exc.__class__.__name__}: {exc}",
            ),
            *_doctor_skipped_pages_stages("Pages API preflight did not complete")[1:],
        ]

    if response.status_code == 404:
        return [
            _doctor_platform_stage(
                "pages_configuration_found",
                "failed",
                "GitHub Pages is not enabled or was not visible to this token",
            ),
            *_doctor_skipped_pages_stages("Pages configuration was unavailable")[1:],
        ]
    if response.status_code in {401, 403}:
        detail = f"Pages API denied access with status {response.status_code}"
        return [
            _doctor_platform_stage("pages_configuration_found", "warning", detail),
            _doctor_platform_stage("pages_source_valid", "skipped", detail),
            _doctor_platform_stage("pages_deployment_permission_valid", "warning", detail),
            _doctor_platform_stage("pages_latest_deployment_valid", "skipped", detail),
        ]
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        return [
            _doctor_platform_stage(
                "pages_configuration_found",
                "warning",
                f"Pages API request failed with status {response.status_code}: {exc}",
            ),
            *_doctor_skipped_pages_stages("Pages API preflight did not complete")[1:],
        ]

    try:
        payload = response.json()
    except ValueError as exc:
        return [
            _doctor_platform_stage(
                "pages_configuration_found",
                "warning",
                f"Pages API returned invalid JSON: {exc}",
            ),
            *_doctor_skipped_pages_stages("Pages API payload was invalid")[1:],
        ]
    if not isinstance(payload, dict):
        return [
            _doctor_platform_stage("pages_configuration_found", "warning", "Pages API payload was not an object"),
            *_doctor_skipped_pages_stages("Pages API payload was invalid")[1:],
        ]

    source_detail = _doctor_pages_source_detail(payload)
    deployment_detail = _doctor_pages_deployment_detail(payload)
    return [
        _doctor_platform_stage("pages_configuration_found", "passed", "GitHub Pages configuration is available"),
        _doctor_platform_stage(*source_detail),
        _doctor_platform_stage(
            "pages_deployment_permission_valid",
            "skipped",
            "deploy-pages permission cannot be proven without attempting a deployment",
        ),
        _doctor_platform_stage(*deployment_detail),
    ]


def _doctor_pages_source_detail(payload: dict[str, object]) -> tuple[str, doctor_mod.DoctorStageStatus, str]:
    build_type = payload.get("build_type")
    if build_type == "workflow":
        return ("pages_source_valid", "passed", "GitHub Pages is configured for workflow deployments")
    if isinstance(build_type, str) and build_type:
        return (
            "pages_source_valid",
            "warning",
            f"GitHub Pages build_type is {build_type!r}, not workflow",
        )
    source = payload.get("source")
    if isinstance(source, dict):
        return (
            "pages_source_valid",
            "warning",
            "GitHub Pages source exists, but workflow deployment mode was not reported",
        )
    return ("pages_source_valid", "warning", "GitHub Pages source configuration was not reported")


def _doctor_pages_deployment_detail(payload: dict[str, object]) -> tuple[str, doctor_mod.DoctorStageStatus, str]:
    status = payload.get("status")
    if status == "built":
        return ("pages_latest_deployment_valid", "passed", "latest Pages status is built")
    if status in {"building", "queued", "pending"}:
        return ("pages_latest_deployment_valid", "warning", f"latest Pages status is {status!r}")
    if status in {"errored", "error", "failed"}:
        return ("pages_latest_deployment_valid", "failed", f"latest Pages status is {status!r}")
    if isinstance(status, str) and status:
        return ("pages_latest_deployment_valid", "warning", f"latest Pages status is {status!r}")
    return ("pages_latest_deployment_valid", "skipped", "latest Pages status was not reported")


def run_doctor(config: RuntimeConfig) -> None:
    """Run read-only dashboard artifact diagnostics."""
    key_checks = [
        ("DASHBOARD_SECRET_DO_NOT_REPLACE", config.dashboard_secret),
        ("COMPARISON_SECRET", config.comparison_secret),
    ]
    result = doctor_mod.diagnose_dashboard_artifact(
        config.pages_index_path,
        configured_artifact_mode=config.resolved_artifact_mode,
        secrets=key_checks,
        retained_data_dir=config.data_dir,
    )
    result.stages.extend(_doctor_pages_preflight_stages(config))
    report_path = Path(".reponomics") / "doctor" / "doctor-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result.to_jsonable(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_doctor_report_output(report_path.as_posix())

    rows: list[tuple[str, str, str, str, str]] = []
    for secret_result in result.secret_results:
        if not secret_result.provided:
            rows.append(
                (
                    secret_result.label,
                    "not provided",
                    "skipped",
                    "skipped",
                    "secret was not configured",
                )
            )
            continue
        auth_status = _doctor_stage_status(secret_result.stages, "summary_authenticates")
        terminal = secret_result.terminal_stage
        rows.append(
            (
                secret_result.label,
                "provided",
                auth_status,
                terminal.name,
                terminal.detail,
            )
        )
        if not secret_result.accepted and result.detected_dashboard_mode == "encrypted":
            warning = (
                f"{secret_result.label} failed at stage {terminal.name}: {terminal.detail}"
            )
            print(
                "::warning title=Reponomics doctor key check::"
                + escape_workflow_data(warning)
            )

    counts = result.stage_counts
    handoff_detail = _doctor_stage_detail(result.stages, "ui_handoff_boundary_reached")
    lines = [
        "## Reponomics dashboard doctor",
        "",
        f"- Dashboard HTML: `{config.pages_index_path.as_posix()}`",
        f"- JSON report: `{report_path.as_posix()}`",
        f"- Configured artifact mode: `{result.configured_artifact_mode}`",
        f"- Detected dashboard mode: `{result.detected_dashboard_mode}`",
        f"- Provided keys checked: `{result.provided_secret_count}`",
        f"- Keys cryptographically accepted: `{result.accepted_secret_count}`",
        f"- Browser/UI handoff boundary: `{_doctor_stage_status(result.stages, 'ui_handoff_boundary_reached')}`",
        f"- Interpretation: {_summary_cell(handoff_detail)}",
        "",
        "| Outcome | Status |",
        "| --- | --- |",
        f"| Dashboard HTML found | `{result.dashboard_html_found}` |",
        f"| Browser payload contract valid | `{result.browser_payload_contract_valid}` |",
        f"| Key cryptographically accepted | `{result.key_cryptographically_accepted}` |",
        f"| Dashboard data well formed | `{result.dashboard_data_well_formed}` |",
        f"| Dashboard data semantically consistent | `{result.dashboard_data_semantically_consistent}` |",
        f"| Repo chunks valid | `{result.repo_chunks_valid}` |",
        f"| Retained workflow artifact decryptable | `{result.retained_data_artifact_decryptable}` |",
        f"| Export artifact valid | `{result.export_artifact_valid}` |",
        f"| Pages deployability preflight | `{_doctor_pages_status(result.stages)}` |",
        "",
        "| Stage status | Count |",
        "| --- | ---: |",
        f"| passed | {counts.get('passed', 0)} |",
        f"| failed | {counts.get('failed', 0)} |",
        f"| warning | {counts.get('warning', 0)} |",
        f"| skipped | {counts.get('skipped', 0)} |",
        "",
        "| Secret | Provided | Summary authentication | Terminal stage | Detail |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| `{label}` | {_summary_cell(provided)} | `{_summary_cell(auth_status)}` | `{_summary_cell(stage)}` | {_summary_cell(detail)} |"
        for label, provided, auth_status, stage, detail in rows
    )
    lines.extend(
        [
            "",
            "### Diagnostic stages",
            "",
            "| Stage | Status | Subject | Detail |",
            "| --- | --- | --- | --- |",
        ]
    )
    for stage in result.stages:
        lines.append(
            f"| `{_summary_cell(stage.name)}` | `{stage.status}` | {_summary_cell(stage.subject)} | {_summary_cell(stage.detail)} |"
        )
    summaries_mod._write_summary(lines)

    encrypted_diagnostics = (
        result.configured_artifact_mode == "encrypted"
        or result.detected_dashboard_mode == "encrypted"
    )
    if encrypted_diagnostics and result.provided_secret_count == 0:
        raise ActionError(
            "doctor mode requires dashboard-secret or comparison-secret to check dashboard decryption."
        )
    if encrypted_diagnostics and result.accepted_secret_count == 0:
        print("::error title=Reponomics doctor key check::No provided key decrypted the dashboard")
        raise ActionError("No provided dashboard key could decrypt the dashboard artifact.")
    if result.dashboard_html_found == "failed":
        raise ActionError("Doctor could not inspect the dashboard HTML artifact.")
    if not result.ui_handoff_reached:
        print(
            "::error title=Reponomics doctor diagnostics::"
            + escape_workflow_data(
                "Dashboard payload did not reach browser/UI handoff boundary: "
                + handoff_detail
            )
        )
        raise ActionError(
            "Doctor staged diagnostics did not reach the browser/UI handoff boundary."
        )


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
    elif config.mode == "doctor":
        run_doctor(config)
    elif _parse_bool(
        _env("REPONOMICS_INCIDENT_RESET_PURGE_ONLY", "false"),
        name="incident-reset-purge-only",
    ):
        run_incident_reset_purge(config)
    else:
        run_incident_reset(config)


if __name__ == "__main__":
    main()
