"""Retained workflow artifact diagnostics for dashboard doctor mode."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import tarfile
import tempfile
from typing import Any, cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import lineage
import storage
from doctor_support import (
    EXPECTED_KDF_ITERATIONS,
    DoctorDataMode,
    DoctorSecretResult,
    DoctorStage,
    DoctorStageStatus,
    _accepted_secret_values,
    _b64url_decode,
    _derive_key,
    _stage,
)


RETAINED_ENCRYPTED_ARTIFACT_NAME = "dashboard-data.enc"


def _retained_encrypted_candidates(retained_data_dir: Path | None) -> list[Path]:
    if retained_data_dir is None:
        return []
    candidates = [
        retained_data_dir / RETAINED_ENCRYPTED_ARTIFACT_NAME,
        Path(".dashboard-data-artifact") / RETAINED_ENCRYPTED_ARTIFACT_NAME,
    ]
    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique.append(candidate)
    return unique


def _safe_extract_retained_tar(archive_bytes: bytes, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    root = target_dir.resolve()
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            if not member.isdir() and not member.isfile():
                raise ValueError(f"Refusing unsafe artifact member: {member.name}")
            if member.isfile() and not member.name:
                raise ValueError("Refusing unsafe artifact member with empty name")
            target = target_dir / member.name
            if not target.resolve().is_relative_to(root):
                raise ValueError(f"Refusing unsafe artifact path: {member.name}")

        for member in members:
            target = target_dir / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"Retained artifact file was unreadable: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as handle:
                handle.write(source.read())


def _validate_retained_data_dir(data_dir: Path) -> tuple[DoctorStage, DoctorStage]:
    missing = [filename for filename in storage.ARTIFACT_FILES if not (data_dir / filename).is_file()]
    schema_errors: list[str] = []
    if missing:
        schema_errors.append("missing files: " + ", ".join(missing[:5]))

    manifest: dict[str, Any] = {}
    manifest_path = data_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = _object_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
        except Exception as exc:
            schema_errors.append(f"manifest.json was invalid: {exc}")
        else:
            if str(manifest.get("schema_version") or "") != storage.SCHEMA_VERSION:
                schema_errors.append("manifest schema_version did not match runtime schema")
            if manifest.get("files") != list(storage.CSV_REGISTRY.keys()):
                schema_errors.append("manifest files did not match runtime CSV registry")

    for filename, (fieldnames, _date_field) in storage.CSV_REGISTRY.items():
        path = data_dir / filename
        if not path.is_file():
            continue
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                header = next(reader, [])
        except Exception as exc:
            schema_errors.append(f"{filename} was unreadable: {exc}")
            continue
        if header != fieldnames:
            schema_errors.append(f"{filename} header did not match schema")

    schema_stage = _stage(
        "retained_artifact_schema_valid",
        "failed" if schema_errors else "passed",
        "; ".join(schema_errors) if schema_errors else "retained artifact schema is valid",
    )
    if schema_errors:
        return schema_stage, _stage(
            "retained_artifact_lineage_valid",
            "skipped",
            "retained artifact schema was invalid",
        )

    try:
        snapshot = lineage.snapshot_payload(data_dir)
        lineage.validate_snapshot_lineage(snapshot)
    except Exception as exc:
        return schema_stage, _stage(
            "retained_artifact_lineage_valid",
            "failed",
            f"retained artifact lineage was invalid: {exc}",
        )
    if not snapshot.lineage:
        return schema_stage, _stage(
            "retained_artifact_lineage_valid",
            "skipped",
            "retained artifact has no lineage metadata",
        )
    return schema_stage, _stage(
        "retained_artifact_lineage_valid",
        "passed",
        "retained artifact lineage is valid",
    )


def _object_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}


def _load_retained_encrypted_payload(path: Path) -> tuple[list[DoctorStage], dict[str, Any] | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [_stage("retained_artifact_readable", "failed", f"encrypted artifact was not readable JSON: {exc}")], None
    if not isinstance(payload, dict):
        return [_stage("retained_artifact_readable", "failed", "encrypted artifact payload was not a JSON object")], None

    errors: list[str] = []
    if payload.get("version") != 1:
        errors.append("unsupported encrypted artifact version")
    if payload.get("kdf") != "PBKDF2-SHA256":
        errors.append("unsupported KDF")
    if payload.get("iterations") != EXPECTED_KDF_ITERATIONS:
        errors.append("unsupported KDF iterations")
    if payload.get("algorithm") != "AES-256-GCM":
        errors.append("unsupported algorithm")
    for field in ("salt", "iv", "ciphertext"):
        if not isinstance(payload.get(field), str) or not payload.get(field):
            errors.append(f"missing {field}")
    if errors:
        return [_stage("retained_artifact_readable", "failed", "; ".join(errors))], None
    return [_stage("retained_artifact_readable", "passed", "encrypted artifact payload is readable")], payload


def _diagnose_encrypted_retained_artifact(
    path: Path,
    *,
    secret_inputs: list[tuple[str, str]],
    secret_results: list[DoctorSecretResult],
) -> tuple[list[DoctorStage], DoctorStageStatus]:
    stages: list[DoctorStage] = [
        _stage("workflow_artifact_restore_requested", "passed", "inspecting restored retained artifact path"),
        _stage("retained_artifact_found", "passed", f"found retained artifact at {path.as_posix()}"),
    ]
    readable_stages, payload = _load_retained_encrypted_payload(path)
    stages.extend(readable_stages)
    if payload is None:
        stages.extend(
            [
                _stage("retained_artifact_decrypts", "skipped", "encrypted artifact payload was unreadable"),
                _stage("retained_artifact_schema_valid", "skipped", "encrypted artifact payload was unreadable"),
                _stage("retained_artifact_lineage_valid", "skipped", "encrypted artifact payload was unreadable"),
            ]
        )
        return stages, "failed"

    try:
        salt = _b64url_decode(cast(str, payload["salt"]))
        iv = _b64url_decode(cast(str, payload["iv"]))
        ciphertext = _b64url_decode(cast(str, payload["ciphertext"]))
    except Exception as exc:
        stages.extend(
            [
                _stage("retained_artifact_decrypts", "failed", f"encrypted artifact payload was malformed: {exc}"),
                _stage("retained_artifact_schema_valid", "skipped", "encrypted artifact payload was malformed"),
                _stage("retained_artifact_lineage_valid", "skipped", "encrypted artifact payload was malformed"),
            ]
        )
        return stages, "failed"

    accepted_secrets = _accepted_secret_values(secret_inputs, secret_results)
    if not accepted_secrets:
        stages.extend(
            [
                _stage("retained_artifact_decrypts", "skipped", "no accepted dashboard secret was available"),
                _stage("retained_artifact_schema_valid", "skipped", "no accepted dashboard secret was available"),
                _stage("retained_artifact_lineage_valid", "skipped", "no accepted dashboard secret was available"),
            ]
        )
        return stages, "skipped"

    for label, secret in accepted_secrets:
        key = _derive_key(secret, salt)
        try:
            plaintext = AESGCM(key).decrypt(iv, ciphertext, None)
        except InvalidTag:
            stages.append(_stage("retained_artifact_decrypts", "failed", "AES-GCM authentication failed", label))
            continue
        stages.append(_stage("retained_artifact_decrypts", "passed", "retained artifact decrypted", label))
        with tempfile.TemporaryDirectory() as temp_dir:
            extracted_dir = Path(temp_dir) / "data"
            try:
                _safe_extract_retained_tar(plaintext, extracted_dir)
            except Exception as exc:
                stages.extend(
                    [
                        _stage("retained_artifact_schema_valid", "failed", f"retained artifact tarball was invalid: {exc}"),
                        _stage("retained_artifact_lineage_valid", "skipped", "retained artifact schema was invalid"),
                    ]
                )
                return stages, "failed"
            schema_stage, lineage_stage = _validate_retained_data_dir(extracted_dir)
            stages.extend([schema_stage, lineage_stage])
            return stages, "failed" if schema_stage.status == "failed" or lineage_stage.status == "failed" else "passed"

    stages.extend(
        [
            _stage("retained_artifact_schema_valid", "skipped", "retained artifact did not decrypt"),
            _stage("retained_artifact_lineage_valid", "skipped", "retained artifact did not decrypt"),
        ]
    )
    return stages, "failed"


def _diagnose_plaintext_retained_artifact(data_dir: Path) -> tuple[list[DoctorStage], DoctorStageStatus]:
    present_files = [filename for filename in storage.ARTIFACT_FILES if (data_dir / filename).is_file()]
    if not present_files:
        return [
            _stage("workflow_artifact_restore_requested", "skipped", "no restored retained artifact contents were found"),
            _stage("retained_artifact_found", "skipped", "no restored retained artifact contents were found"),
            _stage("retained_artifact_readable", "skipped", "no restored retained artifact contents were found"),
            _stage("retained_artifact_decrypts", "skipped", "plaintext mode has no retained artifact decryption key"),
            _stage("retained_artifact_schema_valid", "skipped", "no restored retained artifact contents were found"),
            _stage("retained_artifact_lineage_valid", "skipped", "no restored retained artifact contents were found"),
        ], "skipped"

    schema_stage, lineage_stage = _validate_retained_data_dir(data_dir)
    stages = [
        _stage("workflow_artifact_restore_requested", "passed", "inspecting restored retained artifact path"),
        _stage("retained_artifact_found", "passed", f"found retained artifact contents at {data_dir.as_posix()}"),
        _stage("retained_artifact_readable", "passed", "retained artifact contents are readable"),
        _stage("retained_artifact_decrypts", "skipped", "plaintext mode has no retained artifact decryption key"),
        schema_stage,
        lineage_stage,
    ]
    status: DoctorStageStatus = "failed" if schema_stage.status == "failed" or lineage_stage.status == "failed" else "passed"
    return stages, status


def _diagnose_retained_artifact(
    retained_data_dir: Path | None,
    *,
    configured_mode: DoctorDataMode,
    secret_inputs: list[tuple[str, str]],
    secret_results: list[DoctorSecretResult],
) -> tuple[list[DoctorStage], DoctorStageStatus]:
    if retained_data_dir is None:
        return [
            _stage("workflow_artifact_restore_requested", "skipped", "no retained artifact path was configured"),
            _stage("retained_artifact_found", "skipped", "no retained artifact path was configured"),
            _stage("retained_artifact_readable", "skipped", "no retained artifact path was configured"),
            _stage("retained_artifact_decrypts", "skipped", "no retained artifact path was configured"),
            _stage("retained_artifact_schema_valid", "skipped", "no retained artifact path was configured"),
            _stage("retained_artifact_lineage_valid", "skipped", "no retained artifact path was configured"),
        ], "skipped"

    if configured_mode == "plaintext":
        return _diagnose_plaintext_retained_artifact(retained_data_dir)

    for candidate in _retained_encrypted_candidates(retained_data_dir):
        if candidate.is_file():
            return _diagnose_encrypted_retained_artifact(
                candidate,
                secret_inputs=secret_inputs,
                secret_results=secret_results,
            )
    return [
        _stage("workflow_artifact_restore_requested", "skipped", "no restored encrypted retained artifact was found"),
        _stage("retained_artifact_found", "skipped", "no restored encrypted retained artifact was found"),
        _stage("retained_artifact_readable", "skipped", "no restored encrypted retained artifact was found"),
        _stage("retained_artifact_decrypts", "skipped", "no restored encrypted retained artifact was found"),
        _stage("retained_artifact_schema_valid", "skipped", "no restored encrypted retained artifact was found"),
        _stage("retained_artifact_lineage_valid", "skipped", "no restored encrypted retained artifact was found"),
    ], "skipped"
