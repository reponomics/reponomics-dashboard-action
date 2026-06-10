"""Offline diagnostics for generated Reponomics dashboard artifacts."""

from __future__ import annotations

import argparse
import base64
from collections import Counter
import gzip
from dataclasses import dataclass
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
from typing import Any, Literal, cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


ENCRYPTED_DASHBOARD_SCRIPT_ID = "encrypted-dashboard-data"
PLAIN_DASHBOARD_SCRIPT_ID = "plain-dashboard-data"
PLAIN_DASHBOARD_CONST_NAME = "dashboardDataObject"
EXPECTED_DASHBOARD_DATA_VERSION = 2
EXPECTED_KDF_NAME = "PBKDF2"
EXPECTED_KDF_HASH = "SHA-256"
EXPECTED_KDF_ITERATIONS = 600_000
EXPECTED_SALT_BYTES = 16
EXPECTED_IV_BYTES = 12
CHUNK_ID_RE = re.compile(r"^c[0-9]{4,}$")

DoctorStageStatus = Literal["passed", "failed", "skipped", "warning"]
DoctorArtifactMode = Literal["encrypted", "plain"]
DetectedDashboardMode = Literal["encrypted", "plain", "unknown"]


@dataclass(frozen=True)
class DoctorStage:
    """One bounded diagnostic observation."""

    name: str
    status: DoctorStageStatus
    subject: str = ""
    detail: str = ""

    def to_jsonable(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status,
            "subject": self.subject,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class DoctorSecretResult:
    """Per-label encrypted dashboard diagnostics."""

    label: str
    provided: bool
    stages: list[DoctorStage]

    @property
    def accepted(self) -> bool:
        return _stage_passed(self.stages, "summary_authenticates")

    @property
    def terminal_stage(self) -> DoctorStage:
        failed = _first_status(self.stages, "failed")
        if failed is not None:
            return failed
        warning = _first_status(self.stages, "warning")
        if warning is not None:
            return warning
        passed = [stage for stage in self.stages if stage.status == "passed"]
        if passed:
            return passed[-1]
        skipped = [stage for stage in self.stages if stage.status == "skipped"]
        if skipped:
            return skipped[-1]
        return DoctorStage("unknown", "failed", self.label, "no diagnostic stages were recorded")

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "provided": self.provided,
            "accepted": self.accepted,
            "stages": [stage.to_jsonable() for stage in self.stages],
        }


@dataclass(frozen=True)
class DashboardDoctorResult:
    """Staged dashboard artifact diagnostic result."""

    configured_artifact_mode: DoctorArtifactMode
    detected_dashboard_mode: DetectedDashboardMode
    dashboard_html_found: DoctorStageStatus
    browser_payload_contract_valid: DoctorStageStatus
    key_cryptographically_accepted: DoctorStageStatus
    dashboard_data_well_formed: DoctorStageStatus
    dashboard_data_semantically_consistent: DoctorStageStatus
    repo_chunks_valid: DoctorStageStatus
    retained_data_artifact_decryptable: DoctorStageStatus
    export_artifact_valid: DoctorStageStatus
    secret_results: list[DoctorSecretResult]
    stages: list[DoctorStage]
    dashboard_html_path: str
    chunks_checked: int = 0
    chunk_count: int = 0
    repo_count: int = 0

    @property
    def accepted_secret_count(self) -> int:
        return sum(1 for result in self.secret_results if result.accepted)

    @property
    def provided_secret_count(self) -> int:
        return sum(1 for result in self.secret_results if result.provided)

    @property
    def stage_counts(self) -> Counter[str]:
        counter: Counter[str] = Counter(stage.status for stage in self.stages)
        for secret_result in self.secret_results:
            counter.update(stage.status for stage in secret_result.stages)
        return counter

    @property
    def ui_handoff_reached(self) -> bool:
        return _stage_passed(self.stages, "ui_handoff_boundary_reached")

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "configured_artifact_mode": self.configured_artifact_mode,
            "detected_dashboard_mode": self.detected_dashboard_mode,
            "dashboard_html_found": self.dashboard_html_found,
            "browser_payload_contract_valid": self.browser_payload_contract_valid,
            "key_cryptographically_accepted": self.key_cryptographically_accepted,
            "dashboard_data_well_formed": self.dashboard_data_well_formed,
            "dashboard_data_semantically_consistent": self.dashboard_data_semantically_consistent,
            "repo_chunks_valid": self.repo_chunks_valid,
            "retained_data_artifact_decryptable": self.retained_data_artifact_decryptable,
            "export_artifact_valid": self.export_artifact_valid,
            "dashboard_html_path": self.dashboard_html_path,
            "chunks_checked": self.chunks_checked,
            "chunk_count": self.chunk_count,
            "repo_count": self.repo_count,
            "stage_counts": dict(self.stage_counts),
            "secret_results": [result.to_jsonable() for result in self.secret_results],
            "stages": [stage.to_jsonable() for stage in self.stages],
        }


@dataclass(frozen=True)
class DashboardKeyCheckResult:
    """Compatibility result for checking one key against encrypted dashboard HTML."""

    ok: bool
    stage: str
    detail: str
    chunks_checked: int = 0
    chunk_count: int = 0
    repo_count: int = 0


class _DashboardDoctorError(Exception):
    def __init__(self, stage: str, detail: str) -> None:
        super().__init__(detail)
        self.stage = stage
        self.detail = detail


class _ScriptJsonParser(HTMLParser):
    def __init__(self, script_id: str) -> None:
        super().__init__()
        self._script_id = script_id
        self._capture = False
        self.content = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("id") == self._script_id:
            self._capture = True
            self.content = ""

    def handle_data(self, data: str) -> None:
        if self._capture:
            self.content += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._capture:
            self._capture = False


def _stage(
    name: str,
    status: DoctorStageStatus,
    detail: str,
    subject: str = "",
) -> DoctorStage:
    return DoctorStage(name=name, status=status, subject=subject, detail=detail)


def _first_status(stages: list[DoctorStage], status: DoctorStageStatus) -> DoctorStage | None:
    return next((stage for stage in stages if stage.status == status), None)


def _stage_passed(stages: list[DoctorStage], name: str) -> bool:
    return any(stage.name == name and stage.status == "passed" for stage in stages)


def _stage_failed(stages: list[DoctorStage], name: str) -> bool:
    return any(stage.name == name and stage.status == "failed" for stage in stages)


def _all_named_passed(stages: list[DoctorStage], names: set[str]) -> bool:
    return all(_stage_passed(stages, name) for name in names)


def _any_failed(stages: list[DoctorStage]) -> bool:
    return any(stage.status == "failed" for stage in stages)


def _object_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}


def _status_from_stages(stages: list[DoctorStage], names: set[str]) -> DoctorStageStatus:
    relevant = [stage for stage in stages if stage.name in names]
    if not relevant:
        return "skipped"
    if any(stage.status == "failed" for stage in relevant):
        return "failed"
    if any(stage.status == "warning" for stage in relevant):
        return "warning"
    if all(stage.status == "skipped" for stage in relevant):
        return "skipped"
    return "passed"


def _optional_script_content(html: str, script_id: str) -> str:
    parser = _ScriptJsonParser(script_id)
    parser.feed(html)
    return parser.content.strip()


def _script_json(html: str, script_id: str) -> dict[str, Any]:
    content = _optional_script_content(html, script_id)
    if not content:
        raise _DashboardDoctorError(
            "missing_encrypted_payload",
            f"script payload {script_id!r} was not found",
        )
    return _json_object(content, script_id)


def _runtime_const_json(html: str, const_name: str) -> dict[str, Any]:
    match = re.search(
        rf"const {re.escape(const_name)} = (.*?);\nrenderDashboard\({re.escape(const_name)}\);",
        html,
        flags=re.S,
    )
    if not match:
        raise _DashboardDoctorError(
            "missing_plain_payload",
            f"runtime const payload {const_name!r} was not found",
        )
    return _json_object(match.group(1), const_name)


def _json_object(raw: str, subject: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _DashboardDoctorError(
            "payload_parse",
            f"payload {subject!r} was not valid JSON: {exc}",
        ) from exc
    if not isinstance(value, dict):
        raise _DashboardDoctorError("payload_schema", f"payload {subject!r} was not a JSON object")
    return value


def _b64_decode(value: Any) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("value was not a non-empty base64 string")
    return base64.b64decode(value.encode("ascii"), validate=True)


def _b64url_decode(value: str) -> bytes:
    padded = value + ("=" * ((4 - len(value) % 4) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _validate_encrypted_blob_token(token: Any) -> tuple[bytes, bytes]:
    if not isinstance(token, str):
        raise ValueError("encrypted token was not a string")
    parts = token.split(".")
    if len(parts) != 2:
        raise ValueError("encrypted token did not contain iv.ciphertext parts")
    iv = _b64url_decode(parts[0])
    ciphertext = _b64url_decode(parts[1])
    if len(iv) != EXPECTED_IV_BYTES:
        raise ValueError(f"iv was {len(iv)} bytes, expected {EXPECTED_IV_BYTES}")
    if not ciphertext:
        raise ValueError("ciphertext was empty")
    return iv, ciphertext


def _derive_key(dashboard_key: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=EXPECTED_KDF_ITERATIONS,
    )
    return kdf.derive(dashboard_key.encode("utf-8"))


def _decrypt_blob(token: str, key: bytes) -> dict[str, Any]:
    """Compatibility helper returning a decrypted JSON object or a terminal error."""
    try:
        iv, ciphertext = _validate_encrypted_blob_token(token)
        plaintext = AESGCM(key).decrypt(iv, ciphertext, None)
    except InvalidTag as exc:
        raise _DashboardDoctorError("decrypt", "AES-GCM authentication failed") from exc
    except Exception as exc:
        raise _DashboardDoctorError("payload_schema", f"encrypted blob was malformed: {exc}") from exc

    try:
        decompressed = gzip.decompress(plaintext)
    except OSError as exc:
        raise _DashboardDoctorError("decompress", f"decrypted blob was not valid gzip: {exc}") from exc

    try:
        value = json.loads(decompressed)
    except json.JSONDecodeError as exc:
        raise _DashboardDoctorError("parse", f"decrypted blob was not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise _DashboardDoctorError("schema", "decrypted blob was not a JSON object")
    return value


def _parse_dashboard_payload(
    html: str,
) -> tuple[DetectedDashboardMode, dict[str, Any] | None, list[DoctorStage]]:
    stages: list[DoctorStage] = []
    encrypted_content = _optional_script_content(html, ENCRYPTED_DASHBOARD_SCRIPT_ID)
    plain_script_content = _optional_script_content(html, PLAIN_DASHBOARD_SCRIPT_ID)

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

    if plain_script_content:
        stages.append(
            _stage(
                "detected_dashboard_mode_recorded",
                "passed",
                "plain dashboard payload marker was found",
            )
        )
        stages.append(
            _stage(
                "dashboard_script_found",
                "passed",
                f"script payload {PLAIN_DASHBOARD_SCRIPT_ID!r} was found",
            )
        )
        try:
            data = _json_object(plain_script_content, PLAIN_DASHBOARD_SCRIPT_ID)
        except _DashboardDoctorError as exc:
            stages.append(_stage("dashboard_script_json_valid", "failed", exc.detail))
            return "plain", None, stages
        stages.append(_stage("dashboard_script_json_valid", "passed", "plain payload is JSON"))
        return "plain", data, stages

    try:
        data = _runtime_const_json(html, PLAIN_DASHBOARD_CONST_NAME)
    except _DashboardDoctorError:
        stages.extend(
            [
                _stage(
                    "detected_dashboard_mode_recorded",
                    "failed",
                    "no encrypted or plain dashboard payload marker was found",
                ),
                _stage("dashboard_script_found", "failed", "dashboard payload was not found"),
            ]
        )
        return "unknown", None, stages

    stages.extend(
        [
            _stage(
                "detected_dashboard_mode_recorded",
                "passed",
                "plain dashboard payload was found in the transitional JS assignment",
            ),
            _stage(
                "dashboard_script_found",
                "warning",
                "plain payload uses dashboardDataObject assignment; migrate to a JSON script tag",
            ),
            _stage("dashboard_script_json_valid", "passed", "plain payload is JSON"),
        ]
    )
    return "plain", data, stages


def _validate_configured_mode(mode: str) -> tuple[DoctorArtifactMode, DoctorStage]:
    if mode == "plain":
        return "plain", _stage("configured_artifact_mode_recorded", "passed", "configured plain mode")
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
            "plain encoding is supported" if data.get("encoding") == "json" else "plain encoding is unsupported",
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

    if repo_chunks:
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
            stages.append(_stage("chunk_payload_present", "failed", "plain chunk was missing", subject))
            continue
        stages.append(_stage("chunk_payload_present", "passed", "referenced chunk payload is present", subject))
        try:
            chunk = json.loads(raw_chunk)
        except json.JSONDecodeError as exc:
            stages.append(_stage("chunk_json_valid", "failed", f"plain chunk was not valid JSON: {exc}", subject))
            continue
        if not isinstance(chunk, dict):
            stages.append(_stage("chunk_json_valid", "failed", "plain chunk was not a JSON object", subject))
            continue
        stages.append(_stage("chunk_json_valid", "passed", "plain chunk parsed as JSON", subject))
        stages.extend(_validate_chunk_staged(repo_name, chunk_id, chunk))
        chunks_checked += 1
    if repo_chunks:
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
    retained_status: DoctorStageStatus,
    export_status: DoctorStageStatus,
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
    if configured_mode == "encrypted":
        prerequisites.update(
            {
                "browser_envelope_cipher_valid",
                "browser_envelope_kdf_valid",
                "browser_envelope_salt_valid",
                "browser_envelope_summary_token_valid",
            }
        )
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
    if not _all_named_passed(data_stages, prerequisites):
        return _stage(
            "ui_handoff_boundary_reached",
            "failed",
            "one or more encryption, storage, or data-contract stages failed",
        )
    if retained_status == "failed" or export_status == "failed":
        return _stage(
            "ui_handoff_boundary_reached",
            "failed",
            "retained workflow artifact or export checks failed",
        )
    return _stage(
        "ui_handoff_boundary_reached",
        "passed",
        "encryption, storage, and data-contract checks reached the browser/UI boundary",
    )


def diagnose_dashboard_artifact(
    dashboard_html_path: Path,
    *,
    configured_artifact_mode: str = "encrypted",
    secrets: list[tuple[str, str]] | None = None,
    chunk_limit: int | None = None,
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
    elif payload is not None and detected_mode == "plain":
        stages.extend(_validate_plain_contract(payload))
        plain_stages, chunks_checked, chunk_count, repo_count = _diagnose_plain_data(payload)
        stages.extend(plain_stages)
        for label, secret in secret_inputs:
            secret_results.append(
                _skip_secret_result(
                    label,
                    provided=bool(secret),
                    detail="plain mode has no dashboard decryption key",
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

    stages.extend(
        [
            _stage(
                "workflow_artifact_restore_requested",
                "skipped",
                "retained workflow artifact restore is deferred; current diagnostics inspect rendered dashboard HTML",
            ),
            _stage(
                "export_manifest_found",
                "skipped",
                "export diagnostics are deferred; current diagnostics inspect dashboard payloads",
            ),
        ]
    )
    stages.append(
        _ui_handoff_stage(
            configured_mode=configured_mode,
            detected_mode=detected_mode,
            stages=stages,
            secret_results=secret_results,
            retained_status=retained_status,
            export_status=export_status,
        )
    )

    accepted_secret = next((result for result in secret_results if result.accepted), None)
    if configured_mode == "plain":
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
