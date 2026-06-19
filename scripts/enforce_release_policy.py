"""Enforce release policy before Release Please creates a GitHub release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


MANIFEST_PATH = Path(".github/.release-please-manifest.json")
PACKAGE_NAME = "."
RELEASE_AS_RE = re.compile(r"(?im)^Release-As:\s*v?(?P<version>\d+\.\d+\.\d+)\s*$")


class ReleasePolicyError(RuntimeError):
    """Raised when a release policy gate fails."""


def _version_tuple(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3:
        raise ReleasePolicyError(f"invalid SemVer version: {version!r}")
    try:
        major, minor, patch = (int(part) for part in parts)
    except ValueError as exc:
        raise ReleasePolicyError(f"invalid SemVer version: {version!r}") from exc
    if major < 0 or minor < 0 or patch < 0:
        raise ReleasePolicyError(f"invalid SemVer version: {version!r}")
    return major, minor, patch


def _manifest_version(text: str, package_name: str) -> str:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ReleasePolicyError("release manifest must be a JSON object")
    version = payload.get(package_name)
    if not isinstance(version, str):
        raise ReleasePolicyError(
            f"release manifest does not contain package {package_name!r}"
        )
    _version_tuple(version)
    return version


def _release_as_versions(messages: str) -> list[str]:
    return [match.group("version") for match in RELEASE_AS_RE.finditer(messages)]


def enforce_major_release_policy(
    *,
    previous_version: str,
    current_version: str,
    messages: str,
) -> None:
    previous_major = _version_tuple(previous_version)[0]
    current_major = _version_tuple(current_version)[0]
    if current_major <= previous_major:
        return

    requested_versions = _release_as_versions(messages)
    if current_version in requested_versions:
        return

    requested = ", ".join(requested_versions) if requested_versions else "none"
    raise ReleasePolicyError(
        "major action releases require an explicit "
        + f"`Release-As: {current_version}` trailer; found {requested}"
    )


def _git_output(args: list[str], *, cwd: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=cwd,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip()
        detail = f": {stderr}" if stderr else ""
        raise ReleasePolicyError(f"git {' '.join(args)} failed{detail}") from exc


def _git_text_or_none(args: list[str], *, cwd: Path) -> str | None:
    try:
        return _git_output(args, cwd=cwd)
    except ReleasePolicyError:
        return None


def enforce_release_policy_from_git(
    *,
    root: Path,
    manifest_path: Path = MANIFEST_PATH,
    package_name: str = PACKAGE_NAME,
    base_ref: str = "HEAD^",
    head_ref: str = "HEAD",
) -> None:
    manifest_ref_path = manifest_path.as_posix()
    previous_manifest = _git_text_or_none(
        ["show", f"{base_ref}:{manifest_ref_path}"],
        cwd=root,
    )
    if previous_manifest is None:
        return

    current_manifest_path = root / manifest_path
    current_manifest = current_manifest_path.read_text(encoding="utf-8")
    previous_version = _manifest_version(previous_manifest, package_name)
    current_version = _manifest_version(current_manifest, package_name)
    if previous_version == current_version:
        return

    previous_tag = f"v{previous_version}"
    has_previous_tag = (
        _git_text_or_none(["rev-parse", "-q", "--verify", f"refs/tags/{previous_tag}"], cwd=root)
        is not None
    )
    if has_previous_tag:
        message_range = f"{previous_tag}..{head_ref}"
    else:
        message_range = f"{base_ref}..{head_ref}"
    messages = _git_output(["log", "--format=%B", message_range], cwd=root)
    enforce_major_release_policy(
        previous_version=previous_version,
        current_version=current_version,
        messages=messages,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--package", default=PACKAGE_NAME)
    parser.add_argument("--base-ref", default="HEAD^")
    parser.add_argument("--head-ref", default="HEAD")
    args = parser.parse_args()

    enforce_release_policy_from_git(
        root=args.root,
        manifest_path=args.manifest,
        package_name=args.package,
        base_ref=args.base_ref,
        head_ref=args.head_ref,
    )


if __name__ == "__main__":
    try:
        main()
    except ReleasePolicyError as exc:
        print(f"Release policy failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
