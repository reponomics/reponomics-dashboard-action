"""Offline diagnostics for generated Reponomics dashboard artifacts."""
# ruff: noqa: F401

from __future__ import annotations

import argparse
import os
from pathlib import Path

from doctor_modules.contracts import (
    _mode_match_stage,
    _validate_configured_mode,
    _validate_encrypted_contract,
    _validate_plain_contract,
)
from doctor_modules.core import _compat_stage, check_dashboard_key, diagnose_dashboard_artifact
from doctor_modules.data import (
    _diagnose_encrypted_secret,
    _diagnose_plain_data,
    _skip_secret_result,
)
from doctor_modules.discovery import (
    ENCRYPTED_DASHBOARD_META_NAME,
    EXPORT_MANIFEST_META_NAME,
    PLAINTEXT_DASHBOARD_META_NAME,
    _DashboardMetaParser,
    _dashboard_json_asset_path,
    _dashboard_meta_content,
    _optional_dashboard_json_source,
    _parse_dashboard_payload,
)
from doctor_modules.export import _diagnose_export_artifact
from doctor_modules.handoff import _ui_handoff_stage
from doctor_modules.manifest import _validate_export_manifest_contract
from doctor_modules.decode import _decrypt_gzip_json_staged
from doctor_modules.schema import (
    _semantic_counts_stage,
    _validate_chunk,
    _validate_chunk_staged,
    _validate_summary,
    _validate_summary_staged,
)
from doctor_support import (
    CHUNK_ID_RE,
    ENCRYPTED_DASHBOARD_SCRIPT_ID,
    EXPECTED_DASHBOARD_DATA_VERSION,
    EXPECTED_EXPORT_MANIFEST_VERSION,
    EXPECTED_IV_BYTES,
    EXPECTED_KDF_HASH,
    EXPECTED_KDF_ITERATIONS,
    EXPECTED_KDF_NAME,
    EXPECTED_SALT_BYTES,
    EXPORT_ASSET_RE,
    EXPORT_MANIFEST_SCRIPT_ID,
    PLAINTEXT_DASHBOARD_SCRIPT_ID,
    SHA256_HEX_RE,
    DashboardDoctorError as _DashboardDoctorError,
    DashboardDoctorResult,
    DashboardKeyCheckResult,
    DetectedDashboardMode,
    DoctorDataMode,
    DoctorSecretResult,
    DoctorStage,
    DoctorStageStatus,
    _accepted_secret_values,
    _all_required_stage_statuses_passed,
    _any_failed,
    _b64_decode,
    _derive_key,
    _first_status,
    _json_object,
    _object_dict,
    _optional_script_content,
    _stage,
    _stage_passed,
    _status_from_stages,
    _validate_encrypted_blob_token,
)


__all__ = [
    "CHUNK_ID_RE",
    "ENCRYPTED_DASHBOARD_META_NAME",
    "ENCRYPTED_DASHBOARD_SCRIPT_ID",
    "EXPECTED_DASHBOARD_DATA_VERSION",
    "EXPECTED_EXPORT_MANIFEST_VERSION",
    "EXPECTED_IV_BYTES",
    "EXPECTED_KDF_HASH",
    "EXPECTED_KDF_ITERATIONS",
    "EXPECTED_KDF_NAME",
    "EXPECTED_SALT_BYTES",
    "EXPORT_ASSET_RE",
    "EXPORT_MANIFEST_META_NAME",
    "EXPORT_MANIFEST_SCRIPT_ID",
    "PLAINTEXT_DASHBOARD_META_NAME",
    "PLAINTEXT_DASHBOARD_SCRIPT_ID",
    "SHA256_HEX_RE",
    "DashboardDoctorResult",
    "DashboardKeyCheckResult",
    "DetectedDashboardMode",
    "DoctorDataMode",
    "DoctorSecretResult",
    "DoctorStage",
    "DoctorStageStatus",
    "_DashboardDoctorError",
    "_DashboardMetaParser",
    "_accepted_secret_values",
    "_all_required_stage_statuses_passed",
    "_any_failed",
    "_b64_decode",
    "_compat_stage",
    "_dashboard_json_asset_path",
    "_dashboard_meta_content",
    "_decrypt_gzip_json_staged",
    "_derive_key",
    "_diagnose_encrypted_secret",
    "_diagnose_export_artifact",
    "_diagnose_plain_data",
    "_first_status",
    "_json_object",
    "_mode_match_stage",
    "_object_dict",
    "_optional_dashboard_json_source",
    "_optional_script_content",
    "_parse_dashboard_payload",
    "_semantic_counts_stage",
    "_skip_secret_result",
    "_stage",
    "_stage_passed",
    "_status_from_stages",
    "_ui_handoff_stage",
    "_validate_chunk",
    "_validate_chunk_staged",
    "_validate_configured_mode",
    "_validate_encrypted_blob_token",
    "_validate_encrypted_contract",
    "_validate_export_manifest_contract",
    "_validate_plain_contract",
    "_validate_summary",
    "_validate_summary_staged",
    "check_dashboard_key",
    "diagnose_dashboard_artifact",
]


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dashboard-html", type=Path, required=True)
    parser.add_argument(
        "--dashboard-key",
        help="Dashboard key to check. Prefer DASHBOARD_SECRET_DO_NOT_REPLACE.",
    )
    parser.add_argument("--chunk-limit", type=int)
    args = parser.parse_args()

    dashboard_key = args.dashboard_key or os.environ.get("DASHBOARD_SECRET_DO_NOT_REPLACE", "")
    if not dashboard_key:
        print("DASHBOARD_KEY_CHECK: failed")
        print("STAGE: missing_secret")
        print("DETAIL: dashboard key was not provided")
        return 1

    result = check_dashboard_key(
        args.dashboard_html,
        dashboard_key,
        chunk_limit=args.chunk_limit,
    )
    status = "success" if result.ok else "failed"
    print(f"DASHBOARD_KEY_CHECK: {status}")
    print(f"STAGE: {result.stage}")
    print(f"DETAIL: {result.detail}")
    if result.ok:
        print(f"REPO_COUNT: {result.repo_count}")
        print(f"CHUNKS_CHECKED: {result.chunks_checked}/{result.chunk_count}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())
