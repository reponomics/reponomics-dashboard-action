"""Staged encrypted gzip+JSON decoding for doctor diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
import gzip
import json
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from doctor_support import DoctorStage, _stage, _validate_encrypted_blob_token


@dataclass(frozen=True)
class _DecodeStages:
    """Stage names used while decoding one encrypted dashboard JSON blob."""

    auth: str
    decompress: str
    json: str


def _decrypt_gzip_json_staged(
    token: Any,
    key: bytes,
    *,
    subject: str,
    auth_stage: str,
    decompress_stage: str,
    json_stage: str,
) -> tuple[dict[str, Any] | None, list[DoctorStage]]:
    """Decrypt, decompress, and parse one encrypted gzip+JSON object."""
    stage_names = _DecodeStages(auth=auth_stage, decompress=decompress_stage, json=json_stage)
    stages: list[DoctorStage] = []
    plaintext, auth_stages = _decrypt_blob_staged(token, key, subject, stage_names)
    stages.extend(auth_stages)
    if plaintext is None:
        return None, stages

    decompressed, decompress_stages = _decompress_blob_staged(plaintext, subject, stage_names)
    stages.extend(decompress_stages)
    if decompressed is None:
        return None, stages

    value, json_stages = _parse_json_object_staged(decompressed, subject, stage_names)
    stages.extend(json_stages)
    return value, stages


def _decrypt_blob_staged(
    token: Any,
    key: bytes,
    subject: str,
    stage_names: _DecodeStages,
) -> tuple[bytes | None, list[DoctorStage]]:
    """Decrypt a token and return authentication stages."""
    try:
        iv, ciphertext = _validate_encrypted_blob_token(token)
        plaintext = AESGCM(key).decrypt(iv, ciphertext, None)
    except InvalidTag:
        return None, [
            _stage(stage_names.auth, "failed", "AES-GCM authentication failed", subject),
            _stage(stage_names.decompress, "skipped", "authentication failed", subject),
            _stage(stage_names.json, "skipped", "authentication failed", subject),
        ]
    except Exception as exc:
        return None, [
            _stage(stage_names.auth, "failed", f"encrypted blob was malformed: {exc}", subject),
            _stage(stage_names.decompress, "skipped", "encrypted blob was malformed", subject),
            _stage(stage_names.json, "skipped", "encrypted blob was malformed", subject),
        ]
    return plaintext, [_stage(stage_names.auth, "passed", "AES-GCM authentication passed", subject)]


def _decompress_blob_staged(
    plaintext: bytes,
    subject: str,
    stage_names: _DecodeStages,
) -> tuple[bytes | None, list[DoctorStage]]:
    """Decompress decrypted gzip bytes and return decompression stages."""
    try:
        decompressed = gzip.decompress(plaintext)
    except OSError as exc:
        return None, [
            _stage(
                stage_names.decompress,
                "failed",
                f"decrypted blob was not valid gzip: {exc}",
                subject,
            ),
            _stage(stage_names.json, "skipped", "gzip decompression failed", subject),
        ]
    return decompressed, [
        _stage(stage_names.decompress, "passed", "decrypted plaintext decompressed", subject)
    ]


def _parse_json_object_staged(
    decompressed: bytes,
    subject: str,
    stage_names: _DecodeStages,
) -> tuple[dict[str, Any] | None, list[DoctorStage]]:
    """Parse decompressed bytes into a JSON object and return parse stages."""
    try:
        value = json.loads(decompressed)
    except json.JSONDecodeError as exc:
        return None, [
            _stage(stage_names.json, "failed", f"decrypted blob was not valid JSON: {exc}", subject)
        ]
    if not isinstance(value, dict):
        return None, [
            _stage(stage_names.json, "failed", "decrypted blob was not a JSON object", subject)
        ]
    return value, [
        _stage(stage_names.json, "passed", "decrypted plaintext parsed as JSON", subject)
    ]
