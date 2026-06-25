"""Encrypted export artifact diagnostics for doctor mode."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from doctor_modules.discovery import EXPORT_MANIFEST_META_NAME, _optional_dashboard_json_source
from doctor_modules.export_asset import (
    _blocked_export_stages,
    _diagnose_export_decryption,
    _read_export_ciphertext,
    _record_export_ciphertext_integrity,
)
from doctor_modules.manifest import _validate_export_manifest_contract
from doctor_support import (
    EXPORT_MANIFEST_SCRIPT_ID,
    DashboardDoctorError as _DashboardDoctorError,
    DetectedDashboardMode,
    DoctorSecretResult,
    DoctorStage,
    DoctorStageStatus,
    _any_failed,
    _json_object,
    _stage,
)


@dataclass(frozen=True)
class _ExportManifestResult:
    """Loaded and validated export manifest data."""

    stages: list[DoctorStage]
    manifest: dict[str, Any] | None = None
    salt: bytes | None = None
    iv: bytes | None = None

    @property
    def is_usable(self) -> bool:
        """Return whether the manifest can drive export asset checks."""
        return self.manifest is not None and self.salt is not None and self.iv is not None


def _diagnose_export_artifact(
    html: str,
    dashboard_html_path: Path,
    *,
    detected_mode: DetectedDashboardMode,
    secret_inputs: list[tuple[str, str]],
    secret_results: list[DoctorSecretResult],
) -> tuple[list[DoctorStage], DoctorStageStatus]:
    """Diagnose the encrypted downloadable export artifact for encrypted dashboards."""
    if detected_mode != "encrypted":
        return _plaintext_export_result()

    manifest_result = _load_export_manifest(html, dashboard_html_path)
    stages = manifest_result.stages
    if not manifest_result.is_usable:
        return stages, "failed"

    assert manifest_result.manifest is not None
    assert manifest_result.salt is not None
    assert manifest_result.iv is not None
    ciphertext, asset_stages = _read_export_ciphertext(
        dashboard_html_path, manifest_result.manifest
    )
    stages.extend(asset_stages)
    if ciphertext is None:
        return stages, "failed"

    if not _record_export_ciphertext_integrity(stages, ciphertext, manifest_result.manifest):
        return stages, "failed"

    export_status = _diagnose_export_decryption(
        stages,
        ciphertext,
        manifest_result.manifest,
        manifest_result.salt,
        manifest_result.iv,
        secret_inputs,
        secret_results,
    )
    return stages, export_status


def _plaintext_export_result() -> tuple[list[DoctorStage], DoctorStageStatus]:
    """Return skipped export diagnostics for plaintext dashboards."""
    return [
        _stage(
            "export_manifest_found",
            "skipped",
            "plaintext mode has no encrypted export artifact",
        )
    ], "skipped"


def _load_export_manifest(html: str, dashboard_html_path: Path) -> _ExportManifestResult:
    """Load, parse, and validate the export manifest source."""
    content, manifest_label, manifest_detail, manifest_error = _optional_dashboard_json_source(
        html,
        dashboard_html_path,
        meta_name=EXPORT_MANIFEST_META_NAME,
        script_id=EXPORT_MANIFEST_SCRIPT_ID,
    )
    if manifest_error:
        return _ExportManifestResult(stages=_missing_manifest_stages(manifest_error))
    if not content:
        return _ExportManifestResult(
            stages=_missing_manifest_stages("export manifest was not found")
        )

    stages = [_stage("export_manifest_found", "passed", manifest_detail)]
    manifest = _parse_export_manifest_content(stages, content, manifest_label)
    if manifest is None:
        return _ExportManifestResult(stages=stages)

    manifest_stages, salt, iv = _validate_export_manifest_contract(manifest)
    stages.extend(manifest_stages)
    if _any_failed(manifest_stages) or salt is None or iv is None:
        stages.extend(
            _blocked_export_stages(
                "export manifest was invalid", include_asset=True, plaintext_hash=True
            )
        )
        return _ExportManifestResult(stages=stages)
    return _ExportManifestResult(stages=stages, manifest=manifest, salt=salt, iv=iv)


def _parse_export_manifest_content(
    stages: list[DoctorStage],
    content: str,
    manifest_label: str,
) -> dict[str, Any] | None:
    """Parse the export manifest JSON source and append parse failure stages."""
    try:
        return _json_object(content, manifest_label)
    except _DashboardDoctorError as exc:
        stages.append(_stage("export_manifest_valid", "failed", exc.detail))
        stages.extend(
            _blocked_export_stages(
                "export manifest was invalid", include_asset=True, plaintext_hash=True
            )
        )
        return None


def _missing_manifest_stages(detail: str) -> list[DoctorStage]:
    """Return stages for a missing or unreadable export manifest."""
    return [
        _stage("export_manifest_found", "failed", detail),
        _stage("export_manifest_valid", "skipped", "export manifest was unavailable"),
        *_blocked_export_stages(
            "export manifest was unavailable", include_asset=True, plaintext_hash=True
        ),
    ]
