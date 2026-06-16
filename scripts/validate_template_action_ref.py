"""Validate that the public template action ref is on the compatible action line."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

try:
    from scripts.repo_paths import find_repo_root
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_paths import find_repo_root  # type: ignore[import-not-found,no-redef]


ROOT = find_repo_root(Path(__file__))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import template_contract  # noqa: E402


SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
CORE_VERSION_RE = re.compile(
    r'^VERSION\s*=\s*["\'](?P<version>(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*))["\']',
    re.MULTILINE,
)


class TemplateActionRefError(RuntimeError):
    """Raised when the public template action ref cannot satisfy the contract."""


@dataclass(frozen=True)
class ResolvedActionRef:
    ref: str
    sha: str
    remote_ref: str


def validate_public_action_ref(
    *,
    root: Path = ROOT,
    resolver: Callable[
        [template_contract.TemplateContract],
        ResolvedActionRef,
    ] | None = None,
    version_reader: Callable[
        [template_contract.TemplateContract, ResolvedActionRef],
        str,
    ] | None = None,
) -> ResolvedActionRef:
    resolver = resolver or resolve_public_action_ref
    version_reader = version_reader or read_public_action_version
    contract = template_contract.load_contract(root)
    resolved = resolver(contract)
    action_version = version_reader(contract, resolved)
    _validate_action_version(contract, action_version, resolved)
    return resolved


def resolve_public_action_ref(
    contract: template_contract.TemplateContract,
) -> ResolvedActionRef:
    remote_url = _github_repo_url(contract.action_repository)
    default_ref = contract.default_action_ref
    output = _git_output(
        [
            "git",
            "ls-remote",
            remote_url,
            f"refs/tags/{default_ref}^{{}}",
            f"refs/tags/{default_ref}",
            f"refs/heads/{default_ref}",
            default_ref,
        ],
        cwd=ROOT,
    )
    matches = _parse_ls_remote(output)
    for remote_ref in (
        f"refs/tags/{default_ref}^{{}}",
        f"refs/tags/{default_ref}",
        f"refs/heads/{default_ref}",
        default_ref,
    ):
        if remote_ref in matches:
            return ResolvedActionRef(default_ref, matches[remote_ref], remote_ref)
    raise TemplateActionRefError(
        f"Public default action ref {contract.action_repository}@{default_ref} was not found"
    )


def read_public_action_version(
    contract: template_contract.TemplateContract,
    resolved: ResolvedActionRef,
) -> str:
    pyproject_text = _read_remote_file(
        contract.action_repository,
        resolved.ref,
        "pyproject.toml",
    )
    core_text = _read_remote_file(
        contract.action_repository,
        resolved.ref,
        "dashboard_action/run_modules/core.py",
    )
    pyproject_version = _parse_pyproject_version(pyproject_text)
    core_version = _parse_core_version(core_text)
    if pyproject_version != core_version:
        raise TemplateActionRefError(
            (
                f"Public action ref {contract.action_repository}@{resolved.ref} has "
                + f"mismatched versions: pyproject.toml={pyproject_version}, "
                + f"core.py={core_version}"
            )
        )
    return pyproject_version


def _validate_action_version(
    contract: template_contract.TemplateContract,
    action_version: str,
    resolved: ResolvedActionRef,
) -> None:
    if not SEMVER_RE.fullmatch(action_version):
        raise TemplateActionRefError(
            f"Public action ref {contract.action_repository}@{resolved.ref} "
            + f"has unparsable version {action_version!r}"
        )
    if _major(action_version) != contract.compatible_action_major:
        raise TemplateActionRefError(
            f"Public action ref {contract.action_repository}@{resolved.ref} "
            + f"resolves to version {action_version}, which is not compatible "
            + f"with major {contract.compatible_action_major}"
        )

def _parse_ls_remote(output: str) -> dict[str, str]:
    matches: dict[str, str] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 2:
            matches[parts[1]] = parts[0]
    return matches


def _parse_pyproject_version(text: str) -> str:
    try:
        payload = tomllib.loads(text)
        version = payload["project"]["version"]
    except (KeyError, tomllib.TOMLDecodeError) as exc:
        raise TemplateActionRefError("Could not parse project.version from pyproject.toml") from exc
    if not isinstance(version, str):
        raise TemplateActionRefError("pyproject.toml project.version must be a string")
    return version


def _parse_core_version(text: str) -> str:
    match = CORE_VERSION_RE.search(text)
    if not match:
        raise TemplateActionRefError("Could not parse VERSION from dashboard_action/run_modules/core.py")
    return match.group("version")


def _read_remote_file(repository: str, ref: str, path: str) -> str:
    remote_url = _github_repo_url(repository)
    with tempfile.TemporaryDirectory(prefix="template-action-ref-") as tmp:
        worktree = Path(tmp)
        _git_output(["git", "init"], cwd=worktree)
        _git_output(["git", "remote", "add", "origin", remote_url], cwd=worktree)
        _git_output(["git", "fetch", "--depth=1", "origin", ref], cwd=worktree)
        return _git_output(["git", "show", f"FETCH_HEAD:{path}"], cwd=worktree)


def _github_repo_url(repository: str) -> str:
    return f"https://github.com/{repository}.git"


def _git_output(args: list[str], *, cwd: Path) -> str:
    try:
        return subprocess.check_output(
            args,
            cwd=cwd,
            stderr=subprocess.STDOUT,
            text=True,
        ).strip()
    except subprocess.CalledProcessError as exc:
        output = exc.output.strip()
        details = f": {output}" if output else ""
        raise TemplateActionRefError(f"Command failed: {' '.join(args)}{details}") from exc


def _version_tuple(version: str) -> tuple[int, int, int]:
    match = SEMVER_RE.fullmatch(version)
    if not match:
        raise TemplateActionRefError(f"Invalid SemVer: {version!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def _major(version: str) -> int:
    return _version_tuple(version)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Source repository root containing template-contract.yml.",
    )
    args = parser.parse_args()
    resolved = validate_public_action_ref(root=args.root)
    print(f"Validated public template action ref {resolved.ref} at {resolved.sha}")


if __name__ == "__main__":
    try:
        main()
    except TemplateActionRefError as exc:
        print(f"Template action ref validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
