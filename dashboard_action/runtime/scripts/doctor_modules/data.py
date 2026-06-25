"""Dashboard data and secret diagnostics for doctor mode."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from doctor_modules.decode import _decrypt_gzip_json_staged
from doctor_modules.schema import (
    _semantic_counts_stage,
    _validate_chunk_staged,
    _validate_summary_staged,
)
from doctor_support import (
    DoctorSecretResult,
    DoctorStage,
    _derive_key,
    _object_dict,
    _stage,
    _stage_passed,
)


@dataclass(frozen=True)
class _DataCoverage:
    """Counts reported by dashboard data diagnostics."""

    chunks_checked: int
    chunk_count: int
    repo_count: int


def _skip_secret_result(label: str, provided: bool, detail: str) -> DoctorSecretResult:
    """Build a skipped per-secret result with the standard early stages."""
    return DoctorSecretResult(
        label=label,
        provided=provided,
        stages=[
            _stage("key_derivation_ready", "skipped", detail, label),
            _stage("summary_authenticates", "skipped", detail, label),
        ],
    )


def _diagnose_encrypted_secret(
    label: str,
    secret: str,
    data: dict[str, Any],
    salt: bytes | None,
    *,
    chunk_limit: int | None,
) -> tuple[DoctorSecretResult, int, int, int]:
    """Diagnose one encrypted dashboard secret against summary and chunk payloads."""
    chunks = _object_dict(data.get("chunks"))
    if salt is None:
        return _failed_key_result(
            label, "salt was unavailable", "key derivation failed", len(chunks)
        )

    try:
        key = _derive_key(secret, salt)
    except Exception as exc:
        return _failed_key_result(
            label, f"key derivation failed: {exc}", "key derivation failed", len(chunks)
        )

    stages = [_stage("key_derivation_ready", "passed", "key derivation inputs are usable", label)]
    summary, summary_stages = _decrypt_gzip_json_staged(
        data.get("summary"),
        key,
        subject=label,
        auth_stage="summary_authenticates",
        decompress_stage="summary_decompresses",
        json_stage="summary_json_valid",
    )
    stages.extend(summary_stages)
    if summary is None:
        return DoctorSecretResult(label=label, provided=True, stages=stages), 0, len(chunks), 0

    repo_chunks, repo_count, summary_schema_stages = _validate_summary_staged(summary)
    stages.extend(summary_schema_stages)
    chunks_checked = _diagnose_encrypted_chunks(stages, chunks, repo_chunks, key, chunk_limit)
    _append_semantic_stage(stages, summary_schema_stages, repo_count, repo_chunks, chunks)
    coverage = _DataCoverage(chunks_checked, len(chunks), repo_count)
    return _secret_result_with_coverage(label, stages, coverage)


def _failed_key_result(
    label: str,
    ready_detail: str,
    auth_detail: str,
    chunk_count: int,
) -> tuple[DoctorSecretResult, int, int, int]:
    """Build a failed encrypted-secret result with zero checked chunks."""
    return (
        DoctorSecretResult(
            label=label,
            provided=True,
            stages=[
                _stage("key_derivation_ready", "failed", ready_detail, label),
                _stage("summary_authenticates", "skipped", auth_detail, label),
            ],
        ),
        0,
        chunk_count,
        0,
    )


def _diagnose_encrypted_chunks(
    stages: list[DoctorStage],
    chunks: dict[str, Any],
    repo_chunks: dict[str, str],
    key: bytes,
    chunk_limit: int | None,
) -> int:
    """Decrypt and validate the encrypted chunks referenced by the summary."""
    chunks_checked = 0
    for repo_name, chunk_id in _limited_repo_chunks(repo_chunks, chunk_limit):
        if _diagnose_encrypted_chunk(stages, chunks, repo_name, chunk_id, key):
            chunks_checked += 1
    return chunks_checked


def _limited_repo_chunks(
    repo_chunks: dict[str, str],
    chunk_limit: int | None,
) -> list[tuple[str, str]]:
    """Return summary repo chunk items, honoring an optional non-negative limit."""
    items = list(repo_chunks.items())
    if chunk_limit is None:
        return items
    return items[: max(0, chunk_limit)]


def _diagnose_encrypted_chunk(
    stages: list[DoctorStage],
    chunks: dict[str, Any],
    repo_name: str,
    chunk_id: str,
    key: bytes,
) -> bool:
    """Append diagnostics for one encrypted chunk and return whether it was checked."""
    token = chunks.get(chunk_id)
    subject = f"{repo_name}:{chunk_id}"
    if not isinstance(token, str):
        stages.append(_missing_encrypted_chunk_stage(repo_name, chunk_id, subject))
        return False

    stages.append(_chunk_payload_present_stage(subject))
    chunk, chunk_decode_stages = _decrypt_gzip_json_staged(
        token,
        key,
        subject=subject,
        auth_stage="chunk_authenticates",
        decompress_stage="chunk_decompresses",
        json_stage="chunk_json_valid",
    )
    stages.extend(chunk_decode_stages)
    if chunk is None:
        return False
    stages.extend(_validate_chunk_staged(repo_name, chunk_id, chunk))
    return True


def _missing_encrypted_chunk_stage(
    repo_name: str,
    chunk_id: str,
    subject: str,
) -> DoctorStage:
    """Build the stage for a missing encrypted chunk referenced by summary."""
    return _stage(
        "chunk_payload_present",
        "failed",
        f"dashboard chunk {chunk_id} for {repo_name} was missing",
        subject,
    )


def _chunk_payload_present_stage(subject: str) -> DoctorStage:
    """Build the shared stage for a present chunk payload."""
    return _stage("chunk_payload_present", "passed", "referenced chunk payload is present", subject)


def _secret_result_with_coverage(
    label: str,
    stages: list[DoctorStage],
    coverage: _DataCoverage,
) -> tuple[DoctorSecretResult, int, int, int]:
    """Return a secret result in the legacy tuple shape expected by callers."""
    return (
        DoctorSecretResult(label=label, provided=True, stages=stages),
        coverage.chunks_checked,
        coverage.chunk_count,
        coverage.repo_count,
    )


def _diagnose_plain_data(data: dict[str, Any]) -> tuple[list[DoctorStage], int, int, int]:
    """Validate plaintext summary and chunk payloads."""
    stages: list[DoctorStage] = []
    summary = data.get("summary")
    repo_chunks, repo_count, summary_stages = _validate_summary_staged(summary)
    stages.extend(summary_stages)
    chunks = _object_dict(data.get("chunks"))
    chunks_checked = 0
    for repo_name, chunk_id in repo_chunks.items():
        if _diagnose_plain_chunk(stages, chunks, repo_name, chunk_id):
            chunks_checked += 1
    _append_semantic_stage(stages, summary_stages, repo_count, repo_chunks, chunks)
    return stages, chunks_checked, len(chunks), repo_count


def _diagnose_plain_chunk(
    stages: list[DoctorStage],
    chunks: dict[str, Any],
    repo_name: str,
    chunk_id: str,
) -> bool:
    """Append diagnostics for one plaintext chunk and return whether it was checked."""
    raw_chunk = chunks.get(chunk_id)
    subject = f"{repo_name}:{chunk_id}"
    if not isinstance(raw_chunk, str):
        stages.append(_missing_plaintext_chunk_stage(subject))
        return False

    stages.append(_chunk_payload_present_stage(subject))
    chunk, chunk_json_stages = _parse_plaintext_chunk(raw_chunk, subject)
    stages.extend(chunk_json_stages)
    if chunk is None:
        return False
    stages.extend(_validate_chunk_staged(repo_name, chunk_id, chunk))
    return True


def _missing_plaintext_chunk_stage(subject: str) -> DoctorStage:
    """Build the stage for a missing plaintext chunk referenced by summary."""
    return _stage("chunk_payload_present", "failed", "plaintext chunk was missing", subject)


def _parse_plaintext_chunk(
    raw_chunk: str,
    subject: str,
) -> tuple[dict[str, Any] | None, list[DoctorStage]]:
    """Parse a plaintext chunk JSON object and return parse stages."""
    try:
        chunk = json.loads(raw_chunk)
    except json.JSONDecodeError as exc:
        return None, [
            _stage(
                "chunk_json_valid",
                "failed",
                f"plaintext chunk was not valid JSON: {exc}",
                subject,
            )
        ]
    if not isinstance(chunk, dict):
        return None, [
            _stage("chunk_json_valid", "failed", "plaintext chunk was not a JSON object", subject)
        ]
    return chunk, [_stage("chunk_json_valid", "passed", "plaintext chunk parsed as JSON", subject)]


def _append_semantic_stage(
    stages: list[DoctorStage],
    summary_stages: list[DoctorStage],
    repo_count: int,
    repo_chunks: dict[str, str],
    chunks: dict[str, Any],
) -> None:
    """Append semantic-counts validation when summary mapping is available."""
    if _stage_passed(summary_stages, "summary_repo_chunk_mapping_valid"):
        stages.append(_semantic_counts_stage(repo_count, repo_chunks, chunks))
    else:
        stages.append(
            _stage("semantic_counts_valid", "skipped", "summary repo_chunks were unavailable")
        )
