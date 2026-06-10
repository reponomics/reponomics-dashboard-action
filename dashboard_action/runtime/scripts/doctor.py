"""Offline diagnostics for generated Reponomics dashboard artifacts."""

from __future__ import annotations

import argparse
import base64
import gzip
from dataclasses import dataclass
from html.parser import HTMLParser
import json
import os
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


ENCRYPTED_DASHBOARD_SCRIPT_ID = "encrypted-dashboard-data"
EXPECTED_DASHBOARD_DATA_VERSION = 2
EXPECTED_KDF_NAME = "PBKDF2"
EXPECTED_KDF_HASH = "SHA-256"
EXPECTED_KDF_ITERATIONS = 600_000


@dataclass(frozen=True)
class DashboardKeyCheckResult:
    """Result of checking a supplied key against an encrypted dashboard HTML file."""

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


def _script_json(html: str, script_id: str) -> dict[str, Any]:
    parser = _ScriptJsonParser(script_id)
    parser.feed(html)
    if not parser.content.strip():
        raise _DashboardDoctorError(
            "missing_encrypted_payload",
            f"script payload {script_id!r} was not found",
        )
    try:
        value = json.loads(parser.content)
    except json.JSONDecodeError as exc:
        raise _DashboardDoctorError(
            "payload_parse",
            f"script payload {script_id!r} was not valid JSON: {exc}",
        ) from exc
    if not isinstance(value, dict):
        raise _DashboardDoctorError(
            "payload_schema",
            f"script payload {script_id!r} was not a JSON object",
        )
    return value


def _b64url_decode(value: str) -> bytes:
    padded = value + ("=" * ((4 - len(value) % 4) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _validate_encrypted_dashboard_data(data: dict[str, Any]) -> None:
    if data.get("version") != EXPECTED_DASHBOARD_DATA_VERSION:
        raise _DashboardDoctorError("payload_schema", "encrypted dashboard version is unsupported")
    if data.get("cipher") != "AES-GCM":
        raise _DashboardDoctorError("payload_schema", "encrypted dashboard cipher is unsupported")
    if data.get("encoding") != "gzip+json":
        raise _DashboardDoctorError("payload_schema", "encrypted dashboard encoding is unsupported")
    kdf = data.get("kdf")
    if not isinstance(kdf, dict):
        raise _DashboardDoctorError("payload_schema", "encrypted dashboard kdf is missing")
    if (
        kdf.get("name") != EXPECTED_KDF_NAME
        or kdf.get("hash") != EXPECTED_KDF_HASH
        or kdf.get("iterations") != EXPECTED_KDF_ITERATIONS
    ):
        raise _DashboardDoctorError("payload_schema", "encrypted dashboard kdf is unsupported")
    if not isinstance(data.get("salt"), str):
        raise _DashboardDoctorError("payload_schema", "encrypted dashboard salt is missing")
    if not isinstance(data.get("summary"), str):
        raise _DashboardDoctorError("payload_schema", "encrypted dashboard summary is missing")
    if not isinstance(data.get("chunks"), dict):
        raise _DashboardDoctorError("payload_schema", "encrypted dashboard chunks are missing")


def _derive_key(dashboard_key: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=EXPECTED_KDF_ITERATIONS,
    )
    return kdf.derive(dashboard_key.encode("utf-8"))


def _decrypt_blob(token: str, key: bytes) -> dict[str, Any]:
    try:
        iv_value, ciphertext_value = token.split(".", 1)
        plaintext = AESGCM(key).decrypt(
            _b64url_decode(iv_value),
            _b64url_decode(ciphertext_value),
            None,
        )
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


def _validate_summary(summary: dict[str, Any]) -> None:
    if not isinstance(summary.get("repos"), list):
        raise _DashboardDoctorError("schema", "dashboard summary repos are missing")
    if not isinstance(summary.get("totals"), dict):
        raise _DashboardDoctorError("schema", "dashboard summary totals are missing")
    if not isinstance(summary.get("repo_chunks"), dict):
        raise _DashboardDoctorError("schema", "dashboard summary repo_chunks are missing")


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


def check_dashboard_key(
    dashboard_html_path: Path,
    dashboard_key: str,
    *,
    chunk_limit: int | None = None,
) -> DashboardKeyCheckResult:
    """Check whether a supplied key decrypts an encrypted dashboard HTML artifact."""
    try:
        html = dashboard_html_path.read_text(encoding="utf-8")
    except OSError as exc:
        return DashboardKeyCheckResult(
            ok=False,
            stage="dashboard_html_found",
            detail=f"dashboard HTML was not readable: {exc}",
        )

    try:
        data = _script_json(html, ENCRYPTED_DASHBOARD_SCRIPT_ID)
        _validate_encrypted_dashboard_data(data)
        salt = base64.b64decode(data["salt"])
        key = _derive_key(dashboard_key, salt)
        summary = _decrypt_blob(data["summary"], key)
        _validate_summary(summary)

        repo_chunks = summary["repo_chunks"]
        chunks = data["chunks"]
        checked = 0
        items = list(repo_chunks.items())
        if chunk_limit is not None:
            items = items[: max(0, chunk_limit)]
        for repo_name, chunk_id in items:
            if not isinstance(repo_name, str) or not isinstance(chunk_id, str):
                raise _DashboardDoctorError(
                    "schema",
                    "dashboard summary repo_chunks must map repo names to chunk ids",
                )
            token = chunks.get(chunk_id)
            if not isinstance(token, str):
                raise _DashboardDoctorError(
                    "missing",
                    f"dashboard chunk {chunk_id} for {repo_name} was missing",
                )
            _validate_chunk(repo_name, chunk_id, _decrypt_blob(token, key))
            checked += 1

        return DashboardKeyCheckResult(
            ok=True,
            stage="success",
            detail="supplied key decrypts this dashboard",
            chunks_checked=checked,
            chunk_count=len(chunks),
            repo_count=len(summary["repos"]),
        )
    except _DashboardDoctorError as exc:
        return DashboardKeyCheckResult(ok=False, stage=exc.stage, detail=exc.detail)


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
