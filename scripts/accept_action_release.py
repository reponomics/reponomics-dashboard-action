"""Accept a released action into the generated-template contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import yaml

try:
    from scripts.repo_paths import find_repo_root
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_paths import find_repo_root  # type: ignore[import-not-found,no-redef]


ROOT = find_repo_root(Path(__file__))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import template_contract  # noqa: E402


class AcceptActionReleaseError(RuntimeError):
    """Raised when an action release cannot be accepted into the template contract."""


def _version_tuple(version: str) -> tuple[int, int, int]:
    try:
        return template_contract._version_tuple(version)  # noqa: SLF001
    except template_contract.TemplateContractError as exc:
        raise AcceptActionReleaseError(str(exc)) from exc


def _bump_kind(previous: str, current: str) -> str:
    previous_tuple = _version_tuple(previous)
    current_tuple = _version_tuple(current)
    if current_tuple <= previous_tuple:
        raise AcceptActionReleaseError(
            f"action version {current} must be newer than accepted action {previous}"
        )
    if current_tuple[0] != previous_tuple[0]:
        return "major"
    if current_tuple[1] != previous_tuple[1]:
        return "minor"
    return "patch"


def _bump_version(version: str, kind: str) -> str:
    major, minor, patch = _version_tuple(version)
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    if kind == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise AcceptActionReleaseError(f"unsupported template bump kind: {kind}")


def _load_contract_payload(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise AcceptActionReleaseError(f"{path} must parse as a YAML object")
    return payload


def accept_action_release(
    *,
    root: Path,
    action_version: str,
    action_sha: str,
    action_tag: str | None = None,
    default_ref: str | None = None,
    template_bump: str | None = None,
) -> tuple[dict, bool]:
    contract_path = root / "template-contract.yml"
    original_text = contract_path.read_text(encoding="utf-8")
    payload = _load_contract_payload(contract_path)
    contract = template_contract.load_contract(root)

    action_major = _version_tuple(action_version)[0]
    accepted_major = _version_tuple(contract.accepted_action.version)[0]
    action_tag = action_tag or f"v{action_version}"
    default_ref = default_ref or (
        f"v{action_major}" if action_major != accepted_major else contract.default_action_ref
    )
    next_action = {
        "repository": contract.action_repository,
        "version": action_version,
        "tag": action_tag,
        "sha": action_sha,
        "default_ref": default_ref,
    }

    if next_action == {
        "repository": contract.accepted_action.repository,
        "version": contract.accepted_action.version,
        "tag": contract.accepted_action.tag,
        "sha": contract.accepted_action.sha,
        "default_ref": contract.accepted_action.default_ref,
    }:
        return payload, False

    if action_tag != f"v{action_version}":
        raise AcceptActionReleaseError("action tag must be v<action-version>")
    if not template_contract.GIT_SHA_RE.fullmatch(action_sha):
        raise AcceptActionReleaseError("action SHA must be a 40-character commit SHA")

    bump = template_bump or _bump_kind(contract.accepted_action.version, action_version)
    expected_default_ref = f"v{action_major}" if bump == "major" else contract.default_action_ref
    if default_ref != expected_default_ref:
        raise AcceptActionReleaseError(
            f"accepted default ref must be {expected_default_ref} for {bump} acceptance"
        )
    payload["template_version"] = _bump_version(contract.template_version, bump)
    if bump == "major":
        payload["compatible_action_major"] = action_major
        payload["default_action_ref"] = expected_default_ref
    payload["accepted_action"] = next_action
    if not payload.get("protected_template_refs"):
        payload["minimum_compatible_template_version"] = payload["template_version"]

    next_text = yaml.safe_dump(payload, sort_keys=False)
    contract_path.write_text(next_text, encoding="utf-8")
    try:
        template_contract.validate_local_contract(root)
    except Exception:
        contract_path.write_text(original_text, encoding="utf-8")
        raise
    return payload, True


def _write_outputs(path: Path, payload: dict, *, changed: bool) -> None:
    template_version = str(payload["template_version"])
    accepted_action = payload["accepted_action"]
    lines = [
        f"changed={str(changed).lower()}",
        f"template_version={template_version}",
        f"template_tag=reponomics-dashboard-v{template_version}",
        f"action_version={accepted_action['version']}",
        f"action_tag={accepted_action['tag']}",
        f"action_sha={accepted_action['sha']}",
    ]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _write_release_notes(path: Path, payload: dict) -> None:
    accepted_action = payload["accepted_action"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "Updated "
        + f"`{accepted_action['repository']}` to `{accepted_action['tag']}` "
        + f"(`{accepted_action['sha'][:7]}`).\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--action-version", required=True)
    parser.add_argument("--action-sha", required=True)
    parser.add_argument("--action-tag")
    parser.add_argument("--default-ref")
    parser.add_argument("--template-bump", choices=["patch", "minor", "major"])
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--release-notes", type=Path)
    args = parser.parse_args()

    payload, changed = accept_action_release(
        root=args.root,
        action_version=args.action_version,
        action_sha=args.action_sha,
        action_tag=args.action_tag,
        default_ref=args.default_ref,
        template_bump=args.template_bump,
    )
    if args.github_output:
        _write_outputs(args.github_output, payload, changed=changed)
    if args.release_notes:
        _write_release_notes(args.release_notes, payload)
    template_version = payload["template_version"]
    print(f"Accepted action {args.action_version} for template {template_version}")


if __name__ == "__main__":
    try:
        main()
    except AcceptActionReleaseError as exc:
        print(f"Action release acceptance failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
