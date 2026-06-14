"""Preflight checks for the manual staging smoke fleet."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.repo_paths import find_repo_root


ROOT = find_repo_root(Path(__file__))

DEFAULT_OWNER = "reponomics"
DEFAULT_TEMPLATE_STAGING = "reponomics/reponomics-dashboard-staging"
DEFAULT_ENCRYPTED_FRESH = "reponomics/reponomics-dashboard-staging-private-encrypted-fresh"
DEFAULT_PLAIN_HISTORY = "reponomics/reponomics-dashboard-staging-private-plaintext-with-history"

SOURCE_REQUIRED_VARS = {"TEMPLATE_STAGING_PUBLISH_APP_CLIENT_ID"}
SOURCE_REQUIRED_SECRETS = {"TEMPLATE_STAGING_PUBLISH_APP_PRIVATE_KEY"}
PAT_REQUIRED_SECRETS = {"COLLECTION_TOKEN"}
ENCRYPTED_REQUIRED_SECRETS = {"DASHBOARD_SECRET_DO_NOT_REPLACE"}
OPTIONAL_ENCRYPTED_SECRETS = {"COMPARISON_SECRET", "DASHBOARD_NEXT_SECRET"}


def _delay_seconds() -> float:
    raw = os.environ.get("STAGING_SMOKE_GH_DELAY_SECONDS", "1")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


GH_DELAY_SECONDS = _delay_seconds()


@dataclass(frozen=True)
class RepoSpec:
    label: str
    name: str
    must_be_private: bool
    expected_workflows: tuple[str, ...] = ()


@dataclass(frozen=True)
class Check:
    status: str
    message: str


class PreflightError(RuntimeError):
    """Raised when a command needed for preflight cannot be completed."""


def _run(args: list[str], *, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if args and args[0] == "gh" and GH_DELAY_SECONDS:
        time.sleep(GH_DELAY_SECONDS)
    if result.returncode and not allow_failure:
        command = " ".join(args)
        detail = result.stderr.strip() or result.stdout.strip()
        raise PreflightError(f"{command} failed: {detail}")
    return result


def _json(args: list[str]) -> Any:
    output = _run(args).stdout
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        command = " ".join(args)
        raise PreflightError(f"{command} did not return valid JSON") from exc


def _repo_api_path(repo: str, suffix: str) -> str:
    return f"repos/{repo}/{suffix.lstrip('/')}"


def _secret_names(repo: str) -> set[str]:
    payload = _json(["gh", "api", _repo_api_path(repo, "actions/secrets")])
    return {item["name"] for item in payload.get("secrets", []) if isinstance(item, dict)}


def _variable_names(repo: str) -> set[str]:
    payload = _json(["gh", "api", _repo_api_path(repo, "actions/variables")])
    return {item["name"] for item in payload.get("variables", []) if isinstance(item, dict)}


def _workflow_exists(repo: str, path: str) -> bool:
    result = _run(
        [
            "gh",
            "api",
            "--method",
            "GET",
            _repo_api_path(repo, f"contents/{path}"),
            "-f",
            "ref=main",
        ],
        allow_failure=True,
    )
    return result.returncode == 0


def _check(condition: bool, ok: str, fail: str) -> Check:
    if condition:
        return Check("ok", ok)
    return Check("fail", fail)


def _warn(message: str) -> Check:
    return Check("warn", message)


def _ok(message: str) -> Check:
    return Check("ok", message)


def _fail(message: str) -> Check:
    return Check("fail", message)


def _repo_checks(spec: RepoSpec) -> list[Check]:
    checks: list[Check] = []
    result = _run(
        [
            "gh",
            "repo",
            "view",
            spec.name,
            "--json",
            "nameWithOwner,isPrivate,isTemplate,defaultBranchRef",
        ],
        allow_failure=True,
    )
    if result.returncode:
        checks.append(_fail(f"{spec.label}: repository is not accessible: {spec.name}"))
        return checks

    payload = json.loads(result.stdout)
    default_branch = payload.get("defaultBranchRef") or {}
    checks.append(_ok(f"{spec.label}: repository is accessible: {payload['nameWithOwner']}"))
    checks.append(
        _check(
            bool(payload.get("isPrivate")) is spec.must_be_private,
            f"{spec.label}: visibility matches expected private={spec.must_be_private}",
            f"{spec.label}: expected private={spec.must_be_private}, got private={payload.get('isPrivate')}",
        )
    )
    default_branch_name = default_branch.get("name")
    if spec.label == "template staging" and not default_branch_name:
        checks.append(_warn(f"{spec.label}: default branch is not set yet"))
    else:
        checks.append(
            _check(
                default_branch_name == "main",
                f"{spec.label}: default branch is main",
                f"{spec.label}: expected default branch main, got {default_branch_name!r}",
            )
        )
    if spec.label == "template staging" and not payload.get("isTemplate"):
        checks.append(_warn(f"{spec.label}: repository is not marked as a GitHub template"))

    for workflow in spec.expected_workflows:
        checks.append(
            _check(
                _workflow_exists(spec.name, workflow),
                f"{spec.label}: workflow exists: {workflow}",
                f"{spec.label}: workflow is missing on main: {workflow}",
            )
        )
    return checks


def _repo_accessible(repo: str) -> bool:
    result = _run(["gh", "repo", "view", repo, "--json", "nameWithOwner"], allow_failure=True)
    return result.returncode == 0


def _credential_checks(
    repo: str,
    *,
    label: str,
    collection_mode: str,
    encrypted: bool,
) -> list[Check]:
    checks: list[Check] = []
    try:
        secrets = _secret_names(repo)
    except PreflightError as exc:
        return [_fail(f"{label}: could not inspect repository secrets: {exc}")]

    required_secrets = set()
    required_secrets |= PAT_REQUIRED_SECRETS
    if encrypted:
        required_secrets |= ENCRYPTED_REQUIRED_SECRETS

    for name in sorted(required_secrets):
        checks.append(
            _check(
                name in secrets,
                f"{label}: required secret is configured: {name}",
                f"{label}: missing required secret: {name}",
            )
        )
    if encrypted:
        for name in sorted(OPTIONAL_ENCRYPTED_SECRETS):
            if name in secrets:
                checks.append(_ok(f"{label}: optional secret is configured: {name}"))
            else:
                checks.append(_warn(f"{label}: optional secret is not configured: {name}"))
    return checks


def _source_repo_checks(source_repo: str) -> list[Check]:
    checks: list[Check] = []
    try:
        secrets = _secret_names(source_repo)
        variables = _variable_names(source_repo)
    except PreflightError as exc:
        return [_fail(f"source repo: could not inspect secrets/variables: {exc}")]

    for name in sorted(SOURCE_REQUIRED_VARS):
        checks.append(
            _check(
                name in variables,
                f"source repo: required variable is configured: {name}",
                f"source repo: missing required variable: {name}",
            )
        )
    for name in sorted(SOURCE_REQUIRED_SECRETS):
        checks.append(
            _check(
                name in secrets,
                f"source repo: required secret is configured: {name}",
                f"source repo: missing required secret: {name}",
            )
        )
    return checks


def _local_checks() -> list[Check]:
    gh_path = shutil.which("gh")
    checks = [
        _check(
            gh_path is not None,
            "local: gh CLI is available",
            "local: gh CLI is not available",
        ),
        _check(
            (ROOT / "docs" / "STAGING_SMOKE.md").exists(),
            "local: staging smoke runbook exists",
            "local: missing docs/STAGING_SMOKE.md",
        ),
    ]
    if gh_path is None:
        checks.append(_fail("local: cannot inspect GitHub state without gh CLI"))
        return checks
    auth = _run(["gh", "auth", "status"], allow_failure=True)
    checks.append(
        _check(
            auth.returncode == 0,
            "local: gh auth status succeeded",
            "local: gh auth status failed",
        )
    )
    status = _run(["git", "status", "--short"], allow_failure=True)
    if status.returncode == 0 and status.stdout.strip():
        checks.append(_warn("local: source worktree has uncommitted changes"))
    elif status.returncode == 0:
        checks.append(_ok("local: source worktree is clean"))
    else:
        checks.append(_warn("local: could not inspect git status"))
    return checks


def _print_checks(checks: list[Check]) -> int:
    failures = 0
    for check in checks:
        if check.status == "ok":
            prefix = "OK"
        elif check.status == "warn":
            prefix = "WARN"
        else:
            prefix = "FAIL"
            failures += 1
        print(f"[{prefix}] {check.message}")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", default=f"{DEFAULT_OWNER}/reponomics-dashboard-action")
    parser.add_argument("--template-staging-repo", default=DEFAULT_TEMPLATE_STAGING)
    parser.add_argument("--encrypted-fresh-repo", default=DEFAULT_ENCRYPTED_FRESH)
    parser.add_argument("--plain-history-repo", default=DEFAULT_PLAIN_HISTORY)
    parser.add_argument(
        "--collection-mode",
        choices=("pat",),
        default="pat",
        help="Collection credential mode expected in consumer staging repos. Staging smoke currently supports PAT mode.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    specs = [
        RepoSpec("template staging", args.template_staging_repo, True),
        RepoSpec(
            "encrypted fresh",
            args.encrypted_fresh_repo,
            True,
            (
                ".github/workflows/setup.yml",
                ".github/workflows/collect-and-publish.yml",
                ".github/workflows/rotate-key.yml",
                ".github/workflows/doctor.yml",
            ),
        ),
        RepoSpec(
            "plain history",
            args.plain_history_repo,
            True,
            (
                ".github/workflows/setup.yml",
                ".github/workflows/collect-and-publish.yml",
                ".github/workflows/doctor.yml",
            ),
        ),
    ]

    checks: list[Check] = []
    checks.extend(_local_checks())
    checks.extend(_source_repo_checks(args.source_repo))
    for spec in specs:
        checks.extend(_repo_checks(spec))
    if _repo_accessible(args.encrypted_fresh_repo):
        checks.extend(
            _credential_checks(
                args.encrypted_fresh_repo,
                label="encrypted fresh",
                collection_mode=args.collection_mode,
                encrypted=True,
            )
        )
    else:
        checks.append(_warn("encrypted fresh: skipping credential checks until repo exists"))
    if _repo_accessible(args.plain_history_repo):
        checks.extend(
            _credential_checks(
                args.plain_history_repo,
                label="plain history",
                collection_mode=args.collection_mode,
                encrypted=False,
            )
        )
    else:
        checks.append(_warn("plain history: skipping credential checks until repo exists"))

    failures = _print_checks(checks)
    if failures:
        print(f"\nPreflight failed with {failures} required issue(s).", file=sys.stderr)
        raise SystemExit(1)
    print("\nPreflight passed.")


if __name__ == "__main__":
    try:
        main()
    except PreflightError as exc:
        print(f"Preflight error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
