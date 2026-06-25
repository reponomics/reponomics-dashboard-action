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
    DashboardDoctorError as _DashboardDoctorError,
    DetectedDashboardMode,
    DoctorDataMode,
    DoctorStage,
    _b64_decode,
    _object_dict,
    _stage,
    _validate_encrypted_blob_token,
)


def _validate_configured_mode(mode: str) -> tuple[DoctorDataMode, DoctorStage]:
    """Validate the configured data mode before downstream mode-specific checks."""
    if mode == "plaintext":
        return "plaintext", _stage(
            "configured_data_mode_recorded", "passed", "configured plaintext mode"
        )
    if mode == "encrypted":
        return "encrypted", _stage(
            "configured_data_mode_recorded", "passed", "configured encrypted mode"
        )
    raise _DashboardDoctorError(
        "configured_data_mode_recorded",
        f"configured data mode {mode!r} is invalid",
    )


def _mode_match_stage(
    configured_mode: DoctorDataMode,
    detected_mode: DetectedDashboardMode,
) -> DoctorStage:
    """Return whether the configured mode agrees with the discovered dashboard payload."""
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
    """Build a pass/fail stage from a boolean contract check."""
    return _stage(name, "passed" if ok else "failed", passed_detail if ok else failed_detail)


def _kdf_contract_valid(kdf: Any) -> bool:
    """Return whether an encrypted envelope KDF matches the supported browser contract."""
    return (
        isinstance(kdf, dict)
        and kdf.get("name") == EXPECTED_KDF_NAME
        and kdf.get("hash") == EXPECTED_KDF_HASH
        and kdf.get("iterations") == EXPECTED_KDF_ITERATIONS
    )


def _salt_stage(data: dict[str, Any]) -> tuple[DoctorStage, bytes | None]:
    """Validate and decode the encrypted envelope salt."""
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
    """Return a stage describing whether an encrypted blob token has the expected shape."""
    try:
        _validate_encrypted_blob_token(token)
    except Exception as exc:
        return _stage(name, "failed", f"summary token was malformed: {exc}")
    return _stage(name, "passed", "summary token shape is valid")


def _chunk_contract_stages(data: dict[str, Any], *, encrypted: bool) -> list[DoctorStage]:
    """Validate the shared chunk object, count, ids, and optional token shapes."""
    chunks_raw = data.get("chunks")
    if not isinstance(chunks_raw, dict):
        return _invalid_chunks_object_stages()

    chunks = _object_dict(chunks_raw)
    chunk_ids = list(chunks)
    return [
        _stage("browser_envelope_chunks_object_valid", "passed", "chunks object is valid"),
        _chunk_count_stage(data, chunk_ids),
        _chunk_ids_stage(chunks, encrypted=encrypted),
    ]


def _invalid_chunks_object_stages() -> list[DoctorStage]:
    """Build the stages emitted when the envelope chunks value is not an object."""
    return [
        _stage("browser_envelope_chunks_object_valid", "failed", "chunks must be a JSON object"),
        _stage("browser_envelope_chunk_count_valid", "skipped", "chunks object was invalid"),
        _stage("browser_envelope_chunk_ids_valid", "skipped", "chunks object was invalid"),
    ]


def _chunk_count_stage(data: dict[str, Any], chunk_ids: list[str]) -> DoctorStage:
    """Return whether the declared chunk count matches the emitted chunk ids."""
    count_ok = data.get("chunk_count") == len(chunk_ids)
    return _stage(
        "browser_envelope_chunk_count_valid",
        "passed" if count_ok else "failed",
        (
            "chunk_count matches emitted chunks"
            if count_ok
            else f"chunk_count {data.get('chunk_count')!r} did not match {len(chunk_ids)} chunks"
        ),
    )


def _chunk_ids_stage(chunks: dict[str, Any], *, encrypted: bool) -> DoctorStage:
    """Return whether chunk ids and encrypted chunk tokens match the contract."""
    invalid_ids = _invalid_chunk_ids(chunks)
    malformed_tokens = _malformed_chunk_tokens(chunks) if encrypted else []
    ids_detail = _chunk_ids_detail(invalid_ids, malformed_tokens)
    return _stage(
        "browser_envelope_chunk_ids_valid",
        "passed" if ids_detail is None else "failed",
        ids_detail or "chunk ids and token shapes are valid",
    )


def _invalid_chunk_ids(chunks: dict[str, Any]) -> list[str]:
    """Return chunk ids that do not match the dashboard chunk-id format."""
    return [chunk_id for chunk_id in chunks if not CHUNK_ID_RE.fullmatch(str(chunk_id))]


def _chunk_ids_detail(invalid_ids: list[str], malformed_tokens: list[str]) -> str | None:
    """Return a compact failure detail for invalid ids or malformed tokens."""
    detail_parts = []
    if invalid_ids:
        detail_parts.append("invalid ids: " + ", ".join(invalid_ids[:5]))
    if malformed_tokens:
        detail_parts.append("malformed tokens: " + ", ".join(malformed_tokens[:5]))
    return "; ".join(detail_parts) if detail_parts else None


def _malformed_chunk_tokens(chunks: dict[str, Any]) -> list[str]:
    """Return chunk ids whose encrypted blob token cannot be decoded."""
    malformed: list[str] = []
    for chunk_id, token in chunks.items():
        try:
            _validate_encrypted_blob_token(token)
        except Exception:
            malformed.append(str(chunk_id))
    return malformed


def _validate_encrypted_contract(data: dict[str, Any]) -> tuple[list[DoctorStage], bytes | None]:
    """Validate encrypted browser payload envelope fields and return decoded salt."""
    salt_stage, salt = _salt_stage(data)
    stages = _encrypted_envelope_field_stages(data) + [
        salt_stage,
        _encrypted_token_stage("browser_envelope_summary_token_valid", data.get("summary")),
    ]
    stages.extend(_chunk_contract_stages(data, encrypted=True))
    return stages, salt


def _validate_plain_contract(data: dict[str, Any]) -> list[DoctorStage]:
    """Validate plaintext browser payload envelope fields."""
    stages = _plain_envelope_field_stages(data)
    stages.extend(_chunk_contract_stages(data, encrypted=False))
    return stages


def _encrypted_envelope_field_stages(data: dict[str, Any]) -> list[DoctorStage]:
    """Return encrypted-envelope stages before salt and token-shape validation."""
    return [
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
    ]


def _plain_envelope_field_stages(data: dict[str, Any]) -> list[DoctorStage]:
    """Return plaintext-envelope stages before shared chunk validation."""
    return [
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
