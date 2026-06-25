"""Doctor result aggregation and compatibility helpers."""

from __future__ import annotations

from pathlib import Path

from doctor_support import (
    DetectedDashboardMode,
    DoctorDataMode,
    DoctorSecretResult,
    DoctorStage,
    DoctorStageStatus,
    DashboardDoctorResult,
    _status_from_stages,
)


BROWSER_STAGE_NAMES = {
    "browser_envelope_version_valid",
    "browser_envelope_cipher_valid",
    "browser_envelope_kdf_valid",
    "browser_envelope_encoding_valid",
    "browser_envelope_salt_valid",
    "browser_envelope_summary_token_valid",
    "browser_envelope_chunks_object_valid",
    "browser_envelope_chunk_count_valid",
    "browser_envelope_chunk_ids_valid",
}
SEMANTIC_STAGE_NAMES = {
    "summary_min_schema_valid",
    "summary_repo_chunk_mapping_valid",
    "chunk_repo_matches_summary",
    "chunk_growth_contract_valid",
    "semantic_counts_valid",
}
CHUNK_STAGE_NAMES = {
    "chunk_payload_present",
    "chunk_authenticates",
    "chunk_decompresses",
    "chunk_json_valid",
    "chunk_min_schema_valid",
    "chunk_repo_matches_summary",
    "chunk_growth_contract_valid",
}
WELL_FORMED_STAGE_NAMES = {
    "dashboard_script_json_valid",
    "summary_decompresses",
    "summary_json_valid",
    "summary_min_schema_valid",
    "chunk_decompresses",
    "chunk_json_valid",
}


class _PayloadDiagnosticResult:
    def __init__(
        self,
        *,
        stages: list[DoctorStage],
        secret_results: list[DoctorSecretResult],
        chunks_checked: int = 0,
        chunk_count: int = 0,
        repo_count: int = 0,
    ) -> None:
        self.stages = stages
        self.secret_results = secret_results
        self.chunks_checked = chunks_checked
        self.chunk_count = chunk_count
        self.repo_count = repo_count


def _dashboard_result(
    *,
    dashboard_html_path: Path,
    configured_mode: DoctorDataMode,
    detected_mode: DetectedDashboardMode,
    stages: list[DoctorStage],
    payload_result: _PayloadDiagnosticResult,
    retained_status: DoctorStageStatus,
    export_status: DoctorStageStatus,
) -> DashboardDoctorResult:
    accepted_secret = next(
        (result for result in payload_result.secret_results if result.accepted), None
    )
    if configured_mode == "plaintext":
        key_status: DoctorStageStatus = "skipped"
        data_stages = []
    else:
        key_status = "passed" if accepted_secret is not None else "failed"
        data_stages = accepted_secret.stages if accepted_secret is not None else []
    combined_data_stages = stages + data_stages
    return DashboardDoctorResult(
        configured_data_mode=configured_mode,
        detected_dashboard_mode=detected_mode,
        dashboard_html_found=_status_from_stages(stages, {"dashboard_html_found"}),
        browser_payload_contract_valid=_status_from_stages(stages, BROWSER_STAGE_NAMES),
        key_cryptographically_accepted=key_status,
        dashboard_data_well_formed=_status_from_stages(
            combined_data_stages, WELL_FORMED_STAGE_NAMES
        ),
        dashboard_data_semantically_consistent=_status_from_stages(
            combined_data_stages, SEMANTIC_STAGE_NAMES
        ),
        repo_chunks_valid=_status_from_stages(combined_data_stages, CHUNK_STAGE_NAMES),
        retained_data_artifact_decryptable=retained_status,
        export_artifact_valid=export_status,
        secret_results=payload_result.secret_results,
        stages=stages,
        dashboard_html_path=dashboard_html_path.as_posix(),
        chunks_checked=payload_result.chunks_checked,
        chunk_count=payload_result.chunk_count,
        repo_count=payload_result.repo_count,
    )


def _compat_stage(stage: DoctorStage) -> tuple[str, str]:
    if stage.name in {"summary_authenticates", "chunk_authenticates"}:
        return "decrypt", stage.detail
    if stage.name in {"summary_decompresses", "chunk_decompresses"}:
        return "decompress", stage.detail
    if stage.name in {"summary_json_valid", "chunk_json_valid", "dashboard_script_json_valid"}:
        return "parse", stage.detail
    if stage.name in {
        "summary_min_schema_valid",
        "summary_repo_chunk_mapping_valid",
        "chunk_min_schema_valid",
        "chunk_repo_matches_summary",
        "chunk_growth_contract_valid",
        "semantic_counts_valid",
    }:
        return "schema", stage.detail
    if stage.name == "chunk_payload_present":
        return "missing", stage.detail
    if stage.name.startswith("browser_envelope_"):
        return "payload_schema", stage.detail
    return stage.name, stage.detail
