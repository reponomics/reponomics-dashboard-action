"""Synchronize the template's accepted Reponomics action release."""
# ruff: noqa: ISC002

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "template-action-release.yml"
ACTION_REPOSITORY = "reponomics/reponomics-dashboard-action"
GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT_SECONDS = 20
SEMVER_TAG_RE = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ACTION_REF_RE = re.compile(
    r"reponomics/reponomics-dashboard-action@v(0|[1-9]\d*)"
    r"(?:\.(0|[1-9]\d*)\.(0|[1-9]\d*))?"
)
ACTION_REF_ENV_RE = re.compile(
    r'^(?P<prefix>\s+REPONOMICS_ACTION_REF: ")'
    r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r'(?P<suffix>")$'
)
ACTION_SHA_ENV_RE = re.compile(
    r'^(?P<prefix>\s+REPONOMICS_ACTION_SHA: ")[0-9a-f]{40}(?P<suffix>")$'
)
STATUS_LINE_RE = re.compile(
    r"^(?P<prefix>Status: current(?: docs are aligned with the action| for action) `)"
    r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?P<suffix>`.*)$"
)

MANAGED_TEXT_PATHS = [
    "README.md",
    "docs/GENERATED_REPOSITORY_MODEL.md",
    "docs/README.md",
    "docs/architecture/ENCRYPTED_PAYLOAD_SIZE_AND_SIDE_CHANNELS.md",
    "docs/architecture/PRIVACY_CONFIGURATION_MATRIX.md",
    "docs/architecture/README.md",
    "docs/architecture/SUPPLY_CHAIN_ASSURANCE.md",
    "docs/architecture/VERSIONING_AND_UPDATES.md",
    "template/README.template.md",
    "template/.github/workflows/collect-and-publish.yml",
    "template/.github/workflows/doctor.yml",
    "template/.github/workflows/incident-reset.yml",
    "template/.github/workflows/rotate-key.yml",
    "tests/test_generated_repos.py",
]
SKIPPED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__INTERNAL__",
    "dist",
    "archived",
    "venv",
}
REQUIRED_ACTION_INPUTS = {"allow-docs-sync"}
REQUIRED_ACTION_OUTPUTS = {"docs-sync-state", "docs-action-version", "docs-updated-at"}
MANAGED_DOCS_SOURCE_PREFIX = "dashboard_action/runtime/managed_docs"
TEMPLATE_MANAGED_DOCS_PATH = Path("template/docs/reponomics")
MANAGED_DOCS_NAMESPACE = "docs/reponomics"
MANAGED_DOCS_MANIFEST_NAME = ".manifest.json"
MANAGED_DOCS_MANIFEST_SCHEMA_VERSION = 1


class ActionReleaseError(RuntimeError):
    """Raised when the accepted action release metadata is invalid or stale."""


@dataclass(frozen=True)
class ActionRelease:
    repository: str
    tag: str
    target_commitish: str
    release_url: str
    published_at: str

    @property
    def version(self) -> str:
        return self.tag.removeprefix("v")

    @property
    def major_tag(self) -> str:
        return f"v{self.version.split('.', 1)[0]}"


def _request_json(url: str) -> dict[str, Any]:
    headers = _request_headers(accept="application/vnd.github+json")
    request = urllib.request.Request(
        url,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ActionReleaseError(_format_http_error(url, exc)) from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ActionReleaseError(f"Could not fetch {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ActionReleaseError(f"Expected object response from {url}")
    return payload


def _request_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers=_request_headers(),
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise ActionReleaseError(_format_http_error(url, exc)) from exc
    except urllib.error.URLError as exc:
        raise ActionReleaseError(f"Could not fetch {url}: {exc}") from exc


def _github_token() -> str:
    return os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()


def _request_headers(*, accept: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": "reponomics-dashboard-dev-action-release-sync",
    }
    if accept:
        headers["Accept"] = accept
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    token = _github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _format_http_error(url: str, exc: urllib.error.HTTPError) -> str:
    headers = exc.headers
    rate_limit = {
        "resource": headers.get("x-ratelimit-resource", ""),
        "limit": headers.get("x-ratelimit-limit", ""),
        "remaining": headers.get("x-ratelimit-remaining", ""),
        "reset": headers.get("x-ratelimit-reset", ""),
        "used": headers.get("x-ratelimit-used", ""),
        "request_id": headers.get("x-github-request-id", ""),
    }
    details = ", ".join(
        f"{key}={value}" for key, value in rate_limit.items() if value
    )
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except OSError:
        body = ""
    body_excerpt = body[:500]
    message = f"Could not fetch {url}: HTTP {exc.code} {exc.reason}"
    if details:
        message += f" ({details})"
    if body_excerpt:
        message += f": {body_excerpt}"
    return message


def _validate_tag(tag: str) -> None:
    if not SEMVER_TAG_RE.match(tag):
        raise ActionReleaseError(f"Action release tag must be exact SemVer, got {tag!r}")


def _validate_sha(value: str) -> None:
    if not SHA_RE.match(value):
        raise ActionReleaseError(f"Action release target must be a 40-character SHA, got {value!r}")


def _tag_commit_sha(repository: str, tag: str) -> str:
    ref = _request_json(f"{GITHUB_API}/repos/{repository}/git/ref/tags/{tag}")
    obj = ref.get("object")
    if not isinstance(obj, dict):
        raise ActionReleaseError(f"Tag ref for {repository}@{tag} has no object")
    obj_type = str(obj.get("type") or "")
    obj_sha = str(obj.get("sha") or "")
    if obj_type == "commit":
        _validate_sha(obj_sha)
        return obj_sha
    if obj_type == "tag":
        tag_obj = _request_json(f"{GITHUB_API}/repos/{repository}/git/tags/{obj_sha}")
        target = tag_obj.get("object")
        if isinstance(target, dict) and target.get("type") == "commit":
            target_sha = str(target.get("sha") or "")
            _validate_sha(target_sha)
            return target_sha
    raise ActionReleaseError(f"Could not resolve {repository}@{tag} to a commit SHA")


def fetch_release(repository: str, tag: str) -> ActionRelease:
    _validate_tag(tag)
    payload = _request_json(f"{GITHUB_API}/repos/{repository}/releases/tags/{tag}")
    if payload.get("draft") or payload.get("prerelease"):
        raise ActionReleaseError(f"{repository}@{tag} must be a published stable release")
    target = str(payload.get("target_commitish") or "")
    if not SHA_RE.match(target):
        target = _tag_commit_sha(repository, tag)
    release = ActionRelease(
        repository=repository,
        tag=str(payload.get("tag_name") or ""),
        target_commitish=target,
        release_url=str(payload.get("html_url") or ""),
        published_at=str(payload.get("published_at") or ""),
    )
    validate_release(release)
    return release


def fetch_action_yml(release: ActionRelease) -> str:
    return _request_text(
        f"https://raw.githubusercontent.com/{release.repository}/{release.tag}/action.yml"
    )


def _validate_managed_docs_relative_path(relative: str) -> None:
    path = Path(relative)
    if (
        not relative
        or path.is_absolute()
        or relative == MANAGED_DOCS_MANIFEST_NAME
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ActionReleaseError(f"Invalid managed docs path from action release: {relative!r}")


def fetch_managed_docs_bundle(release: ActionRelease) -> dict[str, str]:
    tree_url = (
        f"{GITHUB_API}/repos/{release.repository}/git/trees/"
        f"{release.target_commitish}?recursive=1"
    )
    payload = _request_json(tree_url)
    tree = payload.get("tree")
    if not isinstance(tree, list):
        raise ActionReleaseError(f"Expected tree list from {tree_url}")

    source_prefix = f"{MANAGED_DOCS_SOURCE_PREFIX}/"
    bundle_paths: list[tuple[str, str]] = []
    for entry in tree:
        if not isinstance(entry, dict) or entry.get("type") != "blob":
            continue
        source_path = str(entry.get("path") or "")
        if not source_path.startswith(source_prefix):
            continue
        relative = source_path.removeprefix(source_prefix)
        _validate_managed_docs_relative_path(relative)
        bundle_paths.append((relative, source_path))

    if not bundle_paths:
        raise ActionReleaseError(
            f"{release.repository}@{release.tag} does not contain managed docs"
        )

    bundle: dict[str, str] = {}
    for relative, source_path in sorted(bundle_paths):
        quoted_path = urllib.parse.quote(source_path, safe="/")
        bundle[relative] = _request_text(
            f"https://raw.githubusercontent.com/"
            f"{release.repository}/{release.target_commitish}/{quoted_path}"
        )
    return bundle


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_managed_docs_snapshot(
    release: ActionRelease,
    bundle: dict[str, str],
) -> dict[str, str]:
    validate_release(release)
    if not bundle:
        raise ActionReleaseError("Managed docs bundle is empty")

    rendered: dict[str, str] = {}
    for relative, text in sorted(bundle.items()):
        _validate_managed_docs_relative_path(relative)
        rendered[relative] = text.replace("{{ACTION_VERSION}}", release.version)

    hashes = {relative: _sha_text(text) for relative, text in sorted(rendered.items())}
    manifest = {
        "schema_version": MANAGED_DOCS_MANIFEST_SCHEMA_VERSION,
        "managed_namespace": MANAGED_DOCS_NAMESPACE,
        "action_repository": release.repository,
        "action_version": release.version,
        "updated_at": release.published_at,
        "files": dict(sorted(hashes.items())),
    }
    rendered[MANAGED_DOCS_MANIFEST_NAME] = json.dumps(
        manifest,
        indent=2,
        sort_keys=True,
    ) + "\n"
    return dict(sorted(rendered.items()))


def _managed_docs_snapshot_files(root: Path) -> dict[str, str]:
    target = root / TEMPLATE_MANAGED_DOCS_PATH
    if not target.exists():
        return {}
    files: dict[str, str] = {}
    for path in sorted(target.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(target).as_posix()
        if relative != MANAGED_DOCS_MANIFEST_NAME:
            _validate_managed_docs_relative_path(relative)
        files[relative] = path.read_text(encoding="utf-8")
    return files


def write_managed_docs_snapshot(
    root: Path,
    release: ActionRelease,
    bundle: dict[str, str],
) -> None:
    expected = render_managed_docs_snapshot(release, bundle)
    target = root / TEMPLATE_MANAGED_DOCS_PATH
    if target.exists():
        for path in sorted((item for item in target.rglob("*") if item.is_file()), reverse=True):
            path.unlink()
        for path in sorted((item for item in target.rglob("*") if item.is_dir()), reverse=True):
            path.rmdir()
    target.mkdir(parents=True, exist_ok=True)
    for relative, text in expected.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def verify_managed_docs_snapshot(
    root: Path,
    release: ActionRelease,
    bundle: dict[str, str],
) -> None:
    expected = render_managed_docs_snapshot(release, bundle)
    actual = _managed_docs_snapshot_files(root)
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
    raise ActionReleaseError(
        "Managed docs snapshot does not match accepted action release:\n" + formatted
    )


def validate_release(release: ActionRelease) -> None:
    if release.repository != ACTION_REPOSITORY:
        raise ActionReleaseError(
            f"Action repository must be {ACTION_REPOSITORY}, got {release.repository!r}"
        )
    _validate_tag(release.tag)
    _validate_sha(release.target_commitish)
    expected_url = f"https://github.com/{release.repository}/releases/tag/{release.tag}"
    if release.release_url != expected_url:
        raise ActionReleaseError(f"Release URL must be {expected_url}, got {release.release_url!r}")
    if not release.published_at:
        raise ActionReleaseError("Release published_at must be set")


def validate_action_metadata(action_yml: str) -> None:
    payload = yaml.safe_load(action_yml) or {}
    if not isinstance(payload, dict):
        raise ActionReleaseError("action.yml must parse as a YAML object")
    inputs = payload.get("inputs")
    outputs = payload.get("outputs")
    if not isinstance(inputs, dict) or not isinstance(outputs, dict):
        raise ActionReleaseError("action.yml must declare inputs and outputs")
    mode = inputs.get("mode")
    if not isinstance(mode, dict) or "docs-sync" not in str(mode.get("description") or ""):
        raise ActionReleaseError("action.yml mode input must document docs-sync")
    missing_inputs = REQUIRED_ACTION_INPUTS - set(inputs)
    if missing_inputs:
        raise ActionReleaseError(
            "action.yml is missing required docs-sync input(s): "
            + ", ".join(sorted(missing_inputs))
        )
    missing_outputs = REQUIRED_ACTION_OUTPUTS - set(outputs)
    if missing_outputs:
        raise ActionReleaseError(
            "action.yml is missing required docs-sync output(s): "
            + ", ".join(sorted(missing_outputs))
        )


def load_manifest(root: Path = ROOT) -> ActionRelease:
    path = root / "template-action-release.yml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ActionReleaseError(f"{path} must parse as a YAML object")
    if payload.get("schema_version") != 1:
        raise ActionReleaseError(f"{path} must declare schema_version: 1")
    release = ActionRelease(
        repository=str(payload.get("repository") or ""),
        tag=str(payload.get("tag") or ""),
        target_commitish=str(payload.get("target_commitish") or ""),
        release_url=str(payload.get("release_url") or ""),
        published_at=str(payload.get("published_at") or ""),
    )
    validate_release(release)
    return release


def write_manifest(release: ActionRelease, root: Path = ROOT) -> None:
    validate_release(release)
    text = "\n".join(
        [
            "schema_version: 1",
            f"repository: {release.repository}",
            f"tag: {release.tag}",
            f"target_commitish: {release.target_commitish}",
            f"release_url: {release.release_url}",
            f'published_at: "{release.published_at}"',
            "",
        ]
    )
    (root / "template-action-release.yml").write_text(text, encoding="utf-8")


def _replace_status_versions(text: str, tag: str) -> str:
    lines = []
    for line in text.splitlines(keepends=True):
        newline = "\n" if line.endswith("\n") else ""
        body = line[:-1] if newline else line
        match = STATUS_LINE_RE.match(body)
        if match:
            body = f"{match.group('prefix')}{tag}{match.group('suffix')}"
        lines.append(body + newline)
    return "".join(lines)


def _replace_action_release_env(text: str, release: ActionRelease) -> str:
    lines = []
    for line in text.splitlines(keepends=True):
        newline = "\n" if line.endswith("\n") else ""
        body = line[:-1] if newline else line
        ref_match = ACTION_REF_ENV_RE.match(body)
        sha_match = ACTION_SHA_ENV_RE.match(body)
        if ref_match:
            body = f"{ref_match.group('prefix')}{release.tag}{ref_match.group('suffix')}"
        elif sha_match:
            body = (
                f"{sha_match.group('prefix')}"
                + f"{release.target_commitish}{sha_match.group('suffix')}"
            )
        lines.append(body + newline)
    return "".join(lines)


def sync_release(
    root: Path,
    release: ActionRelease,
    action_yml: str,
    *,
    managed_docs_bundle: dict[str, str] | None = None,
) -> None:
    validate_release(release)
    validate_action_metadata(action_yml)
    write_manifest(release, root)
    replacement = f"{release.repository}@{release.major_tag}"
    for relative in MANAGED_TEXT_PATHS:
        path = root / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        text = ACTION_REF_RE.sub(replacement, text)
        text = _replace_status_versions(text, release.tag)
        text = _replace_action_release_env(text, release)
        path.write_text(text, encoding="utf-8")
    if managed_docs_bundle is not None:
        write_managed_docs_snapshot(root, release, managed_docs_bundle)


def _iter_text_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in SKIPPED_DIRS for part in relative.parts):
            continue
        if relative == TEMPLATE_MANAGED_DOCS_PATH or TEMPLATE_MANAGED_DOCS_PATH in relative.parents:
            continue
        if path.is_file():
            files.append(path)
    return sorted(files)


def _read_text_if_possible(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def verify_release(
    root: Path,
    release: ActionRelease,
    action_yml: str,
    *,
    managed_docs_bundle: dict[str, str] | None = None,
) -> None:
    validate_release(release)
    validate_action_metadata(action_yml)
    expected_ref = f"{release.repository}@{release.major_tag}"
    stale: list[str] = []
    for path in _iter_text_files(root):
        text = _read_text_if_possible(path)
        if not text:
            continue
        for action_ref_match in ACTION_REF_RE.finditer(text):
            if action_ref_match.group(0) != expected_ref:
                stale.append(f"{path.relative_to(root)}: {action_ref_match.group(0)}")
        for line_number, line in enumerate(text.splitlines(), start=1):
            match = STATUS_LINE_RE.match(line)
            if match and release.tag not in line:
                stale.append(f"{path.relative_to(root)}:{line_number}: {line}")
            ref_match = ACTION_REF_ENV_RE.match(line)
            if ref_match and release.tag not in line:
                stale.append(f"{path.relative_to(root)}:{line_number}: {line}")
            sha_match = ACTION_SHA_ENV_RE.match(line)
            if sha_match and release.target_commitish not in line:
                stale.append(f"{path.relative_to(root)}:{line_number}: {line}")
    if stale:
        formatted = "\n".join(f"  - {entry}" for entry in stale)
        raise ActionReleaseError(f"Stale action release references found:\n{formatted}")
    if managed_docs_bundle is not None:
        verify_managed_docs_snapshot(root, release, managed_docs_bundle)


def _payload_release(path: Path) -> ActionRelease:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ActionReleaseError(f"{path} must contain a JSON object")
    release = ActionRelease(
        repository=ACTION_REPOSITORY,
        tag=str(payload.get("tag_name") or payload.get("tag") or ""),
        target_commitish=str(payload.get("target_commitish") or ""),
        release_url=str(payload.get("html_url") or payload.get("release_url") or ""),
        published_at=str(payload.get("published_at") or ""),
    )
    validate_release(release)
    return release


def _load_action_yml(path: Path | None, release: ActionRelease) -> str:
    if path is not None:
        return path.read_text(encoding="utf-8")
    return fetch_action_yml(release)


def _sync(args: argparse.Namespace) -> None:
    tag = args.tag or args.action_tag
    if not tag:
        raise ActionReleaseError("sync requires --tag or ACTION_TAG")
    release = _payload_release(args.release_json) if args.release_json else fetch_release(args.repository, tag)
    if release.tag != tag:
        raise ActionReleaseError(f"Release payload tag {release.tag!r} did not match {tag!r}")
    if args.expected_target_commitish and release.target_commitish != args.expected_target_commitish:
        raise ActionReleaseError(
            "Release target did not match dispatch payload: "
            + f"{release.target_commitish} != {args.expected_target_commitish}"
        )
    if args.expected_release_url and release.release_url != args.expected_release_url:
        raise ActionReleaseError(
            f"Release URL did not match dispatch payload: {release.release_url} != {args.expected_release_url}"
        )
    action_yml = _load_action_yml(args.action_yml, release)
    managed_docs_bundle = fetch_managed_docs_bundle(release)
    sync_release(
        args.root,
        release,
        action_yml,
        managed_docs_bundle=managed_docs_bundle,
    )
    verify_release(
        args.root,
        release,
        action_yml,
        managed_docs_bundle=managed_docs_bundle,
    )
    print(f"Synchronized {release.repository}@{release.tag}")


def _verify(args: argparse.Namespace) -> None:
    release = load_manifest(args.root)
    action_yml = _load_action_yml(args.action_yml, release)
    managed_docs_bundle = fetch_managed_docs_bundle(release)
    verify_release(
        args.root,
        release,
        action_yml,
        managed_docs_bundle=managed_docs_bundle,
    )
    print(f"Verified {release.repository}@{release.tag}")


def _print_tag(args: argparse.Namespace) -> None:
    print(load_manifest(args.root).tag)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync = subparsers.add_parser("sync", help="Update managed refs to an action release")
    sync.add_argument("--tag")
    sync.add_argument("--repository", default=ACTION_REPOSITORY)
    sync.add_argument("--release-json", type=Path)
    sync.add_argument("--action-yml", type=Path)
    sync.add_argument("--expected-target-commitish", default="")
    sync.add_argument("--expected-release-url", default="")
    sync.set_defaults(func=_sync, action_tag="")

    verify = subparsers.add_parser("verify", help="Verify managed refs match the manifest")
    verify.add_argument("--action-yml", type=Path)
    verify.set_defaults(func=_verify)

    print_tag = subparsers.add_parser("print-tag", help="Print the manifest action tag")
    print_tag.set_defaults(func=_print_tag)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "sync":
        args.action_tag = ""
        if not args.tag:
            args.action_tag = os.environ.get("ACTION_TAG", "")
    try:
        args.func(args)
    except ActionReleaseError as exc:
        print(f"Action release sync error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
