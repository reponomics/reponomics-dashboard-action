"""Generate and verify generated-template provenance and release artifacts."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import stat
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.repo_paths import find_repo_root
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_paths import find_repo_root  # type: ignore[import-not-found,no-redef]


ROOT = find_repo_root(Path(__file__))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import template_contract  # noqa: E402

PROVENANCE_PATH = Path(".reponomics/template-provenance.json")
TREE_MANIFEST_FORMAT = "reponomics-template-tree-v1"
PROVENANCE_SCHEMA_VERSION = 1
EXCLUDED_PAYLOAD_PATHS = frozenset({PROVENANCE_PATH.as_posix()})


class TemplateProvenanceError(RuntimeError):
    """Raised when generated-template provenance cannot be verified."""


@dataclass(frozen=True)
class TreeDigest:
    manifest_bytes: bytes
    digest: str
    file_count: int
    byte_count: int


@dataclass(frozen=True)
class ReleaseArtifacts:
    archive: Path
    tree_manifest: Path
    checksums: Path


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _source_timestamp() -> str:
    raw = _git_value("show", "-s", "--format=%cI", "HEAD")
    if not raw:
        return "unknown"
    try:
        return (
            datetime.fromisoformat(raw.replace("Z", "+00:00"))
            .astimezone(UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except ValueError:
        return raw


def _source_commit() -> str:
    return _git_value("rev-parse", "HEAD") or "unknown"


def _is_excluded(relative: str, excluded_paths: frozenset[str]) -> bool:
    path = Path(relative)
    return relative in excluded_paths or ".git" in path.parts


def _mode_for(path: Path) -> str:
    mode = path.stat().st_mode
    return "100755" if mode & stat.S_IXUSR else "100644"


def _iter_payload_files(
    root: Path,
    *,
    excluded_paths: frozenset[str] = EXCLUDED_PAYLOAD_PATHS,
) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if _is_excluded(relative, excluded_paths):
            continue
        if path.is_symlink():
            raise TemplateProvenanceError(f"Template payload must not contain symlinks: {relative}")
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def canonical_tree_manifest(
    root: Path,
    *,
    excluded_paths: frozenset[str] = EXCLUDED_PAYLOAD_PATHS,
) -> bytes:
    root = root.resolve()
    entries: list[dict[str, Any]] = []
    for path in _iter_payload_files(root, excluded_paths=excluded_paths):
        data = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        entries.append(
            {
                "mode": _mode_for(path),
                "path": relative,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
        )
    return b"".join(
        json.dumps(entry, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
        for entry in entries
    )


def payload_tree_digest(
    root: Path,
    *,
    excluded_paths: frozenset[str] = EXCLUDED_PAYLOAD_PATHS,
) -> TreeDigest:
    manifest_bytes = canonical_tree_manifest(root, excluded_paths=excluded_paths)
    entries = [line for line in manifest_bytes.splitlines() if line]
    byte_count = sum(json.loads(line)["size"] for line in entries)
    return TreeDigest(
        manifest_bytes=manifest_bytes,
        digest=hashlib.sha256(manifest_bytes).hexdigest(),
        file_count=len(entries),
        byte_count=byte_count,
    )


def build_provenance(
    root: Path,
    *,
    contract: template_contract.TemplateContract | None = None,
) -> dict[str, Any]:
    contract = contract or template_contract.validate_local_contract(ROOT)
    tree = payload_tree_digest(root)
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "source": {
            "repository": contract.action_repository,
            "commit": _source_commit(),
        },
        "template": {
            "version": contract.template_version,
            "minimum_compatible_template_version": contract.minimum_compatible_template_version,
        },
        "action": {
            "repository": contract.action_repository,
            "default_ref": contract.default_action_ref,
            "compatible_major": contract.compatible_action_major,
            "accepted_release": {
                "repository": contract.accepted_action.repository,
                "version": contract.accepted_action.version,
                "tag": contract.accepted_action.tag,
                "sha": contract.accepted_action.sha,
                "default_ref": contract.accepted_action.default_ref,
            },
        },
        "generated_at": _source_timestamp(),
        "payload": {
            "tree_manifest_format": TREE_MANIFEST_FORMAT,
            "digest_algorithm": "sha256",
            "digest": tree.digest,
            "file_count": tree.file_count,
            "byte_count": tree.byte_count,
            "excluded_paths": sorted(EXCLUDED_PAYLOAD_PATHS),
        },
    }


def write_template_provenance(
    root: Path,
    *,
    contract: template_contract.TemplateContract | None = None,
) -> Path:
    root = root.resolve()
    provenance = build_provenance(root, contract=contract)
    path = root / PROVENANCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_template_provenance(root: Path) -> dict[str, Any]:
    path = root / PROVENANCE_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TemplateProvenanceError(f"Template provenance is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TemplateProvenanceError(f"Template provenance is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise TemplateProvenanceError(f"Template provenance must be a JSON object: {path}")
    return payload


def verify_template_provenance(
    root: Path,
    *,
    contract: template_contract.TemplateContract | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    contract = contract or template_contract.validate_local_contract(ROOT)
    actual = load_template_provenance(root)
    expected = build_provenance(root, contract=contract)
    if actual == expected:
        return actual

    details: list[str] = []
    for key in ("schema_version", "source", "template", "action", "generated_at", "payload"):
        if actual.get(key) != expected.get(key):
            details.append(f"{key}: expected {expected.get(key)!r}, got {actual.get(key)!r}")
    formatted = "\n".join(f"  - {detail}" for detail in details)
    raise TemplateProvenanceError("Template provenance does not match generated payload:\n" + formatted)


def write_tree_manifest(root: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload_tree_digest(root).manifest_bytes)
    return output


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tar_info(path: Path, arcname: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(arcname)
    data = path.read_bytes()
    info.size = len(data)
    info.mode = 0o755 if os.access(path, os.X_OK) else 0o644
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def package_release_artifacts(root: Path, output_dir: Path) -> ReleaseArtifacts:
    contract = template_contract.validate_local_contract(ROOT)
    verify_template_provenance(root, contract=contract)
    output_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"reponomics-dashboard-template-v{contract.template_version}"
    archive = output_dir / f"{prefix}.tar.gz"
    tree_manifest = output_dir / f"{prefix}.tree.jsonl"
    checksums = output_dir / "SHA256SUMS"

    write_tree_manifest(root, tree_manifest)
    with archive.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                for path in _iter_payload_files(root):
                    relative = path.relative_to(root).as_posix()
                    info = _tar_info(path, f"{prefix}/{relative}")
                    with path.open("rb") as handle:
                        tar.addfile(info, handle)
                provenance_path = root / PROVENANCE_PATH
                info = _tar_info(provenance_path, f"{prefix}/{PROVENANCE_PATH.as_posix()}")
                with provenance_path.open("rb") as handle:
                    tar.addfile(info, handle)

    checksum_lines = [
        f"{_sha256_file(archive)}  {archive.name}",
        f"{_sha256_file(tree_manifest)}  {tree_manifest.name}",
    ]
    checksums.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return ReleaseArtifacts(archive=archive, tree_manifest=tree_manifest, checksums=checksums)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    write_parser = subparsers.add_parser("write", help="Write template provenance.")
    write_parser.add_argument("--root", type=Path, required=True)

    verify_parser = subparsers.add_parser("verify", help="Verify template provenance.")
    verify_parser.add_argument("--root", type=Path, required=True)

    manifest_parser = subparsers.add_parser("manifest", help="Write the canonical tree manifest.")
    manifest_parser.add_argument("--root", type=Path, required=True)
    manifest_parser.add_argument("--output", type=Path, required=True)

    package_parser = subparsers.add_parser("package", help="Build release artifacts.")
    package_parser.add_argument("--root", type=Path, required=True)
    package_parser.add_argument("--output-dir", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "write":
        path = write_template_provenance(args.root)
        print(f"Wrote template provenance: {path}")
    elif args.command == "verify":
        provenance = verify_template_provenance(args.root)
        print(f"Verified template payload digest: {provenance['payload']['digest']}")
    elif args.command == "manifest":
        path = write_tree_manifest(args.root, args.output)
        print(f"Wrote template tree manifest: {path}")
    elif args.command == "package":
        artifacts = package_release_artifacts(args.root, args.output_dir)
        print(f"Built template release archive: {artifacts.archive}")
        print(f"Built template tree manifest: {artifacts.tree_manifest}")
        print(f"Built template checksums: {artifacts.checksums}")


if __name__ == "__main__":
    try:
        main()
    except TemplateProvenanceError as exc:
        print(f"Template provenance error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
