"""Encrypted export artifact diagnostics for doctor mode."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from doctor_modules.discovery import EXPORT_MANIFEST_META_NAME, _optional_dashboard_json_source
from doctor_modules.manifest import _validate_export_manifest_contract
from doctor_support import (
    EXPORT_MANIFEST_SCRIPT_ID,
    DashboardDoctorError as _DashboardDoctorError,
    DetectedDashboardMode,
    DoctorSecretResult,
    DoctorStage,
    DoctorStageStatus,
    _accepted_secret_values,
    _any_failed,
    _derive_key,
    _json_object,
    _stage,
)


def _diagnose_export_artifact(
    html: str,
    dashboard_html_path: Path,
    *,
    detected_mode: DetectedDashboardMode,
    secret_inputs: list[tuple[str, str]],
    secret_results: list[DoctorSecretResult],
) -> tuple[list[DoctorStage], DoctorStageStatus]:
    if detected_mode != "encrypted":
        return [
            _stage(
                "export_manifest_found",
                "skipped",
                "plaintext mode has no encrypted export artifact",
            )
        ], "skipped"

    manifest_result = _load_export_manifest(html, dashboard_html_path)
    stages = manifest_result.stages
    if (
        manifest_result.manifest is None
        or manifest_result.salt is None
        or manifest_result.iv is None
    ):
        return stages, "failed"

    ciphertext, asset_stages = _read_export_ciphertext(
        dashboard_html_path, manifest_result.manifest
    )
    stages.extend(asset_stages)
    if ciphertext is None:
        return stages, "failed"

    ciphertext_ok = _export_ciphertext_integrity_ok(ciphertext, manifest_result.manifest)
    stages.append(
        _stage(
            "export_ciphertext_hash_valid",
            "passed" if ciphertext_ok else "failed",
            (
                "export ciphertext size and SHA-256 match manifest"
                if ciphertext_ok
                else "export ciphertext size or SHA-256 did not match manifest"
            ),
        )
    )
    if not ciphertext_ok:
        stages.extend(
            _blocked_export_stages("ciphertext integrity check failed", plaintext_hash=True)
        )
        return stages, "failed"

    decrypt_status = _diagnose_export_decryption(
        stages,
        ciphertext,
        manifest_result.manifest,
        manifest_result.salt,
        manifest_result.iv,
        secret_inputs,
        secret_results,
    )
    return stages, decrypt_status


class _ExportManifestResult:
    def __init__(
        self,
        *,
        stages: list[DoctorStage],
        manifest: dict[str, Any] | None = None,
        salt: bytes | None = None,
        iv: bytes | None = None,
    ) -> None:
        self.stages = stages
        self.manifest = manifest
        self.salt = salt
        self.iv = iv


def _load_export_manifest(html: str, dashboard_html_path: Path) -> _ExportManifestResult:
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
    try:
        manifest = _json_object(content, manifest_label)
    except _DashboardDoctorError as exc:
        stages.append(_stage("export_manifest_valid", "failed", exc.detail))
        stages.extend(
            _blocked_export_stages(
                "export manifest was invalid", include_asset=True, plaintext_hash=True
            )
        )
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


def _missing_manifest_stages(detail: str) -> list[DoctorStage]:
    return [
        _stage("export_manifest_found", "failed", detail),
        _stage("export_manifest_valid", "skipped", "export manifest was unavailable"),
        *_blocked_export_stages(
            "export manifest was unavailable", include_asset=True, plaintext_hash=True
        ),
    ]


def _blocked_export_stages(
    detail: str,
    *,
    include_asset: bool = False,
    plaintext_hash: bool = False,
) -> list[DoctorStage]:
    stages = []
    if include_asset:
        stages.append(_stage("export_asset_found", "skipped", detail))
        stages.append(_stage("export_ciphertext_hash_valid", "skipped", detail))
    stages.append(_stage("export_decrypts", "skipped", detail))
    if plaintext_hash:
        stages.append(_stage("export_plaintext_hash_valid", "skipped", detail))
    return stages


def _read_export_ciphertext(
    dashboard_html_path: Path,
    manifest: dict[str, Any],
) -> tuple[bytes | None, list[DoctorStage]]:
    asset = cast(str, manifest["asset"])
    asset_path = dashboard_html_path.parent / asset
    try:
        ciphertext = asset_path.read_bytes()
    except OSError as exc:
        return None, [
            _stage("export_asset_found", "failed", f"export asset was not readable: {exc}"),
            _stage("export_ciphertext_hash_valid", "skipped", "export asset was unavailable"),
            *_blocked_export_stages("export asset was unavailable", plaintext_hash=True),
        ]
    return ciphertext, [
        _stage("export_asset_found", "passed", f"export asset {asset} was readable")
    ]


def _export_ciphertext_integrity_ok(ciphertext: bytes, manifest: dict[str, Any]) -> bool:
    return len(ciphertext) == cast(int, manifest["ciphertext_size"]) and hashlib.sha256(
        ciphertext
    ).hexdigest() == cast(str, manifest["ciphertext_sha256"])


def _diagnose_export_decryption(
    stages: list[DoctorStage],
    ciphertext: bytes,
    manifest: dict[str, Any],
    salt: bytes,
    iv: bytes,
    secret_inputs: list[tuple[str, str]],
    secret_results: list[DoctorSecretResult],
) -> DoctorStageStatus:
    accepted_secrets = _accepted_secret_values(secret_inputs, secret_results)
    if not accepted_secrets:
        stages.extend(
            _blocked_export_stages(
                "no accepted dashboard secret was available", plaintext_hash=True
            )
        )
        return "skipped"

    expected_plaintext_sha256 = cast(str, manifest["plaintext_sha256"])
    failures = False
    for label, secret in accepted_secrets:
        export_key = _derive_key(secret, salt)
        try:
            plaintext = AESGCM(export_key).decrypt(iv, ciphertext, None)
        except InvalidTag:
            failures = True
            stages.append(
                _stage("export_decrypts", "failed", "AES-GCM authentication failed", label)
            )
            continue
        stages.append(_stage("export_decrypts", "passed", "export asset decrypted", label))
        if hashlib.sha256(plaintext).hexdigest() != expected_plaintext_sha256:
            failures = True
            stages.append(
                _stage(
                    "export_plaintext_hash_valid",
                    "failed",
                    "decrypted export plaintext SHA-256 did not match manifest",
                    label,
                )
            )
            continue
        stages.append(
            _stage(
                "export_plaintext_hash_valid",
                "passed",
                "decrypted export plaintext SHA-256 matches manifest",
                label,
            )
        )
        return "passed"
    return "failed" if failures else "skipped"
