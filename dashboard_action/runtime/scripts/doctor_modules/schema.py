"""Decoded dashboard summary and chunk schema diagnostics."""

from __future__ import annotations

import gzip
import json
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from doctor_support import (
    DashboardDoctorError as _DashboardDoctorError,
    DoctorStage,
    _object_dict,
    _stage,
    _validate_encrypted_blob_token,
)


def _decrypt_gzip_json_staged(
    token: Any,
    key: bytes,
    *,
    subject: str,
    auth_stage: str,
    decompress_stage: str,
    json_stage: str,
) -> tuple[dict[str, Any] | None, list[DoctorStage]]:
    stages: list[DoctorStage] = []
    try:
        iv, ciphertext = _validate_encrypted_blob_token(token)
        plaintext = AESGCM(key).decrypt(iv, ciphertext, None)
    except InvalidTag:
        stages.extend(
            [
                _stage(auth_stage, "failed", "AES-GCM authentication failed", subject),
                _stage(decompress_stage, "skipped", "authentication failed", subject),
                _stage(json_stage, "skipped", "authentication failed", subject),
            ]
        )
        return None, stages
    except Exception as exc:
        stages.extend(
            [
                _stage(auth_stage, "failed", f"encrypted blob was malformed: {exc}", subject),
                _stage(decompress_stage, "skipped", "encrypted blob was malformed", subject),
                _stage(json_stage, "skipped", "encrypted blob was malformed", subject),
            ]
        )
        return None, stages

    stages.append(_stage(auth_stage, "passed", "AES-GCM authentication passed", subject))
    try:
        decompressed = gzip.decompress(plaintext)
    except OSError as exc:
        stages.extend(
            [
                _stage(
                    decompress_stage, "failed", f"decrypted blob was not valid gzip: {exc}", subject
                ),
                _stage(json_stage, "skipped", "gzip decompression failed", subject),
            ]
        )
        return None, stages

    stages.append(_stage(decompress_stage, "passed", "decrypted plaintext decompressed", subject))
    try:
        value = json.loads(decompressed)
    except json.JSONDecodeError as exc:
        stages.append(
            _stage(json_stage, "failed", f"decrypted blob was not valid JSON: {exc}", subject)
        )
        return None, stages
    if not isinstance(value, dict):
        stages.append(_stage(json_stage, "failed", "decrypted blob was not a JSON object", subject))
        return None, stages
    stages.append(_stage(json_stage, "passed", "decrypted plaintext parsed as JSON", subject))
    return value, stages


def _validate_summary(summary: dict[str, Any]) -> None:
    if not isinstance(summary.get("repos"), list):
        raise _DashboardDoctorError("schema", "dashboard summary repos are missing")
    if not isinstance(summary.get("totals"), dict):
        raise _DashboardDoctorError("schema", "dashboard summary totals are missing")
    if not isinstance(summary.get("repo_chunks"), dict):
        raise _DashboardDoctorError("schema", "dashboard summary repo_chunks are missing")


def _validate_summary_staged(summary: Any) -> tuple[dict[str, str], int, list[DoctorStage]]:
    stages: list[DoctorStage] = []
    repo_chunks: dict[str, str] = {}
    repo_count = 0
    if not isinstance(summary, dict):
        stages.extend(
            [
                _stage("summary_min_schema_valid", "failed", "summary was not a JSON object"),
                _stage("summary_repo_chunk_mapping_valid", "skipped", "summary schema was invalid"),
            ]
        )
        return repo_chunks, repo_count, stages

    missing = [
        field
        for field, expected_type in (("repos", list), ("totals", dict), ("repo_chunks", dict))
        if not isinstance(summary.get(field), expected_type)
    ]
    if missing:
        stages.append(
            _stage(
                "summary_min_schema_valid",
                "failed",
                "dashboard summary missing or invalid fields: " + ", ".join(missing),
            )
        )
        stages.append(
            _stage("summary_repo_chunk_mapping_valid", "skipped", "summary schema was invalid")
        )
        repos = summary.get("repos")
        if isinstance(repos, list):
            repo_count = len(repos)
        return repo_chunks, repo_count, stages

    repo_count = len(summary["repos"])
    stages.append(_stage("summary_min_schema_valid", "passed", "summary has required fields"))

    invalid = [
        f"{repo_name!r}->{chunk_id!r}"
        for repo_name, chunk_id in summary["repo_chunks"].items()
        if not isinstance(repo_name, str) or not isinstance(chunk_id, str)
    ]
    if invalid:
        stages.append(
            _stage(
                "summary_repo_chunk_mapping_valid",
                "failed",
                "repo_chunks contains invalid mappings: " + ", ".join(invalid[:5]),
            )
        )
        return repo_chunks, repo_count, stages

    repo_chunks = dict(summary["repo_chunks"])
    stages.append(
        _stage(
            "summary_repo_chunk_mapping_valid",
            "passed",
            f"summary maps {len(repo_chunks)} repos to chunks",
        )
    )
    return repo_chunks, repo_count, stages


def _validate_chunk(repo_name: str, chunk_id: str, chunk: dict[str, Any]) -> None:
    if chunk.get("repo") != repo_name:
        raise _DashboardDoctorError(
            "schema",
            f"dashboard chunk {chunk_id} did not match repository {repo_name}",
        )
    for field in ("repo_series", "repo_weekday", "repo_referrers", "repo_paths", "growth"):
        if field not in chunk:
            raise _DashboardDoctorError(
                "schema",
                f"dashboard chunk {chunk_id} was missing required field {field}",
            )


def _validate_chunk_staged(repo_name: str, chunk_id: str, chunk: Any) -> list[DoctorStage]:
    subject = f"{repo_name}:{chunk_id}"
    if not isinstance(chunk, dict):
        return [_stage("chunk_min_schema_valid", "failed", "chunk was not a JSON object", subject)]
    required = ("repo_series", "repo_weekday", "repo_referrers", "repo_paths", "growth")
    missing = [field for field in required if field not in chunk]
    growth = _object_dict(chunk.get("growth"))
    per_repo = _object_dict(growth.get("per_repo"))
    series_ok = isinstance(per_repo.get("series"), dict)
    return [
        _stage(
            "chunk_min_schema_valid",
            "passed" if not missing else "failed",
            "chunk has required fields"
            if not missing
            else "chunk missing fields: " + ", ".join(missing),
            subject,
        ),
        _stage(
            "chunk_repo_matches_summary",
            "passed" if chunk.get("repo") == repo_name else "failed",
            (
                "chunk repo matches summary mapping"
                if chunk.get("repo") == repo_name
                else f"chunk repo {chunk.get('repo')!r} did not match {repo_name!r}"
            ),
            subject,
        ),
        _stage(
            "chunk_growth_contract_valid",
            "passed" if series_ok else "failed",
            "chunk growth contains per-repo series"
            if series_ok
            else "chunk growth missing per_repo.series",
            subject,
        ),
    ]


def _semantic_counts_stage(
    repo_count: int,
    repo_chunks: dict[str, str],
    chunks: dict[str, Any],
) -> DoctorStage:
    expected_chunk_ids = set(repo_chunks.values())
    actual_chunk_ids = set(chunks)
    if repo_count != len(repo_chunks):
        return _stage(
            "semantic_counts_valid",
            "failed",
            f"repo count {repo_count} did not match repo_chunks count {len(repo_chunks)}",
        )
    if expected_chunk_ids != actual_chunk_ids:
        missing = sorted(expected_chunk_ids - actual_chunk_ids)
        orphaned = sorted(actual_chunk_ids - expected_chunk_ids)
        detail = []
        if missing:
            detail.append("missing chunks: " + ", ".join(missing[:5]))
        if orphaned:
            detail.append("orphan chunks: " + ", ".join(orphaned[:5]))
        return _stage("semantic_counts_valid", "failed", "; ".join(detail))
    return _stage("semantic_counts_valid", "passed", "repo, mapping, and chunk counts agree")
