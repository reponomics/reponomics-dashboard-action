"""Browser payload and dashboard data contract diagnostics."""

from __future__ import annotations

from typing import Any

from doctor_support import (
    CHUNK_ID_RE,
    EXPECTED_DASHBOARD_DATA_VERSION,
    EXPECTED_KDF_HASH,
    EXPECTED_KDF_ITERATIONS,
    EXPECTED_KDF_NAME,
    EXPECTED_SALT_BYTES,
    DetectedDashboardMode,
    DoctorDataMode,
    DoctorStage,
    _b64_decode,
    _object_dict,
    _stage,
    _validate_encrypted_blob_token,
)


def _validate_configured_mode(mode: str) -> tuple[DoctorDataMode, DoctorStage]:
    if mode == "plaintext":
        return "plaintext", _stage(
            "configured_data_mode_recorded", "passed", "configured plaintext mode"
        )
    if mode == "encrypted":
        return "encrypted", _stage(
            "configured_data_mode_recorded", "passed", "configured encrypted mode"
        )
    return (
        "encrypted",
        _stage(
            "configured_data_mode_recorded",
            "failed",
            f"configured data mode {mode!r} is invalid",
        ),
    )


def _mode_match_stage(
    configured_mode: DoctorDataMode,
    detected_mode: DetectedDashboardMode,
) -> DoctorStage:
    if detected_mode == "unknown":
        return _stage(
            "configured_detected_mode_match",
            "failed",
            "dashboard mode could not be detected",
        )
    if configured_mode != detected_mode:
        return _stage(
            "configured_detected_mode_match",
            "failed",
            f"configured {configured_mode} mode but detected {detected_mode} dashboard payload",
        )
    return _stage(
        "configured_detected_mode_match",
        "passed",
        f"configured and detected modes are both {configured_mode}",
    )


def _value_stage(
    name: str,
    ok: bool,
    passed_detail: str,
    failed_detail: str,
) -> DoctorStage:
    return _stage(name, "passed" if ok else "failed", passed_detail if ok else failed_detail)


def _kdf_contract_valid(kdf: Any) -> bool:
    return (
        isinstance(kdf, dict)
        and kdf.get("name") == EXPECTED_KDF_NAME
        and kdf.get("hash") == EXPECTED_KDF_HASH
        and kdf.get("iterations") == EXPECTED_KDF_ITERATIONS
    )


def _salt_stage(data: dict[str, Any]) -> tuple[DoctorStage, bytes | None]:
    try:
        salt = _b64_decode(data.get("salt"))
        if len(salt) == EXPECTED_SALT_BYTES:
            return _stage("browser_envelope_salt_valid", "passed", "salt length is supported"), salt
        return (
            _stage(
                "browser_envelope_salt_valid",
                "failed",
                f"salt was {len(salt)} bytes, expected {EXPECTED_SALT_BYTES}",
            ),
            None,
        )
    except Exception as exc:
        return _stage("browser_envelope_salt_valid", "failed", f"salt was malformed: {exc}"), None


def _encrypted_token_stage(name: str, token: Any) -> DoctorStage:
    try:
        _validate_encrypted_blob_token(token)
    except Exception as exc:
        return _stage(name, "failed", f"summary token was malformed: {exc}")
    return _stage(name, "passed", "summary token shape is valid")


def _chunk_contract_stages(data: dict[str, Any], *, encrypted: bool) -> list[DoctorStage]:
    chunks_raw = data.get("chunks")
    if not isinstance(chunks_raw, dict):
        return [
            _stage(
                "browser_envelope_chunks_object_valid", "failed", "chunks must be a JSON object"
            ),
            _stage("browser_envelope_chunk_count_valid", "skipped", "chunks object was invalid"),
            _stage("browser_envelope_chunk_ids_valid", "skipped", "chunks object was invalid"),
        ]

    chunks = _object_dict(chunks_raw)
    chunk_ids = list(chunks)
    count_ok = data.get("chunk_count") == len(chunk_ids)
    invalid_ids = [chunk_id for chunk_id in chunk_ids if not CHUNK_ID_RE.fullmatch(str(chunk_id))]
    malformed_tokens = _malformed_chunk_tokens(chunks) if encrypted else []
    ids_detail = _chunk_ids_detail(invalid_ids, malformed_tokens)
    return [
        _stage("browser_envelope_chunks_object_valid", "passed", "chunks object is valid"),
        _stage(
            "browser_envelope_chunk_count_valid",
            "passed" if count_ok else "failed",
            (
                "chunk_count matches emitted chunks"
                if count_ok
                else f"chunk_count {data.get('chunk_count')!r} did not match {len(chunk_ids)} chunks"
            ),
        ),
        _stage(
            "browser_envelope_chunk_ids_valid",
            "passed" if ids_detail is None else "failed",
            ids_detail or "chunk ids and token shapes are valid",
        ),
    ]


def _chunk_ids_detail(invalid_ids: list[str], malformed_tokens: list[str]) -> str | None:
    detail_parts = []
    if invalid_ids:
        detail_parts.append("invalid ids: " + ", ".join(invalid_ids[:5]))
    if malformed_tokens:
        detail_parts.append("malformed tokens: " + ", ".join(malformed_tokens[:5]))
    return "; ".join(detail_parts) if detail_parts else None


def _malformed_chunk_tokens(chunks: dict[str, Any]) -> list[str]:
    malformed: list[str] = []
    for chunk_id, token in chunks.items():
        try:
            _validate_encrypted_blob_token(token)
        except Exception:
            malformed.append(str(chunk_id))
    return malformed


def _validate_encrypted_contract(data: dict[str, Any]) -> tuple[list[DoctorStage], bytes | None]:
    salt_stage, salt = _salt_stage(data)
    stages = [
        _value_stage(
            "browser_envelope_version_valid",
            data.get("version") == EXPECTED_DASHBOARD_DATA_VERSION,
            "dashboard data version is supported",
            "dashboard data version is unsupported",
        ),
        _value_stage(
            "browser_envelope_cipher_valid",
            data.get("cipher") == "AES-GCM",
            "cipher is supported",
            "encrypted dashboard cipher is unsupported",
        ),
        _value_stage(
            "browser_envelope_encoding_valid",
            data.get("encoding") == "gzip+json",
            "encoding is supported",
            "encrypted dashboard encoding is unsupported",
        ),
        _value_stage(
            "browser_envelope_kdf_valid",
            _kdf_contract_valid(data.get("kdf")),
            "KDF contract is supported",
            "encrypted dashboard KDF is unsupported",
        ),
        salt_stage,
        _encrypted_token_stage("browser_envelope_summary_token_valid", data.get("summary")),
    ]
    stages.extend(_chunk_contract_stages(data, encrypted=True))
    return stages, salt


def _validate_plain_contract(data: dict[str, Any]) -> list[DoctorStage]:
    stages = [
        _value_stage(
            "browser_envelope_version_valid",
            data.get("version") == EXPECTED_DASHBOARD_DATA_VERSION,
            "dashboard data version is supported",
            "dashboard data version is unsupported",
        ),
        _value_stage(
            "browser_envelope_encoding_valid",
            data.get("encoding") == "json",
            "plaintext encoding is supported",
            "plaintext encoding is unsupported",
        ),
    ]
    stages.extend(_chunk_contract_stages(data, encrypted=False))
    return stages
