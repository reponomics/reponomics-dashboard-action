"""Materialize managed Reponomics documentation into a consumer repository."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MANIFEST_NAME = ".manifest.json"
MANIFEST_SCHEMA_VERSION = 1
STATE_UP_TO_DATE = "up_to_date"
STATE_UPDATED = "updated"
STATE_DISABLED = "disabled"
STATE_PERMISSION_MISSING = "permission_missing"
STATE_USER_MODIFIED_CONFLICT = "user_modified_conflict"
STATE_MANIFEST_INCONSISTENT = "manifest_inconsistent"
STATE_PUSH_RACE = "push_race"


class ManagedDocsError(RuntimeError):
    """Raised when the bundled managed docs payload is invalid."""


@dataclass(frozen=True)
class ManagedDocsResult:
    state: str
    reason: str
    docs_bundle_version: str
    manifest_action_version: str
    namespace: Path
    changed: bool = False


def sync_managed_docs(
    *,
    namespace: Path,
    bundle_dir: Path,
    action_repository: str,
    action_version: str,
    docs_bundle_version: str,
    enabled: bool,
) -> ManagedDocsResult:
    """Sync the bundled docs into the managed namespace without committing."""
    namespace = Path(namespace)
    symlink = _first_symlink_in_namespace(namespace)
    if symlink:
        return _result(
            STATE_MANIFEST_INCONSISTENT,
            f"Managed docs namespace contains a symlink: {symlink}",
            docs_bundle_version,
            "",
            namespace,
        )
    if not enabled:
        return _result(
            STATE_DISABLED,
            "Managed documentation sync is disabled.",
            docs_bundle_version,
            "",
            namespace,
        )

    bundle_files = _load_bundle(
        bundle_dir,
        action_version=action_version,
        docs_bundle_version=docs_bundle_version,
    )
    next_hashes = {path: _sha_bytes(content) for path, content in bundle_files.items()}
    manifest_path = namespace / MANIFEST_NAME

    if not manifest_path.exists():
        if _namespace_has_unowned_files(namespace):
            return _result(
                STATE_MANIFEST_INCONSISTENT,
                "Managed docs namespace exists without a valid manifest.",
                docs_bundle_version,
                "",
                namespace,
            )
        _write_bundle(
            namespace=namespace,
            bundle_files=bundle_files,
            previous_files={},
            manifest=_build_manifest(
                namespace=namespace,
                action_repository=action_repository,
                action_version=action_version,
                docs_bundle_version=docs_bundle_version,
                file_hashes=next_hashes,
            ),
        )
        return _result(
            STATE_UPDATED,
            "Managed documentation was written.",
            docs_bundle_version,
            action_version,
            namespace,
            changed=True,
        )

    try:
        manifest = _read_manifest(manifest_path)
        previous_hashes = _validate_manifest(
            manifest,
            namespace=namespace,
            action_repository=action_repository,
        )
    except ManagedDocsError as exc:
        return _result(
            STATE_MANIFEST_INCONSISTENT,
            str(exc),
            docs_bundle_version,
            "",
            namespace,
        )

    manifest_action_version = str(manifest.get("action_version") or "")
    untracked = _first_untracked_file(namespace, previous_hashes)
    if untracked:
        return _result(
            STATE_MANIFEST_INCONSISTENT,
            f"Managed docs namespace contains a file outside the manifest: {untracked}",
            docs_bundle_version,
            manifest_action_version,
            namespace,
        )
    conflict = _first_hash_conflict(namespace, previous_hashes)
    if conflict:
        return _result(
            STATE_USER_MODIFIED_CONFLICT,
            f"Managed docs file differs from manifest: {conflict}",
            docs_bundle_version,
            manifest_action_version,
            namespace,
        )

    current_bundle_version = str(manifest.get("docs_bundle_version") or "")
    if (
        manifest_action_version == action_version
        and current_bundle_version == docs_bundle_version
        and previous_hashes == next_hashes
    ):
        return _result(
            STATE_UP_TO_DATE,
            "Managed documentation is current.",
            docs_bundle_version,
            manifest_action_version,
            namespace,
        )

    _write_bundle(
        namespace=namespace,
        bundle_files=bundle_files,
        previous_files=previous_hashes,
        manifest=_build_manifest(
            namespace=namespace,
            action_repository=action_repository,
            action_version=action_version,
            docs_bundle_version=docs_bundle_version,
            file_hashes=next_hashes,
        ),
    )
    return _result(
        STATE_UPDATED,
        "Managed documentation was updated.",
        docs_bundle_version,
        action_version,
        namespace,
        changed=True,
    )


def _result(
    state: str,
    reason: str,
    docs_bundle_version: str,
    manifest_action_version: str,
    namespace: Path,
    *,
    changed: bool = False,
) -> ManagedDocsResult:
    return ManagedDocsResult(
        state=state,
        reason=reason,
        docs_bundle_version=docs_bundle_version,
        manifest_action_version=manifest_action_version,
        namespace=namespace,
        changed=changed,
    )


def _load_bundle(
    bundle_dir: Path,
    *,
    action_version: str,
    docs_bundle_version: str,
) -> dict[str, bytes]:
    bundle_dir = Path(bundle_dir)
    if not bundle_dir.is_dir():
        raise ManagedDocsError(f"managed docs bundle directory is missing: {bundle_dir}")

    files: dict[str, bytes] = {}
    for path in sorted(bundle_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(bundle_dir).as_posix()
        _validate_relative_path(relative)
        text = path.read_text(encoding="utf-8")
        text = text.replace("{{ACTION_VERSION}}", action_version)
        text = text.replace("{{DOCS_BUNDLE_VERSION}}", docs_bundle_version)
        files[relative] = text.encode("utf-8")

    if not files:
        raise ManagedDocsError("managed docs bundle is empty.")
    return files


def _namespace_has_unowned_files(namespace: Path) -> bool:
    if not namespace.exists():
        return False
    return any(path.is_file() or path.is_symlink() for path in namespace.rglob("*"))


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


def _first_hash_conflict(namespace: Path, file_hashes: dict[str, str]) -> str:
    for relative, expected_hash in sorted(file_hashes.items()):
        path = namespace / relative
        if path.is_symlink():
            return relative
        if not path.is_file():
            return relative
        if _sha_file(path) != expected_hash:
            return relative
    return ""


def _first_untracked_file(namespace: Path, file_hashes: dict[str, str]) -> str:
    for path in sorted(namespace.rglob("*")):
        if not path.is_file() and not path.is_symlink():
            continue
        relative = path.relative_to(namespace).as_posix()
        if relative == MANIFEST_NAME:
            continue
        if relative not in file_hashes:
            return relative
    return ""


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
            pass


def _build_manifest(
    *,
    namespace: Path,
    action_repository: str,
    action_version: str,
    docs_bundle_version: str,
    file_hashes: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "managed_namespace": namespace.as_posix(),
        "action_repository": action_repository,
        "action_version": action_version,
        "docs_bundle_version": docs_bundle_version,
        "files": dict(sorted(file_hashes.items())),
    }


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _sha_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)
