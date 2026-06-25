"""Export ciphertext asset integrity and decryption diagnostics."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from doctor_support import (
    DoctorSecretResult,
    DoctorStage,
    DoctorStageStatus,
    _accepted_secret_values,
    _derive_key,
    _stage,
)


def _blocked_export_stages(
    detail: str,
    *,
    include_asset: bool = False,
    plaintext_hash: bool = False,
) -> list[DoctorStage]:
    """Return skipped downstream export stages after an earlier blocker."""
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
    """Read the export ciphertext asset declared by the manifest."""
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


def _record_export_ciphertext_integrity(
    stages: list[DoctorStage],
    ciphertext: bytes,
    manifest: dict[str, Any],
) -> bool:
    """Append ciphertext integrity diagnostics and return whether decryption can proceed."""
    ciphertext_ok = _export_ciphertext_integrity_ok(ciphertext, manifest)
    stages.append(_export_ciphertext_integrity_stage(ciphertext_ok))
    if not ciphertext_ok:
        stages.extend(
            _blocked_export_stages("ciphertext integrity check failed", plaintext_hash=True)
        )
    return ciphertext_ok


def _export_ciphertext_integrity_ok(ciphertext: bytes, manifest: dict[str, Any]) -> bool:
    """Return whether export ciphertext size and digest match the manifest."""
    return len(ciphertext) == cast(int, manifest["ciphertext_size"]) and hashlib.sha256(
        ciphertext
    ).hexdigest() == cast(str, manifest["ciphertext_sha256"])


def _export_ciphertext_integrity_stage(ciphertext_ok: bool) -> DoctorStage:
    """Build the export ciphertext size/hash stage."""
    return _stage(
        "export_ciphertext_hash_valid",
        "passed" if ciphertext_ok else "failed",
        (
            "export ciphertext size and SHA-256 match manifest"
            if ciphertext_ok
            else "export ciphertext size or SHA-256 did not match manifest"
        ),
    )


def _diagnose_export_decryption(
    stages: list[DoctorStage],
    ciphertext: bytes,
    manifest: dict[str, Any],
    salt: bytes,
    iv: bytes,
    secret_inputs: list[tuple[str, str]],
    secret_results: list[DoctorSecretResult],
) -> DoctorStageStatus:
    """Try accepted dashboard secrets until the export decrypts and hashes correctly."""
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
        plaintext = _decrypt_export_with_secret(stages, ciphertext, salt, iv, label, secret)
        if plaintext is None:
            failures = True
            continue
        if not _record_export_plaintext_hash(stages, plaintext, expected_plaintext_sha256, label):
            failures = True
            continue
        return "passed"
    return "failed" if failures else "skipped"


def _decrypt_export_with_secret(
    stages: list[DoctorStage],
    ciphertext: bytes,
    salt: bytes,
    iv: bytes,
    label: str,
    secret: str,
) -> bytes | None:
    """Decrypt export ciphertext with one accepted dashboard secret."""
    export_key = _derive_key(secret, salt)
    try:
        plaintext = AESGCM(export_key).decrypt(iv, ciphertext, None)
    except InvalidTag:
        stages.append(_stage("export_decrypts", "failed", "AES-GCM authentication failed", label))
        return None
    stages.append(_stage("export_decrypts", "passed", "export asset decrypted", label))
    return plaintext


def _record_export_plaintext_hash(
    stages: list[DoctorStage],
    plaintext: bytes,
    expected_plaintext_sha256: str,
    label: str,
) -> bool:
    """Append plaintext digest diagnostics and return whether the export is valid."""
    plaintext_ok = hashlib.sha256(plaintext).hexdigest() == expected_plaintext_sha256
    stages.append(
        _stage(
            "export_plaintext_hash_valid",
            "passed" if plaintext_ok else "failed",
            (
                "decrypted export plaintext SHA-256 matches manifest"
                if plaintext_ok
                else "decrypted export plaintext SHA-256 did not match manifest"
            ),
            label,
        )
    )
    return plaintext_ok
