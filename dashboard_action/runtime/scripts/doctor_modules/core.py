"""High-level dashboard doctor orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeGuard

from doctor_modules.contracts import (
    _mode_match_stage,
    _validate_configured_mode,
    _validate_encrypted_contract,
    _validate_plain_contract,
)
from doctor_modules.data import (
    _diagnose_encrypted_secret,
    _diagnose_plain_data,
    _skip_secret_result,
)
from doctor_modules.discovery import _parse_dashboard_payload
from doctor_modules.export import _diagnose_export_artifact
from doctor_modules.handoff import _ui_handoff_stage
from doctor_modules.result import _PayloadDiagnosticResult, _compat_stage, _dashboard_result
from doctor_retained import _diagnose_retained_artifact
from doctor_support import (
    DetectedDashboardMode,
    DoctorDataMode,
    DoctorSecretResult,
    DoctorStage,
    DoctorStageStatus,
    DashboardDoctorResult,
    DashboardKeyCheckResult,
    _first_status,
    _stage,
)


@dataclass(frozen=True)
class _SecretCoverage:
    """The chunk/repo coverage reported by the best accepted dashboard secret."""

    chunks_checked: int = 0
    chunk_count: int = 0
    repo_count: int = 0

    def with_candidate(
        self,
        result: DoctorSecretResult,
        *,
        chunks_checked: int,
        chunk_count: int,
        repo_count: int,
    ) -> _SecretCoverage:
        """Keep the accepted secret result that checked the most chunks."""
        if result.accepted and chunks_checked >= self.chunks_checked:
            return _SecretCoverage(
                chunks_checked=chunks_checked,
                chunk_count=chunk_count,
                repo_count=repo_count,
            )
        return self


def diagnose_dashboard_artifact(
    dashboard_html_path: Path,
    *,
    configured_data_mode: str = "encrypted",
    secrets: list[tuple[str, str]] | None = None,
    chunk_limit: int | None = None,
    retained_data_dir: Path | None = None,
) -> DashboardDoctorResult:
    """Run staged diagnostics for a rendered dashboard HTML artifact."""
    configured_mode, stages, secret_inputs = _start_dashboard_diagnosis(
        configured_data_mode,
        secrets,
    )

    try:
        html = _read_dashboard_html(dashboard_html_path)
    except OSError as exc:
        return _unreadable_dashboard_result(dashboard_html_path, configured_mode, stages, exc)

    stages.append(_stage("dashboard_html_found", "passed", "dashboard HTML was readable"))
    detected_mode, payload = _record_dashboard_payload(
        stages,
        html,
        dashboard_html_path,
        configured_mode,
    )
    payload_result = _diagnose_payload(payload, detected_mode, secret_inputs, chunk_limit)
    stages.extend(payload_result.stages)
    retained_status = _record_retained_artifact_diagnostics(
        stages,
        retained_data_dir,
        configured_mode,
        secret_inputs,
        payload_result.secret_results,
    )
    export_status = _record_export_artifact_diagnostics(
        stages,
        html,
        dashboard_html_path,
        detected_mode,
        secret_inputs,
        payload_result.secret_results,
    )
    _record_ui_handoff_boundary(stages, configured_mode, detected_mode, payload_result)
    return _dashboard_result(
        dashboard_html_path=dashboard_html_path,
        configured_mode=configured_mode,
        detected_mode=detected_mode,
        stages=stages,
        payload_result=payload_result,
        retained_status=retained_status,
        export_status=export_status,
    )


def _start_dashboard_diagnosis(
    configured_data_mode: str,
    secrets: list[tuple[str, str]] | None,
) -> tuple[DoctorDataMode, list[DoctorStage], list[tuple[str, str]]]:
    """Normalize configuration and create the first diagnostic stage list."""
    configured_mode, configured_stage = _validate_configured_mode(configured_data_mode)
    return configured_mode, [configured_stage], secrets or []


def _read_dashboard_html(dashboard_html_path: Path) -> str:
    """Read the dashboard HTML so the caller can record success or failure."""
    return dashboard_html_path.read_text(encoding="utf-8")


def _record_dashboard_payload(
    stages: list[DoctorStage],
    html: str,
    dashboard_html_path: Path,
    configured_mode: DoctorDataMode,
) -> tuple[DetectedDashboardMode, dict[str, Any] | None]:
    """Detect the embedded payload and append the mode-matching stages."""
    detected_mode, payload, payload_stages = _parse_dashboard_payload(html, dashboard_html_path)
    stages.extend(payload_stages)
    stages.append(_mode_match_stage(configured_mode, detected_mode))
    return detected_mode, payload


def _diagnose_payload(
    payload: dict[str, Any] | None,
    detected_mode: DetectedDashboardMode,
    secret_inputs: list[tuple[str, str]],
    chunk_limit: int | None,
) -> _PayloadDiagnosticResult:
    """Choose the payload diagnostic path that matches the detected mode."""
    if _detected_encrypted_mode(detected_mode) and _payload_is_available(payload):
        return _diagnose_encrypted_payload(payload, secret_inputs, chunk_limit)
    if _detected_plaintext_mode(detected_mode) and _payload_is_available(payload):
        return _diagnose_plaintext_payload(payload, secret_inputs)
    return _diagnose_missing_payload(secret_inputs)


def _detected_encrypted_mode(detected_mode: DetectedDashboardMode) -> bool:
    """Return whether payload discovery selected encrypted dashboard mode."""
    return detected_mode == "encrypted"


def _detected_plaintext_mode(detected_mode: DetectedDashboardMode) -> bool:
    """Return whether payload discovery selected plaintext dashboard mode."""
    return detected_mode == "plaintext"


def _payload_is_available(
    payload: dict[str, Any] | None,
) -> TypeGuard[dict[str, Any]]:
    """Return whether parsed payload data is available for contract checks."""
    return payload is not None


def _diagnose_encrypted_payload(
    payload: dict[str, Any],
    secret_inputs: list[tuple[str, str]],
    chunk_limit: int | None,
) -> _PayloadDiagnosticResult:
    """Validate the encrypted envelope and diagnose each supplied secret."""
    stages, salt = _validate_encrypted_contract(payload)
    secret_results, coverage = _diagnose_encrypted_secret_inputs(
        secret_inputs,
        payload,
        salt,
        chunk_limit,
    )
    return _PayloadDiagnosticResult(
        stages=stages,
        secret_results=secret_results,
        chunks_checked=coverage.chunks_checked,
        chunk_count=coverage.chunk_count,
        repo_count=coverage.repo_count,
    )


def _diagnose_encrypted_secret_inputs(
    secret_inputs: list[tuple[str, str]],
    payload: dict[str, Any],
    salt: bytes | None,
    chunk_limit: int | None,
) -> tuple[list[DoctorSecretResult], _SecretCoverage]:
    """Diagnose every encrypted-mode secret and retain the best accepted coverage."""
    secret_results: list[DoctorSecretResult] = []
    coverage = _SecretCoverage()
    for label, secret in secret_inputs:
        result, candidate_coverage = _diagnose_one_encrypted_secret(
            label,
            secret,
            payload,
            salt,
            chunk_limit,
        )
        secret_results.append(result)
        coverage = coverage.with_candidate(
            result,
            chunks_checked=candidate_coverage.chunks_checked,
            chunk_count=candidate_coverage.chunk_count,
            repo_count=candidate_coverage.repo_count,
        )
    return secret_results, coverage


def _diagnose_one_encrypted_secret(
    label: str,
    secret: str,
    payload: dict[str, Any],
    salt: bytes | None,
    chunk_limit: int | None,
) -> tuple[DoctorSecretResult, _SecretCoverage]:
    """Return the diagnostic result and coverage for one encrypted-mode secret."""
    if not secret:
        return _missing_encrypted_secret_result(label), _SecretCoverage()
    result, chunks_checked, chunk_count, repo_count = _diagnose_encrypted_secret(
        label,
        secret,
        payload,
        salt,
        chunk_limit=chunk_limit,
    )
    return result, _SecretCoverage(
        chunks_checked=chunks_checked,
        chunk_count=chunk_count,
        repo_count=repo_count,
    )


def _missing_encrypted_secret_result(label: str) -> DoctorSecretResult:
    """Build the skipped diagnostic result for an unset encrypted-mode secret."""
    return _skip_secret_result(label, provided=False, detail="secret was not configured")


def _diagnose_plaintext_payload(
    payload: dict[str, Any],
    secret_inputs: list[tuple[str, str]],
) -> _PayloadDiagnosticResult:
    """Validate plaintext payload contracts and mark supplied secrets as irrelevant."""
    stages = _validate_plain_contract(payload)
    plain_stages, chunks_checked, chunk_count, repo_count = _diagnose_plain_data(payload)
    stages.extend(plain_stages)
    return _PayloadDiagnosticResult(
        stages=stages,
        secret_results=_plaintext_secret_results(secret_inputs),
        chunks_checked=chunks_checked,
        chunk_count=chunk_count,
        repo_count=repo_count,
    )


def _plaintext_secret_results(secret_inputs: list[tuple[str, str]]) -> list[DoctorSecretResult]:
    """Build skipped secret diagnostics for plaintext dashboards."""
    return [
        _skip_secret_result(
            label,
            provided=bool(secret),
            detail="plaintext mode has no dashboard decryption key",
        )
        for label, secret in secret_inputs
    ]


def _diagnose_missing_payload(
    secret_inputs: list[tuple[str, str]],
) -> _PayloadDiagnosticResult:
    """Mark secret diagnostics as skipped when no dashboard payload was available."""
    return _PayloadDiagnosticResult(
        stages=[],
        secret_results=_payload_unavailable_secret_results(secret_inputs),
    )


def _payload_unavailable_secret_results(
    secret_inputs: list[tuple[str, str]],
) -> list[DoctorSecretResult]:
    """Build skipped secret diagnostics for dashboards without payload data."""
    return [
        _skip_secret_result(
            label,
            provided=bool(secret),
            detail="dashboard payload was unavailable",
        )
        for label, secret in secret_inputs
    ]


def _record_retained_artifact_diagnostics(
    stages: list[DoctorStage],
    retained_data_dir: Path | None,
    configured_mode: DoctorDataMode,
    secret_inputs: list[tuple[str, str]],
    secret_results: list[DoctorSecretResult],
) -> DoctorStageStatus:
    """Append retained workflow artifact diagnostics and return their status."""
    retained_stages, retained_status = _diagnose_retained_artifact(
        retained_data_dir,
        configured_mode=configured_mode,
        secret_inputs=secret_inputs,
        secret_results=secret_results,
    )
    stages.extend(retained_stages)
    return retained_status


def _record_export_artifact_diagnostics(
    stages: list[DoctorStage],
    html: str,
    dashboard_html_path: Path,
    detected_mode: DetectedDashboardMode,
    secret_inputs: list[tuple[str, str]],
    secret_results: list[DoctorSecretResult],
) -> DoctorStageStatus:
    """Append encrypted export artifact diagnostics and return their status."""
    export_stages, export_status = _diagnose_export_artifact(
        html,
        dashboard_html_path,
        detected_mode=detected_mode,
        secret_inputs=secret_inputs,
        secret_results=secret_results,
    )
    stages.extend(export_stages)
    return export_status


def _record_ui_handoff_boundary(
    stages: list[DoctorStage],
    configured_mode: DoctorDataMode,
    detected_mode: DetectedDashboardMode,
    payload_result: _PayloadDiagnosticResult,
) -> None:
    """Append the final browser/UI handoff boundary stage."""
    stages.append(
        _ui_handoff_stage(
            configured_mode=configured_mode,
            detected_mode=detected_mode,
            stages=stages,
            secret_results=payload_result.secret_results,
            repo_count=payload_result.repo_count,
        )
    )


def _unreadable_dashboard_result(
    dashboard_html_path: Path,
    configured_mode: DoctorDataMode,
    stages: list[DoctorStage],
    exc: OSError,
) -> DashboardDoctorResult:
    """Return the terminal diagnostic result for an unreadable dashboard file."""
    stages.append(
        _stage("dashboard_html_found", "failed", f"dashboard HTML was not readable: {exc}")
    )
    stages.extend(_blocked_artifact_stages_for_missing_html())
    return DashboardDoctorResult(
        configured_data_mode=configured_mode,
        detected_dashboard_mode="unknown",
        dashboard_html_found="failed",
        browser_payload_contract_valid="skipped",
        key_cryptographically_accepted="skipped",
        dashboard_data_well_formed="skipped",
        dashboard_data_semantically_consistent="skipped",
        repo_chunks_valid="skipped",
        retained_data_artifact_decryptable="skipped",
        export_artifact_valid="skipped",
        secret_results=[],
        stages=stages,
        dashboard_html_path=dashboard_html_path.as_posix(),
    )


def _blocked_artifact_stages_for_missing_html() -> list[DoctorStage]:
    """Build the skipped downstream stages caused by unreadable HTML."""
    return [
        _stage(
            "workflow_artifact_restore_requested",
            "skipped",
            "retained workflow artifact restore is not implemented in this diagnostic slice",
        ),
        _stage(
            "export_manifest_found",
            "skipped",
            "export diagnostics are not implemented in this diagnostic slice",
        ),
        _stage("ui_handoff_boundary_reached", "failed", "dashboard HTML was unavailable"),
    ]


def check_dashboard_key(
    dashboard_html_path: Path,
    dashboard_key: str,
    *,
    chunk_limit: int | None = None,
) -> DashboardKeyCheckResult:
    """Check whether a supplied key decrypts an encrypted dashboard HTML artifact."""
    result = diagnose_dashboard_artifact(
        dashboard_html_path,
        configured_data_mode="encrypted",
        secrets=[("DASHBOARD_SECRET_DO_NOT_REPLACE", dashboard_key)],
        chunk_limit=chunk_limit,
    )
    secret_result = _first_secret_result(result)
    if _dashboard_key_was_accepted(result, secret_result):
        return _successful_key_check(result)
    failed_stage = _key_check_failure_stage(result, secret_result)
    return _failed_key_check(failed_stage)


def _first_secret_result(result: DashboardDoctorResult) -> DoctorSecretResult | None:
    """Return the compatibility key-check secret result, when one exists."""
    return result.secret_results[0] if result.secret_results else None


def _dashboard_key_was_accepted(
    result: DashboardDoctorResult,
    secret_result: DoctorSecretResult | None,
) -> bool:
    """Return whether the supplied key passed crypto checks and reached UI handoff."""
    return secret_result is not None and secret_result.accepted and result.ui_handoff_reached


def _successful_key_check(result: DashboardDoctorResult) -> DashboardKeyCheckResult:
    """Build the legacy success result for `check_dashboard_key` callers."""
    return DashboardKeyCheckResult(
        ok=True,
        stage="success",
        detail="supplied key decrypts this dashboard",
        chunks_checked=result.chunks_checked,
        chunk_count=result.chunk_count,
        repo_count=result.repo_count,
    )


def _key_check_failure_stage(
    result: DashboardDoctorResult,
    secret_result: DoctorSecretResult | None,
) -> DoctorStage:
    """Choose the most specific failed stage for the legacy key-check result."""
    failed_stage = (
        secret_result.terminal_stage
        if secret_result is not None
        else _first_status(result.stages, "failed")
    )
    return failed_stage or DoctorStage(
        "unknown",
        "failed",
        detail="dashboard diagnostics did not pass",
    )


def _failed_key_check(failed_stage: DoctorStage) -> DashboardKeyCheckResult:
    """Build the legacy failed result for `check_dashboard_key` callers."""
    compat_stage, detail = _compat_stage(failed_stage)
    return DashboardKeyCheckResult(ok=False, stage=compat_stage, detail=detail)
