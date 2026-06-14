"""Offline diagnostics for generated Reponomics dashboard artifacts."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
from typing import Any, cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from doctor_retained import (
    _diagnose_retained_artifact,
)
from doctor_support import (
    CHUNK_ID_RE,
    ENCRYPTED_DASHBOARD_SCRIPT_ID,
    EXPECTED_DASHBOARD_DATA_VERSION,
    EXPECTED_EXPORT_MANIFEST_VERSION,
    EXPECTED_IV_BYTES,
    EXPECTED_KDF_HASH,
    EXPECTED_KDF_ITERATIONS,
    EXPECTED_KDF_NAME,
    EXPECTED_SALT_BYTES,
    EXPORT_ASSET_RE,
    EXPORT_MANIFEST_SCRIPT_ID,
    PLAINTEXT_DASHBOARD_SCRIPT_ID,
    SHA256_HEX_RE,
    DashboardDoctorError as _DashboardDoctorError,
    DashboardDoctorResult,
    DashboardKeyCheckResult,
    DetectedDashboardMode,
    DoctorArtifactMode,
    DoctorSecretResult,
    DoctorStage,
    DoctorStageStatus,
    _accepted_secret_values,
    _all_required_stage_statuses_passed,
    _any_failed,
    _b64_decode,
    _derive_key,
    _first_status,
    _json_object,
    _object_dict,
    _optional_script_content,
    _stage,
    _stage_passed,
    _status_from_stages,
    _validate_encrypted_blob_token,
)


def _parse_dashboard_payload(
    html: str,
) -> tuple[DetectedDashboardMode, dict[str, Any] | None, list[DoctorStage]]:
    stages: list[DoctorStage] = []
    encrypted_content = _optional_script_content(html, ENCRYPTED_DASHBOARD_SCRIPT_ID)
    plaintext_script_content = _optional_script_content(html, PLAINTEXT_DASHBOARD_SCRIPT_ID)

    if encrypted_content:
        stages.append(
            _stage(
                "detected_dashboard_mode_recorded",
                "passed",
                "encrypted dashboard payload marker was found",
            )
        )
        stages.append(
            _stage(
                "dashboard_script_found",
                "passed",
                f"script payload {ENCRYPTED_DASHBOARD_SCRIPT_ID!r} was found",
            )
        )
        try:
            data = _json_object(encrypted_content, ENCRYPTED_DASHBOARD_SCRIPT_ID)
        except _DashboardDoctorError as exc:
            stages.append(_stage("dashboard_script_json_valid", "failed", exc.detail))
            return "encrypted", None, stages
        stages.append(_stage("dashboard_script_json_valid", "passed", "encrypted payload is JSON"))
        return "encrypted", data, stages

    if plaintext_script_content:
        stages.append(
            _stage(
                "detected_dashboard_mode_recorded",
                "passed",
                "plaintext dashboard payload marker was found",
            )
        )
        stages.append(
            _stage(
                "dashboard_script_found",
                "passed",
                f"script payload {PLAINTEXT_DASHBOARD_SCRIPT_ID!r} was found",
            )
        )
        try:
            data = _json_object(plaintext_script_content, PLAINTEXT_DASHBOARD_SCRIPT_ID)
        except _DashboardDoctorError as exc:
            stages.append(_stage("dashboard_script_json_valid", "failed", exc.detail))
            return "plaintext", None, stages
        stages.append(_stage("dashboard_script_json_valid", "passed", "plaintext payload is JSON"))
        return "plaintext", data, stages

    stages.extend(
        [
            _stage(
                "detected_dashboard_mode_recorded",
                "failed",
                "no encrypted or plaintext dashboard payload marker was found",
            ),
            _stage("dashboard_script_found", "failed", "dashboard payload was not found"),
        ]
    )
    return "unknown", None, stages


def _validate_configured_mode(mode: str) -> tuple[DoctorArtifactMode, DoctorStage]:
    if mode == "plaintext":
        return "plaintext", _stage("configured_artifact_mode_recorded", "passed", "configured plaintext mode")
    if mode == "encrypted":
        return (
            "encrypted",
            _stage("configured_artifact_mode_recorded", "passed", "configured encrypted mode"),
        )
    return (
        "encrypted",
        _stage(
            "configured_artifact_mode_recorded",
            "failed",
            f"configured artifact mode {mode!r} is invalid",
        ),
    )


def _mode_match_stage(
    configured_mode: DoctorArtifactMode,
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


def _validate_encrypted_contract(data: dict[str, Any]) -> tuple[list[DoctorStage], bytes | None]:
    stages: list[DoctorStage] = []
    salt: bytes | None = None

    stages.append(
        _stage(
            "browser_envelope_version_valid",
            "passed" if data.get("version") == EXPECTED_DASHBOARD_DATA_VERSION else "failed",
            (
                "dashboard data version is supported"
                if data.get("version") == EXPECTED_DASHBOARD_DATA_VERSION
                else "dashboard data version is unsupported"
            ),
        )
    )
    stages.append(
        _stage(
            "browser_envelope_cipher_valid",
            "passed" if data.get("cipher") == "AES-GCM" else "failed",
            (
                "cipher is supported"
                if data.get("cipher") == "AES-GCM"
                else "encrypted dashboard cipher is unsupported"
            ),
        )
    )
    stages.append(
        _stage(
            "browser_envelope_encoding_valid",
            "passed" if data.get("encoding") == "gzip+json" else "failed",
            (
                "encoding is supported"
                if data.get("encoding") == "gzip+json"
                else "encrypted dashboard encoding is unsupported"
            ),
        )
    )

    kdf = data.get("kdf")
    kdf_ok = (
        isinstance(kdf, dict)
        and kdf.get("name") == EXPECTED_KDF_NAME
        and kdf.get("hash") == EXPECTED_KDF_HASH
        and kdf.get("iterations") == EXPECTED_KDF_ITERATIONS
    )
    stages.append(
        _stage(
            "browser_envelope_kdf_valid",
            "passed" if kdf_ok else "failed",
            "KDF contract is supported" if kdf_ok else "encrypted dashboard KDF is unsupported",
        )
    )

    try:
        salt = _b64_decode(data.get("salt"))
        salt_ok = len(salt) == EXPECTED_SALT_BYTES
        detail = (
            "salt length is supported"
            if salt_ok
            else f"salt was {len(salt)} bytes, expected {EXPECTED_SALT_BYTES}"
        )
    except Exception as exc:
        salt_ok = False
        detail = f"salt was malformed: {exc}"
    stages.append(_stage("browser_envelope_salt_valid", "passed" if salt_ok else "failed", detail))

    try:
        _validate_encrypted_blob_token(data.get("summary"))
        summary_token_ok = True
        detail = "summary token shape is valid"
    except Exception as exc:
        summary_token_ok = False
        detail = f"summary token was malformed: {exc}"
    stages.append(
        _stage(
            "browser_envelope_summary_token_valid",
            "passed" if summary_token_ok else "failed",
            detail,
        )
    )

    chunks_raw = data.get("chunks")
    chunks_ok = isinstance(chunks_raw, dict)
    stages.append(
        _stage(
            "browser_envelope_chunks_object_valid",
            "passed" if chunks_ok else "failed",
            "chunks object is valid" if chunks_ok else "chunks must be a JSON object",
        )
    )
    if chunks_ok:
        chunks = _object_dict(chunks_raw)
        chunk_ids = list(chunks)
        count_ok = data.get("chunk_count") == len(chunk_ids)
        stages.append(
            _stage(
                "browser_envelope_chunk_count_valid",
                "passed" if count_ok else "failed",
                (
                    "chunk_count matches emitted chunks"
                    if count_ok
                    else f"chunk_count {data.get('chunk_count')!r} did not match {len(chunk_ids)} chunks"
                ),
            )
        )
        invalid_ids = [chunk_id for chunk_id in chunk_ids if not CHUNK_ID_RE.fullmatch(str(chunk_id))]
        malformed_tokens: list[str] = []
        for chunk_id, token in chunks.items():
            try:
                _validate_encrypted_blob_token(token)
            except Exception:
                malformed_tokens.append(str(chunk_id))
        chunks_valid = not invalid_ids and not malformed_tokens
        detail_parts = []
        if invalid_ids:
            detail_parts.append("invalid ids: " + ", ".join(invalid_ids[:5]))
        if malformed_tokens:
            detail_parts.append("malformed tokens: " + ", ".join(malformed_tokens[:5]))
        stages.append(
            _stage(
                "browser_envelope_chunk_ids_valid",
                "passed" if chunks_valid else "failed",
                "; ".join(detail_parts) if detail_parts else "chunk ids and token shapes are valid",
            )
        )
    else:
        stages.extend(
            [
                _stage("browser_envelope_chunk_count_valid", "skipped", "chunks object was invalid"),
                _stage("browser_envelope_chunk_ids_valid", "skipped", "chunks object was invalid"),
            ]
        )

    return stages, salt if salt_ok else None


def _validate_plain_contract(data: dict[str, Any]) -> list[DoctorStage]:
    stages: list[DoctorStage] = []
    stages.append(
        _stage(
            "browser_envelope_version_valid",
            "passed" if data.get("version") == EXPECTED_DASHBOARD_DATA_VERSION else "failed",
            (
                "dashboard data version is supported"
                if data.get("version") == EXPECTED_DASHBOARD_DATA_VERSION
                else "dashboard data version is unsupported"
            ),
        )
    )
    stages.append(
        _stage(
            "browser_envelope_encoding_valid",
            "passed" if data.get("encoding") == "json" else "failed",
            "plaintext encoding is supported" if data.get("encoding") == "json" else "plaintext encoding is unsupported",
        )
    )
    chunks_raw = data.get("chunks")
    chunks_ok = isinstance(chunks_raw, dict)
    stages.append(
        _stage(
            "browser_envelope_chunks_object_valid",
            "passed" if chunks_ok else "failed",
            "chunks object is valid" if chunks_ok else "chunks must be a JSON object",
        )
    )
    if chunks_ok:
        chunks = _object_dict(chunks_raw)
        chunk_ids = list(chunks)
        count_ok = data.get("chunk_count") == len(chunk_ids)
        stages.append(
            _stage(
                "browser_envelope_chunk_count_valid",
                "passed" if count_ok else "failed",
                (
                    "chunk_count matches emitted chunks"
                    if count_ok
                    else f"chunk_count {data.get('chunk_count')!r} did not match {len(chunk_ids)} chunks"
                ),
            )
        )
        invalid_ids = [chunk_id for chunk_id in chunk_ids if not CHUNK_ID_RE.fullmatch(str(chunk_id))]
        stages.append(
            _stage(
                "browser_envelope_chunk_ids_valid",
                "passed" if not invalid_ids else "failed",
                (
                    "chunk ids are valid"
                    if not invalid_ids
                    else "invalid ids: " + ", ".join(invalid_ids[:5])
                ),
            )
        )
    else:
        stages.extend(
            [
                _stage("browser_envelope_chunk_count_valid", "skipped", "chunks object was invalid"),
                _stage("browser_envelope_chunk_ids_valid", "skipped", "chunks object was invalid"),
            ]
        )
    return stages


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
                _stage(decompress_stage, "failed", f"decrypted blob was not valid gzip: {exc}", subject),
                _stage(json_stage, "skipped", "gzip decompression failed", subject),
            ]
        )
        return None, stages

    stages.append(_stage(decompress_stage, "passed", "decrypted plaintext decompressed", subject))
    try:
        value = json.loads(decompressed)
    except json.JSONDecodeError as exc:
        stages.append(_stage(json_stage, "failed", f"decrypted blob was not valid JSON: {exc}", subject))
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
    stages: list[DoctorStage] = []
    subject = f"{repo_name}:{chunk_id}"
    if not isinstance(chunk, dict):
        return [_stage("chunk_min_schema_valid", "failed", "chunk was not a JSON object", subject)]
    required = ("repo_series", "repo_weekday", "repo_referrers", "repo_paths", "growth")
    missing = [field for field in required if field not in chunk]
    stages.append(
        _stage(
            "chunk_min_schema_valid",
            "passed" if not missing else "failed",
            "chunk has required fields" if not missing else "chunk missing fields: " + ", ".join(missing),
            subject,
        )
    )
    stages.append(
        _stage(
            "chunk_repo_matches_summary",
            "passed" if chunk.get("repo") == repo_name else "failed",
            (
                "chunk repo matches summary mapping"
                if chunk.get("repo") == repo_name
                else f"chunk repo {chunk.get('repo')!r} did not match {repo_name!r}"
            ),
            subject,
        )
    )
    growth = _object_dict(chunk.get("growth"))
    per_repo = _object_dict(growth.get("per_repo"))
    series_ok = isinstance(per_repo.get("series"), dict)
    stages.append(
        _stage(
            "chunk_growth_contract_valid",
            "passed" if series_ok else "failed",
            (
                "chunk growth contains per-repo series"
                if series_ok
                else "chunk growth missing per_repo.series"
            ),
            subject,
        )
    )
    return stages


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


def _validate_export_manifest_contract(manifest: dict[str, Any]) -> tuple[list[DoctorStage], bytes | None, bytes | None]:
    stages: list[DoctorStage] = []
    errors: list[str] = []
    salt: bytes | None = None
    iv: bytes | None = None

    if manifest.get("version") != EXPECTED_EXPORT_MANIFEST_VERSION:
        errors.append("unsupported version")
    if manifest.get("cipher") != "AES-GCM":
        errors.append("unsupported cipher")
    kdf = manifest.get("kdf")
    if not (
        isinstance(kdf, dict)
        and kdf.get("name") == EXPECTED_KDF_NAME
        and kdf.get("hash") == EXPECTED_KDF_HASH
        and kdf.get("iterations") == EXPECTED_KDF_ITERATIONS
    ):
        errors.append("unsupported KDF")
    asset = manifest.get("asset")
    if not isinstance(asset, str) or not EXPORT_ASSET_RE.fullmatch(asset):
        errors.append("invalid asset path")
    filename = manifest.get("filename")
    if not isinstance(filename, str) or not filename:
        errors.append("missing filename")
    ciphertext_size = manifest.get("ciphertext_size")
    if not isinstance(ciphertext_size, int) or ciphertext_size <= 0:
        errors.append("invalid ciphertext size")
    ciphertext_sha256 = manifest.get("ciphertext_sha256")
    if not isinstance(ciphertext_sha256, str) or not SHA256_HEX_RE.fullmatch(ciphertext_sha256):
        errors.append("invalid ciphertext sha256")
    plaintext_sha256 = manifest.get("plaintext_sha256")
    if not isinstance(plaintext_sha256, str) or not SHA256_HEX_RE.fullmatch(plaintext_sha256):
        errors.append("invalid plaintext sha256")

    try:
        salt = _b64_decode(manifest.get("salt"))
        if len(salt) != EXPECTED_SALT_BYTES:
            errors.append(f"salt was {len(salt)} bytes")
            salt = None
    except Exception as exc:
        errors.append(f"salt was malformed: {exc}")
    try:
        iv = _b64_decode(manifest.get("iv"))
        if len(iv) != EXPECTED_IV_BYTES:
            errors.append(f"iv was {len(iv)} bytes")
            iv = None
    except Exception as exc:
        errors.append(f"iv was malformed: {exc}")

    stages.append(
        _stage(
            "export_manifest_valid",
            "failed" if errors else "passed",
            "; ".join(errors) if errors else "encrypted export manifest contract is valid",
        )
    )
    return stages, salt, iv


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

    stages: list[DoctorStage] = []
    content = _optional_script_content(html, EXPORT_MANIFEST_SCRIPT_ID)
    if not content:
        stages.extend(
            [
                _stage("export_manifest_found", "failed", "export manifest script was not found"),
                _stage("export_manifest_valid", "skipped", "export manifest was unavailable"),
                _stage("export_asset_found", "skipped", "export manifest was unavailable"),
                _stage("export_ciphertext_hash_valid", "skipped", "export manifest was unavailable"),
                _stage("export_decrypts", "skipped", "export manifest was unavailable"),
                _stage("export_plaintext_hash_valid", "skipped", "export manifest was unavailable"),
            ]
        )
        return stages, "failed"

    stages.append(_stage("export_manifest_found", "passed", "export manifest script was found"))
    try:
        manifest = _json_object(content, EXPORT_MANIFEST_SCRIPT_ID)
    except _DashboardDoctorError as exc:
        stages.extend(
            [
                _stage("export_manifest_valid", "failed", exc.detail),
                _stage("export_asset_found", "skipped", "export manifest was invalid"),
                _stage("export_ciphertext_hash_valid", "skipped", "export manifest was invalid"),
                _stage("export_decrypts", "skipped", "export manifest was invalid"),
                _stage("export_plaintext_hash_valid", "skipped", "export manifest was invalid"),
            ]
        )
        return stages, "failed"

    manifest_stages, salt, iv = _validate_export_manifest_contract(manifest)
    stages.extend(manifest_stages)
    if _any_failed(manifest_stages) or salt is None or iv is None:
        stages.extend(
            [
                _stage("export_asset_found", "skipped", "export manifest was invalid"),
                _stage("export_ciphertext_hash_valid", "skipped", "export manifest was invalid"),
                _stage("export_decrypts", "skipped", "export manifest was invalid"),
                _stage("export_plaintext_hash_valid", "skipped", "export manifest was invalid"),
            ]
        )
        return stages, "failed"

    asset = cast(str, manifest["asset"])
    asset_path = dashboard_html_path.parent / asset
    try:
        ciphertext = asset_path.read_bytes()
    except OSError as exc:
        stages.extend(
            [
                _stage("export_asset_found", "failed", f"export asset was not readable: {exc}"),
                _stage("export_ciphertext_hash_valid", "skipped", "export asset was unavailable"),
                _stage("export_decrypts", "skipped", "export asset was unavailable"),
                _stage("export_plaintext_hash_valid", "skipped", "export asset was unavailable"),
            ]
        )
        return stages, "failed"

    stages.append(_stage("export_asset_found", "passed", f"export asset {asset} was readable"))
    actual_ciphertext_sha256 = hashlib.sha256(ciphertext).hexdigest()
    expected_ciphertext_sha256 = cast(str, manifest["ciphertext_sha256"])
    expected_ciphertext_size = cast(int, manifest["ciphertext_size"])
    ciphertext_ok = (
        len(ciphertext) == expected_ciphertext_size
        and actual_ciphertext_sha256 == expected_ciphertext_sha256
    )
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
            [
                _stage("export_decrypts", "skipped", "ciphertext integrity check failed"),
                _stage("export_plaintext_hash_valid", "skipped", "ciphertext integrity check failed"),
            ]
        )
        return stages, "failed"

    accepted_secrets = _accepted_secret_values(secret_inputs, secret_results)
    if not accepted_secrets:
        stages.extend(
            [
                _stage("export_decrypts", "skipped", "no accepted dashboard secret was available"),
                _stage("export_plaintext_hash_valid", "skipped", "no accepted dashboard secret was available"),
            ]
        )
        return stages, "skipped"

    expected_plaintext_sha256 = cast(str, manifest["plaintext_sha256"])
    decrypt_failures: list[str] = []
    plaintext_hash_failures: list[str] = []
    for label, secret in accepted_secrets:
        export_key = _derive_key(secret, salt)
        try:
            plaintext = AESGCM(export_key).decrypt(iv, ciphertext, None)
        except InvalidTag:
            decrypt_failures.append(label)
            stages.append(_stage("export_decrypts", "failed", "AES-GCM authentication failed", label))
            continue
        stages.append(_stage("export_decrypts", "passed", "export asset decrypted", label))
        actual_plaintext_sha256 = hashlib.sha256(plaintext).hexdigest()
        if actual_plaintext_sha256 != expected_plaintext_sha256:
            plaintext_hash_failures.append(label)
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
        return stages, "passed"

    if decrypt_failures or plaintext_hash_failures:
        return stages, "failed"
    return stages, "skipped"


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
    stages: list[DoctorStage] = []
    chunks_checked = 0
    chunks = _object_dict(data.get("chunks"))
    chunk_count = len(chunks)
    repo_count = 0

    if salt is None:
        stages.extend(
            [
                _stage("key_derivation_ready", "failed", "salt was unavailable", label),
                _stage("summary_authenticates", "skipped", "key derivation failed", label),
            ]
        )
        return DoctorSecretResult(label=label, provided=True, stages=stages), 0, chunk_count, 0

    try:
        key = _derive_key(secret, salt)
    except Exception as exc:
        stages.extend(
            [
                _stage("key_derivation_ready", "failed", f"key derivation failed: {exc}", label),
                _stage("summary_authenticates", "skipped", "key derivation failed", label),
            ]
        )
        return DoctorSecretResult(label=label, provided=True, stages=stages), 0, chunk_count, 0

    stages.append(_stage("key_derivation_ready", "passed", "key derivation inputs are usable", label))
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
        return DoctorSecretResult(label=label, provided=True, stages=stages), 0, chunk_count, 0

    repo_chunks, repo_count, summary_schema_stages = _validate_summary_staged(summary)
    stages.extend(summary_schema_stages)
    items = list(repo_chunks.items())
    if chunk_limit is not None:
        items = items[: max(0, chunk_limit)]
    for repo_name, chunk_id in items:
        token = chunks.get(chunk_id)
        if not isinstance(token, str):
            stages.append(
                _stage(
                    "chunk_payload_present",
                    "failed",
                    f"dashboard chunk {chunk_id} for {repo_name} was missing",
                    f"{repo_name}:{chunk_id}",
                )
            )
            continue
        stages.append(
            _stage(
                "chunk_payload_present",
                "passed",
                "referenced chunk payload is present",
                f"{repo_name}:{chunk_id}",
            )
        )
        chunk, chunk_decode_stages = _decrypt_gzip_json_staged(
            token,
            key,
            subject=f"{repo_name}:{chunk_id}",
            auth_stage="chunk_authenticates",
            decompress_stage="chunk_decompresses",
            json_stage="chunk_json_valid",
        )
        stages.extend(chunk_decode_stages)
        if chunk is None:
            continue
        stages.extend(_validate_chunk_staged(repo_name, chunk_id, chunk))
        chunks_checked += 1

    if _stage_passed(summary_schema_stages, "summary_repo_chunk_mapping_valid"):
        stages.append(_semantic_counts_stage(repo_count, repo_chunks, chunks))
    else:
        stages.append(
            _stage("semantic_counts_valid", "skipped", "summary repo_chunks were unavailable")
        )
    return DoctorSecretResult(label=label, provided=True, stages=stages), chunks_checked, chunk_count, repo_count


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
            stages.append(_stage("chunk_payload_present", "failed", "plaintext chunk was missing", subject))
            continue
        stages.append(_stage("chunk_payload_present", "passed", "referenced chunk payload is present", subject))
        try:
            chunk = json.loads(raw_chunk)
        except json.JSONDecodeError as exc:
            stages.append(_stage("chunk_json_valid", "failed", f"plaintext chunk was not valid JSON: {exc}", subject))
            continue
        if not isinstance(chunk, dict):
            stages.append(_stage("chunk_json_valid", "failed", "plaintext chunk was not a JSON object", subject))
            continue
        stages.append(_stage("chunk_json_valid", "passed", "plaintext chunk parsed as JSON", subject))
        stages.extend(_validate_chunk_staged(repo_name, chunk_id, chunk))
        chunks_checked += 1
    if _stage_passed(summary_stages, "summary_repo_chunk_mapping_valid"):
        stages.append(_semantic_counts_stage(repo_count, repo_chunks, chunks))
    else:
        stages.append(
            _stage("semantic_counts_valid", "skipped", "summary repo_chunks were unavailable")
        )
    return stages, chunks_checked, len(chunks), repo_count


def _ui_handoff_stage(
    *,
    configured_mode: DoctorArtifactMode,
    detected_mode: DetectedDashboardMode,
    stages: list[DoctorStage],
    secret_results: list[DoctorSecretResult],
    repo_count: int,
) -> DoctorStage:
    prerequisites = {
        "dashboard_html_found",
        "configured_artifact_mode_recorded",
        "detected_dashboard_mode_recorded",
        "configured_detected_mode_match",
        "dashboard_script_json_valid",
        "browser_envelope_version_valid",
        "browser_envelope_encoding_valid",
        "browser_envelope_chunks_object_valid",
        "browser_envelope_chunk_count_valid",
        "browser_envelope_chunk_ids_valid",
        "summary_min_schema_valid",
        "summary_repo_chunk_mapping_valid",
        "semantic_counts_valid",
    }
    if repo_count > 0:
        prerequisites.update(
            {
                "chunk_payload_present",
                "chunk_json_valid",
                "chunk_min_schema_valid",
                "chunk_repo_matches_summary",
                "chunk_growth_contract_valid",
            }
        )
    if configured_mode == "encrypted":
        prerequisites.update(
            {
                "browser_envelope_cipher_valid",
                "browser_envelope_kdf_valid",
                "browser_envelope_salt_valid",
                "browser_envelope_summary_token_valid",
            }
        )
        if repo_count > 0:
            prerequisites.update({"chunk_authenticates", "chunk_decompresses"})
    data_stages = list(stages)
    accepted_secret = next((result for result in secret_results if result.accepted), None)
    if configured_mode == "encrypted":
        if accepted_secret is None:
            return _stage(
                "ui_handoff_boundary_reached",
                "failed",
                "no supplied secret authenticated the encrypted dashboard summary",
            )
        data_stages.extend(accepted_secret.stages)

    if detected_mode != configured_mode:
        return _stage(
            "ui_handoff_boundary_reached",
            "failed",
            "configured and detected dashboard modes were not compatible",
        )
    if not _all_required_stage_statuses_passed(data_stages, prerequisites):
        return _stage(
            "ui_handoff_boundary_reached",
            "failed",
            "one or more encryption, storage, or data-contract stages failed",
        )
    return _stage(
        "ui_handoff_boundary_reached",
        "passed",
        "rendered dashboard payload checks reached the browser/UI boundary",
    )


def diagnose_dashboard_artifact(
    dashboard_html_path: Path,
    *,
    configured_artifact_mode: str = "encrypted",
    secrets: list[tuple[str, str]] | None = None,
    chunk_limit: int | None = None,
    retained_data_dir: Path | None = None,
) -> DashboardDoctorResult:
    """Run staged diagnostics for a rendered dashboard HTML artifact."""
    configured_mode, configured_stage = _validate_configured_mode(configured_artifact_mode)
    stages: list[DoctorStage] = [configured_stage]
    secret_inputs = secrets or []
    secret_results: list[DoctorSecretResult] = []
    retained_status: DoctorStageStatus = "skipped"
    export_status: DoctorStageStatus = "skipped"
    chunks_checked = 0
    chunk_count = 0
    repo_count = 0

    try:
        html = dashboard_html_path.read_text(encoding="utf-8")
    except OSError as exc:
        stages.append(_stage("dashboard_html_found", "failed", f"dashboard HTML was not readable: {exc}"))
        stages.extend(
            [
                _stage("workflow_artifact_restore_requested", "skipped", "retained workflow artifact restore is not implemented in this diagnostic slice"),
                _stage("export_manifest_found", "skipped", "export diagnostics are not implemented in this diagnostic slice"),
                _stage("ui_handoff_boundary_reached", "failed", "dashboard HTML was unavailable"),
            ]
        )
        return DashboardDoctorResult(
            configured_artifact_mode=configured_mode,
            detected_dashboard_mode="unknown",
            dashboard_html_found="failed",
            browser_payload_contract_valid="skipped",
            key_cryptographically_accepted="skipped",
            dashboard_data_well_formed="skipped",
            dashboard_data_semantically_consistent="skipped",
            repo_chunks_valid="skipped",
            retained_data_artifact_decryptable=retained_status,
            export_artifact_valid=export_status,
            secret_results=[],
            stages=stages,
            dashboard_html_path=dashboard_html_path.as_posix(),
        )

    stages.append(_stage("dashboard_html_found", "passed", "dashboard HTML was readable"))
    detected_mode, payload, payload_stages = _parse_dashboard_payload(html)
    stages.extend(payload_stages)
    stages.append(_mode_match_stage(configured_mode, detected_mode))
    browser_stage_names = {
        "browser_envelope_version_valid",
        "browser_envelope_cipher_valid",
        "browser_envelope_kdf_valid",
        "browser_envelope_encoding_valid",
        "browser_envelope_salt_valid",
        "browser_envelope_summary_token_valid",
        "browser_envelope_chunks_object_valid",
        "browser_envelope_chunk_count_valid",
        "browser_envelope_chunk_ids_valid",
    }

    if payload is not None and detected_mode == "encrypted":
        encrypted_stages, salt = _validate_encrypted_contract(payload)
        stages.extend(encrypted_stages)
        for label, secret in secret_inputs:
            if not secret:
                secret_results.append(
                    _skip_secret_result(label, provided=False, detail="secret was not configured")
                )
                continue
            result, checked, total_chunks, total_repos = _diagnose_encrypted_secret(
                label,
                secret,
                payload,
                salt,
                chunk_limit=chunk_limit,
            )
            secret_results.append(result)
            if result.accepted and checked >= chunks_checked:
                chunks_checked = checked
                chunk_count = total_chunks
                repo_count = total_repos
    elif payload is not None and detected_mode == "plaintext":
        stages.extend(_validate_plain_contract(payload))
        plain_stages, chunks_checked, chunk_count, repo_count = _diagnose_plain_data(payload)
        stages.extend(plain_stages)
        for label, secret in secret_inputs:
            secret_results.append(
                _skip_secret_result(
                    label,
                    provided=bool(secret),
                    detail="plaintext mode has no dashboard decryption key",
                )
            )
    else:
        for label, secret in secret_inputs:
            secret_results.append(
                _skip_secret_result(
                    label,
                    provided=bool(secret),
                    detail="dashboard payload was unavailable",
                )
            )

    retained_stages, retained_status = _diagnose_retained_artifact(
        retained_data_dir,
        configured_mode=configured_mode,
        secret_inputs=secret_inputs,
        secret_results=secret_results,
    )
    stages.extend(retained_stages)
    export_stages, export_status = _diagnose_export_artifact(
        html,
        dashboard_html_path,
        detected_mode=detected_mode,
        secret_inputs=secret_inputs,
        secret_results=secret_results,
    )
    stages.extend(export_stages)
    stages.append(
        _ui_handoff_stage(
            configured_mode=configured_mode,
            detected_mode=detected_mode,
            stages=stages,
            secret_results=secret_results,
            repo_count=repo_count,
        )
    )

    accepted_secret = next((result for result in secret_results if result.accepted), None)
    if configured_mode == "plaintext":
        key_status: DoctorStageStatus = "skipped"
        data_stages = []
    else:
        key_status = "passed" if accepted_secret is not None else "failed"
        data_stages = accepted_secret.stages if accepted_secret is not None else []

    semantic_stage_names = {
        "summary_min_schema_valid",
        "summary_repo_chunk_mapping_valid",
        "chunk_repo_matches_summary",
        "chunk_growth_contract_valid",
        "semantic_counts_valid",
    }
    chunk_stage_names = {
        "chunk_payload_present",
        "chunk_authenticates",
        "chunk_decompresses",
        "chunk_json_valid",
        "chunk_min_schema_valid",
        "chunk_repo_matches_summary",
        "chunk_growth_contract_valid",
    }
    well_formed_stage_names = {
        "dashboard_script_json_valid",
        "summary_decompresses",
        "summary_json_valid",
        "summary_min_schema_valid",
        "chunk_decompresses",
        "chunk_json_valid",
    }
    combined_data_stages = stages + data_stages
    return DashboardDoctorResult(
        configured_artifact_mode=configured_mode,
        detected_dashboard_mode=detected_mode,
        dashboard_html_found=_status_from_stages(stages, {"dashboard_html_found"}),
        browser_payload_contract_valid=_status_from_stages(stages, browser_stage_names),
        key_cryptographically_accepted=key_status,
        dashboard_data_well_formed=_status_from_stages(combined_data_stages, well_formed_stage_names),
        dashboard_data_semantically_consistent=_status_from_stages(combined_data_stages, semantic_stage_names),
        repo_chunks_valid=_status_from_stages(combined_data_stages, chunk_stage_names),
        retained_data_artifact_decryptable=retained_status,
        export_artifact_valid=export_status,
        secret_results=secret_results,
        stages=stages,
        dashboard_html_path=dashboard_html_path.as_posix(),
        chunks_checked=chunks_checked,
        chunk_count=chunk_count,
        repo_count=repo_count,
    )


def _compat_stage(stage: DoctorStage) -> tuple[str, str]:
    if stage.name in {"summary_authenticates", "chunk_authenticates"}:
        return "decrypt", stage.detail
    if stage.name in {"summary_decompresses", "chunk_decompresses"}:
        return "decompress", stage.detail
    if stage.name in {"summary_json_valid", "chunk_json_valid", "dashboard_script_json_valid"}:
        return "parse", stage.detail
    if stage.name in {
        "summary_min_schema_valid",
        "summary_repo_chunk_mapping_valid",
        "chunk_min_schema_valid",
        "chunk_repo_matches_summary",
        "chunk_growth_contract_valid",
        "semantic_counts_valid",
    }:
        return "schema", stage.detail
    if stage.name == "chunk_payload_present":
        return "missing", stage.detail
    if stage.name.startswith("browser_envelope_"):
        return "payload_schema", stage.detail
    return stage.name, stage.detail


def check_dashboard_key(
    dashboard_html_path: Path,
    dashboard_key: str,
    *,
    chunk_limit: int | None = None,
) -> DashboardKeyCheckResult:
    """Check whether a supplied key decrypts an encrypted dashboard HTML artifact."""
    result = diagnose_dashboard_artifact(
        dashboard_html_path,
        configured_artifact_mode="encrypted",
        secrets=[("DASHBOARD_SECRET_DO_NOT_REPLACE", dashboard_key)],
        chunk_limit=chunk_limit,
    )
    secret_result = result.secret_results[0] if result.secret_results else None
    if secret_result is not None and secret_result.accepted and result.ui_handoff_reached:
        return DashboardKeyCheckResult(
            ok=True,
            stage="success",
            detail="supplied key decrypts this dashboard",
            chunks_checked=result.chunks_checked,
            chunk_count=result.chunk_count,
            repo_count=result.repo_count,
        )
    failed_stage = secret_result.terminal_stage if secret_result is not None else _first_status(result.stages, "failed")
    if failed_stage is None:
        failed_stage = DoctorStage("unknown", "failed", detail="dashboard diagnostics did not pass")
    compat_stage, detail = _compat_stage(failed_stage)
    return DashboardKeyCheckResult(ok=False, stage=compat_stage, detail=detail)


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dashboard-html", type=Path, required=True)
    parser.add_argument(
        "--dashboard-key",
        help="Dashboard key to check. Prefer DASHBOARD_SECRET_DO_NOT_REPLACE.",
    )
    parser.add_argument("--chunk-limit", type=int)
    args = parser.parse_args()

    dashboard_key = args.dashboard_key or os.environ.get("DASHBOARD_SECRET_DO_NOT_REPLACE", "")
    if not dashboard_key:
        print("DASHBOARD_KEY_CHECK: failed")
        print("STAGE: missing_secret")
        print("DETAIL: dashboard key was not provided")
        return 1

    result = check_dashboard_key(
        args.dashboard_html,
        dashboard_key,
        chunk_limit=args.chunk_limit,
    )
    status = "success" if result.ok else "failed"
    print(f"DASHBOARD_KEY_CHECK: {status}")
    print(f"STAGE: {result.stage}")
    print(f"DETAIL: {result.detail}")
    if result.ok:
        print(f"REPO_COUNT: {result.repo_count}")
        print(f"CHUNKS_CHECKED: {result.chunks_checked}/{result.chunk_count}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())
