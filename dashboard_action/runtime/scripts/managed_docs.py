"""Materialize managed Reponomics documentation into a consumer repository."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MANIFEST_NAME = ".manifest.json"
MANIFEST_SCHEMA_VERSION = 1
STATE_UNCHANGED = "unchanged"
STATE_WRITTEN = "written"
STATE_DISABLED = "disabled"
STATE_PERMISSION_MISSING = "permission_missing"
STATE_MANIFEST_INCONSISTENT = "manifest_inconsistent"
STATE_PUSH_RACE = "push_race"


class ManagedDocsError(RuntimeError):
    """Raised when the bundled managed docs payload is invalid."""


@dataclass(frozen=True)
class ManagedDocsResult:
    state: str
    reason: str
    manifest_action_version: str
    docs_updated_at: str
    namespace: Path
    changed: bool = False


def sync_managed_docs(
    *,
    namespace: Path,
    bundle_dir: Path,
    action_repository: str,
    action_version: str,
    allowed: bool,
) -> ManagedDocsResult:
    """Sync the bundled docs into the managed namespace without committing."""
    namespace = Path(namespace)
    if not allowed:
        return _result(
            STATE_DISABLED,
            "Managed documentation sync is disabled.",
            "",
            "",
            namespace,
        )

    symlink = _first_symlink_in_namespace(namespace)
    if symlink:
        return _result(
            STATE_MANIFEST_INCONSISTENT,
            f"Managed docs namespace contains a symlink: {symlink}",
            "",
            "",
            namespace,
        )

    bundle_files = _load_bundle(bundle_dir)
    next_hashes = {path: _sha_bytes(content) for path, content in bundle_files.items()}
    manifest_path = namespace / MANIFEST_NAME
    current_hashes = _current_file_hashes(namespace)

    manifest_action_version = ""
    docs_updated_at = ""
    manifest_hashes: dict[str, str] = {}
    try:
        if manifest_path.exists():
            manifest = _read_manifest(manifest_path)
            manifest_hashes = _validate_manifest(
                manifest,
                namespace=namespace,
                action_repository=action_repository,
            )
            manifest_action_version = str(manifest.get("action_version") or "")
            docs_updated_at = str(manifest.get("updated_at") or "")
    except ManagedDocsError:
        manifest_hashes = {}
        manifest_action_version = ""
        docs_updated_at = ""

    current_managed_hashes = {
        relative: current_hashes.get(relative) for relative in next_hashes
    }
    if (
        manifest_action_version == action_version
        and manifest_hashes == next_hashes
        and current_managed_hashes == next_hashes
    ):
        return _result(
            STATE_UNCHANGED,
            "Managed documentation is current.",
            manifest_action_version,
            docs_updated_at,
            namespace,
        )

    directory_collision = _first_directory_collision(namespace, bundle_files)
    if directory_collision:
        return _result(
            STATE_MANIFEST_INCONSISTENT,
            f"Managed docs target path is a directory: {directory_collision}",
            manifest_action_version,
            docs_updated_at,
            namespace,
        )

    previous_managed_files = (
        manifest_hashes
        if manifest_hashes
        else {
            relative: digest
            for relative, digest in current_hashes.items()
            if relative in next_hashes
        }
    )
    updated_at = _utc_now()
    _write_bundle(
        namespace=namespace,
        bundle_files=bundle_files,
        previous_files=previous_managed_files,
        manifest=_build_manifest(
            namespace=namespace,
            action_repository=action_repository,
            action_version=action_version,
            updated_at=updated_at,
            file_hashes=next_hashes,
        ),
    )
    return _result(
        STATE_WRITTEN,
        "Managed documentation was written.",
        action_version,
        updated_at,
        namespace,
        changed=True,
    )


def _result(
    state: str,
    reason: str,
    manifest_action_version: str,
    docs_updated_at: str,
    namespace: Path,
    *,
    changed: bool = False,
) -> ManagedDocsResult:
    return ManagedDocsResult(
        state=state,
        reason=reason,
        manifest_action_version=manifest_action_version,
        docs_updated_at=docs_updated_at,
        namespace=namespace,
        changed=changed,
    )


def _load_bundle(bundle_dir: Path) -> dict[str, bytes]:
    bundle_dir = Path(bundle_dir)
    if not bundle_dir.is_dir():
        raise ManagedDocsError(f"managed docs bundle directory is missing: {bundle_dir}")

    files: dict[str, bytes] = {}
    for path in sorted(bundle_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(bundle_dir).as_posix()
        _validate_relative_path(relative)
        files[relative] = path.read_bytes()

    if not files:
        raise ManagedDocsError("managed docs bundle is empty.")
    return files


def _read_manifest(manifest_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManagedDocsError("managed docs manifest is not readable JSON.") from exc
    if not isinstance(payload, dict):
        raise ManagedDocsError("managed docs manifest must be a JSON object.")
    return payload


def _validate_manifest(
    manifest: dict[str, Any],
    *,
    namespace: Path,
    action_repository: str,
) -> dict[str, str]:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ManagedDocsError("managed docs manifest schema version is unsupported.")
    if manifest.get("managed_namespace") != namespace.as_posix():
        raise ManagedDocsError("managed docs manifest namespace does not match.")
    if manifest.get("action_repository") != action_repository:
        raise ManagedDocsError("managed docs manifest action repository does not match.")
    updated_at = manifest.get("updated_at")
    if not isinstance(updated_at, str) or not updated_at.strip():
        raise ManagedDocsError("managed docs manifest updated_at is missing.")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ManagedDocsError("managed docs manifest files must be a map.")

    hashes: dict[str, str] = {}
    for relative, digest in files.items():
        path = str(relative)
        _validate_relative_path(path)
        if not isinstance(digest, str) or not _is_sha256(digest):
            raise ManagedDocsError(f"managed docs manifest hash is invalid for {path}.")
        hashes[path] = digest
    return hashes


def _validate_relative_path(relative: str) -> None:
    path = Path(relative)
    if (
        not relative
        or path.is_absolute()
        or relative == MANIFEST_NAME
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ManagedDocsError(f"invalid managed docs relative path: {relative!r}")


def _current_file_hashes(namespace: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    if not namespace.exists():
        return hashes
    for path in sorted(namespace.rglob("*")):
        if not path.is_file() and not path.is_symlink():
            continue
        relative = path.relative_to(namespace).as_posix()
        if relative == MANIFEST_NAME:
            continue
        hashes[relative] = _sha_file(path)
    return hashes


def _first_symlink_component(path: Path) -> str:
    current = Path(path.anchor) if path.is_absolute() else Path()
    start = 1 if path.anchor else 0
    for part in path.parts[start:]:
        current = current / part
        if current.is_symlink():
            return current.as_posix()
    return ""


def _first_symlink_in_namespace(namespace: Path) -> str:
    symlink = _first_symlink_component(namespace)
    if symlink:
        return symlink
    if not namespace.exists():
        return ""
    for path in sorted(namespace.rglob("*")):
        if path.is_symlink():
            return path.relative_to(namespace).as_posix()
    return ""


def _first_directory_collision(namespace: Path, bundle_files: dict[str, bytes]) -> str:
    if not namespace.exists():
        return ""
    for relative in sorted(bundle_files):
        path = namespace / relative
        if path.exists() and path.is_dir():
            return relative
    return ""


def _write_bundle(
    *,
    namespace: Path,
    bundle_files: dict[str, bytes],
    previous_files: dict[str, str],
    manifest: dict[str, Any],
) -> None:
    namespace.mkdir(parents=True, exist_ok=True)

    for relative in sorted(set(previous_files) - set(bundle_files)):
        stale_path = namespace / relative
        if stale_path.exists():
            stale_path.unlink()

    _remove_empty_dirs(namespace)
    for relative, content in sorted(bundle_files.items()):
        path = namespace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    _remove_empty_dirs(namespace)
    (namespace / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _remove_empty_dirs(namespace: Path) -> None:
    for path in sorted((item for item in namespace.rglob("*") if item.is_dir()), reverse=True):
        try:
            path.rmdir()
        except OSError:
            # Best-effort cleanup: directory may be non-empty or changed concurrently.
            # This is non-fatal for managed docs synchronization.
            pass


def _build_manifest(
    *,
    namespace: Path,
    action_repository: str,
    action_version: str,
    updated_at: str,
    file_hashes: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "managed_namespace": namespace.as_posix(),
        "action_repository": action_repository,
        "action_version": action_version,
        "updated_at": updated_at,
        "files": dict(sorted(file_hashes.items())),
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _sha_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)
