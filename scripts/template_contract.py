"""Validate the local action/template product contract."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

try:
    from scripts.repo_paths import find_repo_root
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_paths import find_repo_root  # type: ignore[import-not-found,no-redef]


ROOT = find_repo_root(Path(__file__))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard_action.run_modules.core import MANAGED_DOCS_BUNDLE_DIR, VERSION  # noqa: E402
ACTION_REPOSITORY = "reponomics/reponomics-dashboard-action"
MANAGED_DOCS_MANIFEST_NAME = ".manifest.json"
MANAGED_DOCS_MANIFEST_SCHEMA_VERSION = 1
REQUIRED_ACTION_INPUTS = {"allow-docs-sync"}
REQUIRED_ACTION_OUTPUTS = {"docs-sync-state", "docs-action-version", "docs-updated-at"}
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
ACTION_REF_RE = re.compile(r"reponomics/reponomics-dashboard-action@[^\s'\"<>)\]}]+")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TEMPLATE_RELEASE_REF_RE = re.compile(
    r"^reponomics-dashboard-v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$"
)


class TemplateContractError(RuntimeError):
    """Raised when the local action/template contract is invalid."""


@dataclass(frozen=True)
class ProtectedTemplateRef:
    ref: str
    template_version: str
    source_commit: str
    status: str = "required"


@dataclass(frozen=True)
class AcceptedActionRelease:
    repository: str
    version: str
    tag: str
    sha: str
    default_ref: str


@dataclass(frozen=True)
class TemplateContract:
    template_version: str
    action_repository: str
    default_action_ref: str
    compatible_action_major: int
    accepted_action: AcceptedActionRelease
    minimum_compatible_template_version: str
    protected_template_refs: tuple[ProtectedTemplateRef, ...]
    managed_docs_namespace: Path

    @property
    def action_version(self) -> str:
        return VERSION

    @property
    def action_tag(self) -> str:
        return f"v{self.action_version}"

    @property
    def major_tag(self) -> str:
        return self.default_action_ref


def load_contract(root: Path = ROOT) -> TemplateContract:
    path = root / "template-contract.yml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise TemplateContractError(f"{path} must parse as a YAML object")
    if payload.get("schema_version") != 1:
        raise TemplateContractError(f"{path} must declare schema_version: 1")

    template_version = str(payload.get("template_version") or "")
    minimum_compatible_template_version = str(
        payload.get("minimum_compatible_template_version") or ""
    )
    action_repository = str(payload.get("action_repository") or "")
    default_action_ref = str(payload.get("default_action_ref") or "")
    managed_docs_namespace = Path(str(payload.get("managed_docs_namespace") or ""))
    compatible_action_major = payload.get("compatible_action_major")
    accepted_action = _parse_accepted_action_release(
        payload.get("accepted_action"),
        path=path,
    )
    protected_template_refs = _parse_protected_template_refs(
        payload.get("protected_template_refs"),
        path=path,
    )

    if not SEMVER_RE.fullmatch(template_version):
        raise TemplateContractError(f"template_version must be SemVer, got {template_version!r}")
    if not SEMVER_RE.fullmatch(minimum_compatible_template_version):
        raise TemplateContractError(
            "minimum_compatible_template_version must be SemVer, "
            + f"got {minimum_compatible_template_version!r}"
        )
    if _version_tuple(minimum_compatible_template_version) > _version_tuple(
        template_version
    ):
        raise TemplateContractError(
            "minimum_compatible_template_version must not be newer than template_version"
        )
    if action_repository != ACTION_REPOSITORY:
        raise TemplateContractError(
            f"action_repository must be {ACTION_REPOSITORY}, got {action_repository!r}"
        )
    if not isinstance(compatible_action_major, int) or compatible_action_major < 0:
        raise TemplateContractError("compatible_action_major must be a non-negative integer")
    if default_action_ref != f"v{compatible_action_major}":
        raise TemplateContractError(
            (
                "default_action_ref must match compatible_action_major "
                + f"(expected v{compatible_action_major}, got {default_action_ref!r})"
            )
        )
    _validate_accepted_action_release(
        accepted_action,
        action_repository=action_repository,
        default_action_ref=default_action_ref,
        compatible_action_major=compatible_action_major,
    )
    if managed_docs_namespace.as_posix() != "docs/reponomics":
        raise TemplateContractError("managed_docs_namespace must be docs/reponomics")
    _validate_protected_template_refs(
        protected_template_refs,
        minimum_compatible_template_version=minimum_compatible_template_version,
    )

    return TemplateContract(
        template_version=template_version,
        action_repository=action_repository,
        default_action_ref=default_action_ref,
        compatible_action_major=compatible_action_major,
        accepted_action=accepted_action,
        minimum_compatible_template_version=minimum_compatible_template_version,
        protected_template_refs=tuple(protected_template_refs),
        managed_docs_namespace=managed_docs_namespace,
    )


def validate_action_metadata(action_yml: str) -> None:
    payload = yaml.safe_load(action_yml) or {}
    if not isinstance(payload, dict):
        raise TemplateContractError("action.yml must parse as a YAML object")
    inputs = payload.get("inputs")
    outputs = payload.get("outputs")
    if not isinstance(inputs, dict) or not isinstance(outputs, dict):
        raise TemplateContractError("action.yml must declare inputs and outputs")
    mode = inputs.get("mode")
    if not isinstance(mode, dict) or "docs-sync" not in str(mode.get("description") or ""):
        raise TemplateContractError("action.yml mode input must document docs-sync")
    missing_inputs = REQUIRED_ACTION_INPUTS - set(inputs)
    if missing_inputs:
        raise TemplateContractError(
            "action.yml is missing required docs-sync input(s): "
            + ", ".join(sorted(missing_inputs))
        )
    missing_outputs = REQUIRED_ACTION_OUTPUTS - set(outputs)
    if missing_outputs:
        raise TemplateContractError(
            "action.yml is missing required docs-sync output(s): "
            + ", ".join(sorted(missing_outputs))
        )


def validate_local_contract(root: Path = ROOT) -> TemplateContract:
    contract = load_contract(root)
    validate_action_metadata((root / "action.yml").read_text(encoding="utf-8"))
    if _major(VERSION) != contract.compatible_action_major:
        raise TemplateContractError(
            (
                f"local action version {VERSION} does not match template-compatible "
                + f"major {contract.compatible_action_major}"
            )
        )
    return contract


def _parse_protected_template_refs(
    raw_refs: object,
    *,
    path: Path,
) -> list[ProtectedTemplateRef]:
    if not isinstance(raw_refs, list) or not raw_refs:
        raise TemplateContractError(f"{path} must declare non-empty protected_template_refs")

    protected: list[ProtectedTemplateRef] = []
    for index, raw_ref in enumerate(raw_refs):
        if not isinstance(raw_ref, dict):
            raise TemplateContractError(
                f"protected_template_refs[{index}] must be a YAML object"
            )
        ref = str(raw_ref.get("ref") or "")
        template_version = str(raw_ref.get("template_version") or "")
        source_commit = str(raw_ref.get("source_commit") or "")
        status = str(raw_ref.get("status") or "required")

        if not TEMPLATE_RELEASE_REF_RE.fullmatch(ref):
            raise TemplateContractError(
                f"protected_template_refs[{index}].ref must be reponomics-dashboard-vX.Y.Z"
            )
        if not SEMVER_RE.fullmatch(template_version):
            raise TemplateContractError(
                f"protected_template_refs[{index}].template_version must be SemVer"
            )
        if ref != f"reponomics-dashboard-v{template_version}":
            raise TemplateContractError(
                f"protected_template_refs[{index}] ref must match template_version"
            )
        if not GIT_SHA_RE.fullmatch(source_commit):
            raise TemplateContractError(
                "protected_template_refs"
                + f"[{index}].source_commit must be a 40-character commit SHA"
            )
        if status != "required":
            raise TemplateContractError(
                f"protected_template_refs[{index}].status must be required"
            )
        protected.append(
            ProtectedTemplateRef(
                ref=ref,
                template_version=template_version,
                source_commit=source_commit,
                status=status,
            )
        )
    return protected


def _parse_accepted_action_release(
    raw_action: object,
    *,
    path: Path,
) -> AcceptedActionRelease:
    if not isinstance(raw_action, dict):
        raise TemplateContractError(f"{path} must declare accepted_action")

    repository = str(raw_action.get("repository") or "")
    version = str(raw_action.get("version") or "")
    tag = str(raw_action.get("tag") or "")
    sha = str(raw_action.get("sha") or "")
    default_ref = str(raw_action.get("default_ref") or "")
    return AcceptedActionRelease(
        repository=repository,
        version=version,
        tag=tag,
        sha=sha,
        default_ref=default_ref,
    )


def _validate_accepted_action_release(
    accepted_action: AcceptedActionRelease,
    *,
    action_repository: str,
    default_action_ref: str,
    compatible_action_major: int,
) -> None:
    if accepted_action.repository != action_repository:
        raise TemplateContractError("accepted_action.repository must match action_repository")
    if accepted_action.default_ref != default_action_ref:
        raise TemplateContractError("accepted_action.default_ref must match default_action_ref")
    if not SEMVER_RE.fullmatch(accepted_action.version):
        raise TemplateContractError(
            f"accepted_action.version must be SemVer, got {accepted_action.version!r}"
        )
    if accepted_action.tag != f"v{accepted_action.version}":
        raise TemplateContractError("accepted_action.tag must be v<accepted_action.version>")
    if _major(accepted_action.version) != compatible_action_major:
        raise TemplateContractError(
            "accepted_action.version must match compatible_action_major"
        )
    if not GIT_SHA_RE.fullmatch(accepted_action.sha):
        raise TemplateContractError("accepted_action.sha must be a 40-character commit SHA")


def _validate_protected_template_refs(
    protected_template_refs: list[ProtectedTemplateRef],
    *,
    minimum_compatible_template_version: str,
) -> None:
    seen_versions: set[str] = set()
    for protected in protected_template_refs:
        if protected.template_version in seen_versions:
            raise TemplateContractError(
                f"duplicate protected template version: {protected.template_version}"
            )
        seen_versions.add(protected.template_version)
    if minimum_compatible_template_version not in seen_versions:
        raise TemplateContractError(
            "minimum_compatible_template_version must be covered by protected_template_refs"
        )


def render_managed_docs_snapshot(
    *,
    contract: TemplateContract | None = None,
    updated_at: str | None = None,
) -> dict[str, str]:
    contract = contract or load_contract()
    rendered: dict[str, str] = {}
    for path in sorted(MANAGED_DOCS_BUNDLE_DIR.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(MANAGED_DOCS_BUNDLE_DIR).as_posix()
        _validate_managed_docs_relative_path(relative)
        rendered[relative] = path.read_text(encoding="utf-8")

    if not rendered:
        raise TemplateContractError("managed docs bundle is empty")

    hashes = {relative: _sha_text(text) for relative, text in sorted(rendered.items())}
    manifest = {
        "schema_version": MANAGED_DOCS_MANIFEST_SCHEMA_VERSION,
        "managed_namespace": contract.managed_docs_namespace.as_posix(),
        "action_repository": contract.action_repository,
        "action_version": contract.action_version,
        "updated_at": updated_at or _source_timestamp(),
        "files": dict(sorted(hashes.items())),
    }
    rendered[MANAGED_DOCS_MANIFEST_NAME] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return dict(sorted(rendered.items()))


def write_managed_docs_snapshot(
    namespace: Path,
    *,
    contract: TemplateContract | None = None,
    updated_at: str | None = None,
) -> None:
    rendered = render_managed_docs_snapshot(contract=contract, updated_at=updated_at)
    if namespace.exists():
        for path in sorted((item for item in namespace.rglob("*") if item.is_file()), reverse=True):
            path.unlink()
        for path in sorted((item for item in namespace.rglob("*") if item.is_dir()), reverse=True):
            path.rmdir()
    namespace.mkdir(parents=True, exist_ok=True)
    for relative, text in rendered.items():
        path = namespace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def verify_managed_docs_snapshot(
    namespace: Path,
    *,
    contract: TemplateContract | None = None,
) -> None:
    actual = _managed_docs_snapshot_files(namespace)
    if not actual:
        raise TemplateContractError(f"managed docs snapshot is missing: {namespace}")
    expected = render_managed_docs_snapshot(
        contract=contract,
        updated_at=_manifest_updated_at(actual),
    )
    if actual == expected:
        return

    expected_paths = set(expected)
    actual_paths = set(actual)
    missing = sorted(expected_paths - actual_paths)
    extra = sorted(actual_paths - expected_paths)
    changed = sorted(path for path in expected_paths & actual_paths if expected[path] != actual[path])
    details: list[str] = []
    details.extend(f"missing: {path}" for path in missing)
    details.extend(f"extra: {path}" for path in extra)
    details.extend(f"changed: {path}" for path in changed)
    formatted = "\n".join(f"  - {detail}" for detail in details)
    raise TemplateContractError("Managed docs snapshot does not match local bundle:\n" + formatted)


def verify_template_refs(
    root: Path = ROOT,
    *,
    contract: TemplateContract | None = None,
) -> None:
    contract = contract or validate_local_contract(root)
    expected_ref = f"{contract.action_repository}@{contract.default_action_ref}"
    stale: list[str] = []
    for path in _iter_text_files(root):
        relative = path.relative_to(root)
        if _is_relative_to(relative, contract.managed_docs_namespace):
            continue
        text = _read_text_if_possible(path)
        if not text:
            continue
        for action_ref_match in ACTION_REF_RE.finditer(text):
            if action_ref_match.group(0) != expected_ref:
                stale.append(f"{relative}: {action_ref_match.group(0)}")
    if stale:
        formatted = "\n".join(f"  - {entry}" for entry in stale)
        raise TemplateContractError(f"Stale template action references found:\n{formatted}")


def _managed_docs_snapshot_files(namespace: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    if not namespace.exists():
        return files
    for path in sorted(namespace.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(namespace).as_posix()
        if relative != MANAGED_DOCS_MANIFEST_NAME:
            _validate_managed_docs_relative_path(relative)
        files[relative] = path.read_text(encoding="utf-8")
    return files


def _manifest_updated_at(snapshot: dict[str, str]) -> str:
    try:
        manifest = json.loads(snapshot[MANAGED_DOCS_MANIFEST_NAME])
    except (KeyError, json.JSONDecodeError) as exc:
        raise TemplateContractError("managed docs snapshot manifest is invalid") from exc
    updated_at = manifest.get("updated_at")
    if not isinstance(updated_at, str) or not updated_at.strip():
        raise TemplateContractError("managed docs snapshot manifest is missing updated_at")
    return updated_at


def _validate_managed_docs_relative_path(relative: str) -> None:
    path = Path(relative)
    if (
        not relative
        or path.is_absolute()
        or relative == MANAGED_DOCS_MANIFEST_NAME
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise TemplateContractError(f"invalid managed docs path: {relative!r}")


def _iter_text_files(root: Path) -> list[Path]:
    skipped_dirs = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "venv"}
    files: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in skipped_dirs for part in relative.parts):
            continue
        if path.is_file():
            files.append(path)
    return sorted(files)


def _read_text_if_possible(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def _is_relative_to(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _source_timestamp() -> str:
    try:
        timestamp = subprocess.check_output(
            ["git", "log", "-1", "--format=%cI"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "source"
    return _normalize_timestamp_utc(timestamp)


def _normalize_timestamp_utc(timestamp: str) -> str:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return timestamp
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _version_tuple(version: str) -> tuple[int, int, int]:
    match = SEMVER_RE.fullmatch(version)
    if not match:
        raise TemplateContractError(f"invalid SemVer: {version!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def _major(version: str) -> int:
    return _version_tuple(version)[0]


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
