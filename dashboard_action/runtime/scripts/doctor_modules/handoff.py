"""Browser/UI handoff readiness diagnostics."""

from __future__ import annotations

from doctor_support import (
    DetectedDashboardMode,
    DoctorDataMode,
    DoctorSecretResult,
    DoctorStage,
    _all_required_stage_statuses_passed,
    _stage,
)


def _ui_handoff_stage(
    *,
    configured_mode: DoctorDataMode,
    detected_mode: DetectedDashboardMode,
    stages: list[DoctorStage],
    secret_results: list[DoctorSecretResult],
    repo_count: int,
) -> DoctorStage:
    """Return whether diagnostics reached the browser/UI handoff boundary."""
    if _detected_mode_does_not_match_configuration(configured_mode, detected_mode):
        return _mode_mismatch_handoff_stage()

    prerequisites = _ui_handoff_prerequisites(configured_mode, repo_count)
    data_stages = list(stages)
    accepted_secret = next((result for result in secret_results if result.accepted), None)
    if _encrypted_mode_requires_accepted_secret(configured_mode):
        if accepted_secret is None:
            return _missing_accepted_secret_handoff_stage()
        data_stages.extend(accepted_secret.stages)

    if not _all_required_stage_statuses_passed(data_stages, prerequisites):
        return _failed_prerequisites_handoff_stage()
    return _passed_handoff_stage()


def _detected_mode_does_not_match_configuration(
    configured_mode: DoctorDataMode,
    detected_mode: DetectedDashboardMode,
) -> bool:
    """Return whether payload discovery contradicted the configured mode."""
    return detected_mode != configured_mode


def _encrypted_mode_requires_accepted_secret(configured_mode: DoctorDataMode) -> bool:
    """Return whether UI handoff depends on an authenticated dashboard secret."""
    return configured_mode == "encrypted"


def _mode_mismatch_handoff_stage() -> DoctorStage:
    """Build the UI handoff failure for incompatible configured/detected modes."""
    return _stage(
        "ui_handoff_boundary_reached",
        "failed",
        "configured and detected dashboard modes were not compatible",
    )


def _missing_accepted_secret_handoff_stage() -> DoctorStage:
    """Build the UI handoff failure for encrypted dashboards without a valid key."""
    return _stage(
        "ui_handoff_boundary_reached",
        "failed",
        "no supplied secret authenticated the encrypted dashboard summary",
    )


def _failed_prerequisites_handoff_stage() -> DoctorStage:
    """Build the UI handoff failure for failed storage or data-contract checks."""
    return _stage(
        "ui_handoff_boundary_reached",
        "failed",
        "one or more encryption, storage, or data-contract stages failed",
    )


def _passed_handoff_stage() -> DoctorStage:
    """Build the UI handoff success stage."""
    return _stage(
        "ui_handoff_boundary_reached",
        "passed",
        "rendered dashboard payload checks reached the browser/UI boundary",
    )


def _ui_handoff_prerequisites(configured_mode: DoctorDataMode, repo_count: int) -> set[str]:
    """Return the stage names required before handing off to browser/UI behavior."""
    prerequisites = {
        "dashboard_html_found",
        "configured_data_mode_recorded",
        "detected_dashboard_mode_recorded",
        "configured_detected_mode_match",
        "dashboard_script_json_valid",
        "browser_envelope_version_valid",
        "browser_envelope_encoding_valid",
        "browser_envelope_chunks_object_valid",
        "browser_envelope_chunk_count_valid",
        "browser_envelope_chunk_ids_valid",
        "summary_min_schema_valid",
        "summary_repo_chunk_mapping_valid",
        "semantic_counts_valid",
    }
    if repo_count > 0:
        prerequisites.update(
            {
                "chunk_payload_present",
                "chunk_json_valid",
                "chunk_min_schema_valid",
                "chunk_repo_matches_summary",
                "chunk_growth_contract_valid",
            }
        )
    if configured_mode == "encrypted":
        prerequisites.update(
            {
                "browser_envelope_cipher_valid",
                "browser_envelope_kdf_valid",
                "browser_envelope_salt_valid",
                "browser_envelope_summary_token_valid",
            }
        )
        if repo_count > 0:
            prerequisites.update({"chunk_authenticates", "chunk_decompresses"})
    return prerequisites
