"""Shared types and low-level helpers for dashboard doctor diagnostics."""

from __future__ import annotations

import base64
from collections import Counter
from dataclasses import dataclass
import gzip
from html.parser import HTMLParser
import json
import re
from typing import Any, Literal, cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


ENCRYPTED_DASHBOARD_SCRIPT_ID = "encrypted-dashboard-data"
PLAINTEXT_DASHBOARD_SCRIPT_ID = "plaintext-dashboard-data"
EXPORT_MANIFEST_SCRIPT_ID = "export-manifest"
EXPECTED_DASHBOARD_DATA_VERSION = 2
EXPECTED_EXPORT_MANIFEST_VERSION = 1
EXPECTED_KDF_NAME = "PBKDF2"
EXPECTED_KDF_HASH = "SHA-256"
EXPECTED_KDF_ITERATIONS = 600_000
EXPECTED_SALT_BYTES = 16
EXPECTED_IV_BYTES = 12
CHUNK_ID_RE = re.compile(r"^c[0-9]{4,}$")
EXPORT_ASSET_RE = re.compile(r"^assets/export-data-[a-f0-9]{16}\.enc$")
SHA256_HEX_RE = re.compile(r"^[a-f0-9]{64}$")

DoctorStageStatus = Literal["passed", "failed", "skipped", "warning"]
DoctorArtifactMode = Literal["encrypted", "plaintext"]
DetectedDashboardMode = Literal["encrypted", "plaintext", "unknown"]


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


class DashboardDoctorError(Exception):
    def __init__(self, stage: str, detail: str) -> None:
        super().__init__(detail)
        self.stage = stage
        self.detail = detail


class ScriptJsonParser(HTMLParser):
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


def _all_required_stage_statuses_passed(stages: list[DoctorStage], names: set[str]) -> bool:
    return all(_status_from_stages(stages, {name}) == "passed" for name in names)


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
    parser = ScriptJsonParser(script_id)
    parser.feed(html)
    return parser.content.strip()


def _script_json(html: str, script_id: str) -> dict[str, Any]:
    content = _optional_script_content(html, script_id)
    if not content:
        raise DashboardDoctorError(
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
        raise DashboardDoctorError(
            "missing_plain_payload",
            f"runtime const payload {const_name!r} was not found",
        )
    return _json_object(match.group(1), const_name)


def _json_object(raw: str, subject: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DashboardDoctorError(
            "payload_parse",
            f"payload {subject!r} was not valid JSON: {exc}",
        ) from exc
    if not isinstance(value, dict):
        raise DashboardDoctorError("payload_schema", f"payload {subject!r} was not a JSON object")
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
        raise DashboardDoctorError("decrypt", "AES-GCM authentication failed") from exc
    except Exception as exc:
        raise DashboardDoctorError("payload_schema", f"encrypted blob was malformed: {exc}") from exc

    try:
        decompressed = gzip.decompress(plaintext)
    except OSError as exc:
        raise DashboardDoctorError("decompress", f"decrypted blob was not valid gzip: {exc}") from exc

    try:
        value = json.loads(decompressed)
    except json.JSONDecodeError as exc:
        raise DashboardDoctorError("parse", f"decrypted blob was not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise DashboardDoctorError("schema", "decrypted blob was not a JSON object")
    return value


def _accepted_secret_values(
    secret_inputs: list[tuple[str, str]],
    secret_results: list[DoctorSecretResult],
) -> list[tuple[str, str]]:
    values = dict(secret_inputs)
    return [
        (result.label, values[result.label])
        for result in secret_results
        if result.accepted and values.get(result.label)
    ]
