"""Dashboard data and secret diagnostics for doctor mode."""

from __future__ import annotations

import json
from typing import Any

from doctor_modules.schema import (
    _decrypt_gzip_json_staged,
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


def _skip_secret_result(label: str, provided: bool, detail: str) -> DoctorSecretResult:
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
    return (
        DoctorSecretResult(label=label, provided=True, stages=stages),
        chunks_checked,
        len(chunks),
        repo_count,
    )


def _failed_key_result(
    label: str,
    ready_detail: str,
    auth_detail: str,
    chunk_count: int,
) -> tuple[DoctorSecretResult, int, int, int]:
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
    chunks_checked = 0
    items = list(repo_chunks.items())
    if chunk_limit is not None:
        items = items[: max(0, chunk_limit)]
    for repo_name, chunk_id in items:
        token = chunks.get(chunk_id)
        subject = f"{repo_name}:{chunk_id}"
        if not isinstance(token, str):
            stages.append(
                _stage(
                    "chunk_payload_present",
                    "failed",
                    f"dashboard chunk {chunk_id} for {repo_name} was missing",
                    subject,
                )
            )
            continue
        stages.append(
            _stage(
                "chunk_payload_present", "passed", "referenced chunk payload is present", subject
            )
        )
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
            continue
        stages.extend(_validate_chunk_staged(repo_name, chunk_id, chunk))
        chunks_checked += 1
    return chunks_checked


def _diagnose_plain_data(data: dict[str, Any]) -> tuple[list[DoctorStage], int, int, int]:
    stages: list[DoctorStage] = []
    summary = data.get("summary")
    repo_chunks, repo_count, summary_stages = _validate_summary_staged(summary)
    stages.extend(summary_stages)
    chunks = _object_dict(data.get("chunks"))
    chunks_checked = 0
    for repo_name, chunk_id in repo_chunks.items():
        raw_chunk = chunks.get(chunk_id)
        subject = f"{repo_name}:{chunk_id}"
        if not isinstance(raw_chunk, str):
            stages.append(
                _stage("chunk_payload_present", "failed", "plaintext chunk was missing", subject)
            )
            continue
        stages.append(
            _stage(
                "chunk_payload_present", "passed", "referenced chunk payload is present", subject
            )
        )
        try:
            chunk = json.loads(raw_chunk)
        except json.JSONDecodeError as exc:
            stages.append(
                _stage(
                    "chunk_json_valid",
                    "failed",
                    f"plaintext chunk was not valid JSON: {exc}",
                    subject,
                )
            )
            continue
        if not isinstance(chunk, dict):
            stages.append(
                _stage(
                    "chunk_json_valid", "failed", "plaintext chunk was not a JSON object", subject
                )
            )
            continue
        stages.append(
            _stage("chunk_json_valid", "passed", "plaintext chunk parsed as JSON", subject)
        )
        stages.extend(_validate_chunk_staged(repo_name, chunk_id, chunk))
        chunks_checked += 1
    _append_semantic_stage(stages, summary_stages, repo_count, repo_chunks, chunks)
    return stages, chunks_checked, len(chunks), repo_count


def _append_semantic_stage(
    stages: list[DoctorStage],
    summary_stages: list[DoctorStage],
    repo_count: int,
    repo_chunks: dict[str, str],
    chunks: dict[str, Any],
) -> None:
    if _stage_passed(summary_stages, "summary_repo_chunk_mapping_valid"):
        stages.append(_semantic_counts_stage(repo_count, repo_chunks, chunks))
    else:
        stages.append(
            _stage("semantic_counts_valid", "skipped", "summary repo_chunks were unavailable")
        )
