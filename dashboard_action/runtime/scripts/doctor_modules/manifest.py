"""Encrypted export manifest contract diagnostics."""

from __future__ import annotations

from typing import Any

from doctor_support import (
    EXPECTED_EXPORT_MANIFEST_VERSION,
    EXPECTED_IV_BYTES,
    EXPECTED_KDF_HASH,
    EXPECTED_KDF_ITERATIONS,
    EXPECTED_KDF_NAME,
    EXPECTED_SALT_BYTES,
    EXPORT_ASSET_RE,
    SHA256_HEX_RE,
    DoctorStage,
    _b64_decode,
    _stage,
)


def _validate_export_manifest_contract(
    manifest: dict[str, Any],
) -> tuple[list[DoctorStage], bytes | None, bytes | None]:
    """Validate export manifest fields and decode reusable crypto parameters."""
    errors = _export_manifest_contract_errors(manifest)
    salt, salt_error = _decode_manifest_bytes(manifest.get("salt"), "salt", EXPECTED_SALT_BYTES)
    iv, iv_error = _decode_manifest_bytes(manifest.get("iv"), "iv", EXPECTED_IV_BYTES)
    errors.extend(error for error in (salt_error, iv_error) if error)
    return (
        [
            _stage(
                "export_manifest_valid",
                "failed" if errors else "passed",
                "; ".join(errors) if errors else "encrypted export manifest contract is valid",
            )
        ],
        salt,
        iv,
    )


def _export_manifest_contract_errors(manifest: dict[str, Any]) -> list[str]:
    """Return human-readable export manifest contract violations."""
    errors: list[str] = []
    if manifest.get("version") != EXPECTED_EXPORT_MANIFEST_VERSION:
        errors.append("unsupported version")
    if manifest.get("cipher") != "AES-GCM":
        errors.append("unsupported cipher")
    if not _manifest_kdf_valid(manifest.get("kdf")):
        errors.append("unsupported KDF")
    if not _asset_path_valid(manifest.get("asset")):
        errors.append("invalid asset path")
    if not isinstance(manifest.get("filename"), str) or not manifest.get("filename"):
        errors.append("missing filename")
    if not _positive_int(manifest.get("ciphertext_size")):
        errors.append("invalid ciphertext size")
    if not _sha256_value_valid(manifest.get("ciphertext_sha256")):
        errors.append("invalid ciphertext sha256")
    if not _sha256_value_valid(manifest.get("plaintext_sha256")):
        errors.append("invalid plaintext sha256")
    return errors


def _manifest_kdf_valid(kdf: Any) -> bool:
    """Return whether the export manifest KDF matches the supported contract."""
    return (
        isinstance(kdf, dict)
        and kdf.get("name") == EXPECTED_KDF_NAME
        and kdf.get("hash") == EXPECTED_KDF_HASH
        and kdf.get("iterations") == EXPECTED_KDF_ITERATIONS
    )


def _asset_path_valid(asset: Any) -> bool:
    """Return whether the export asset path uses the expected generated filename."""
    return isinstance(asset, str) and bool(EXPORT_ASSET_RE.fullmatch(asset))


def _positive_int(value: Any) -> bool:
    """Return whether a manifest value is a positive integer."""
    return isinstance(value, int) and value > 0


def _sha256_value_valid(value: Any) -> bool:
    """Return whether a manifest value is a lowercase SHA-256 hex digest."""
    return isinstance(value, str) and bool(SHA256_HEX_RE.fullmatch(value))


def _decode_manifest_bytes(
    value: Any, name: str, expected_len: int
) -> tuple[bytes | None, str | None]:
    """Decode a base64 manifest byte field and validate its length."""
    try:
        decoded = _b64_decode(value)
    except Exception as exc:
        return None, f"{name} was malformed: {exc}"
    if len(decoded) != expected_len:
        return None, f"{name} was {len(decoded)} bytes"
    return decoded, None
