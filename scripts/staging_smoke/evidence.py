"""Read-only evidence checks for completed staging smoke runs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.repo_paths import find_repo_root
from scripts.staging_smoke.preflight import DEFAULT_ENCRYPTED_FRESH, DEFAULT_PLAIN_HISTORY


ROOT = find_repo_root(Path(__file__))

COMMON_REQUIRED_FILES = (
    ".reponomics/setup-complete",
    "config.yaml",
    "docs/reponomics/.manifest.json",
    "README.md",
)

ARTIFACT_NAMES = {"dashboard-data", "html-dashboard-plaintext", "html-dashboard-encrypted"}


@dataclass(frozen=True)
class Evidence:
    status: str
    message: str


class EvidenceError(RuntimeError):
    """Raised when a required evidence command cannot be completed."""


def _delay_seconds() -> float:
    raw = os.environ.get("STAGING_SMOKE_GH_DELAY_SECONDS", "1")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


GH_DELAY_SECONDS = _delay_seconds()


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
        raise EvidenceError(f"{command} failed: {detail}")
    return result


def _json(args: list[str], *, allow_failure: bool = False) -> Any | None:
    result = _run(args, allow_failure=allow_failure)
    if result.returncode and allow_failure:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        command = " ".join(args)
        raise EvidenceError(f"{command} did not return valid JSON") from exc


def _ok(message: str) -> Evidence:
    return Evidence("ok", message)


def _warn(message: str) -> Evidence:
    return Evidence("warn", message)


def _fail(message: str) -> Evidence:
    return Evidence("fail", message)


def _check(condition: bool, ok: str, fail: str) -> Evidence:
    if condition:
        return _ok(ok)
    return _fail(fail)


def _repo_payload(repo: str) -> dict[str, Any] | None:
    payload = _json(
        [
            "gh",
            "repo",
            "view",
            repo,
            "--json",
            "nameWithOwner,isPrivate,defaultBranchRef,url",
        ],
        allow_failure=True,
    )
    return payload if isinstance(payload, dict) else None


def _content_exists(repo: str, path: str) -> bool:
    result = _run(
        ["gh", "api", f"repos/{repo}/contents/{path}", "-f", "ref=main"],
        allow_failure=True,
    )
    return result.returncode == 0


def _artifact_payload(repo: str) -> dict[str, Any]:
    payload = _json(["gh", "api", f"repos/{repo}/actions/artifacts?per_page=100"], allow_failure=True)
    return payload if isinstance(payload, dict) else {}


def _artifact_names(repo: str) -> set[str]:
    payload = _artifact_payload(repo)
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return set()
    names = {
        str(item.get("name"))
        for item in artifacts
        if isinstance(item, dict) and item.get("name") in ARTIFACT_NAMES
    }
    return names


def _recent_runs(repo: str, workflow: str) -> list[dict[str, Any]]:
    payload = _json(
        [
            "gh",
            "run",
            "list",
            "--repo",
            repo,
            "--workflow",
            workflow,
            "--branch",
            "main",
            "--limit",
            "5",
            "--json",
            "databaseId,status,conclusion,createdAt,url",
        ],
        allow_failure=True,
    )
    return payload if isinstance(payload, list) else []


def _latest_success(repo: str, workflow: str) -> dict[str, Any] | None:
    for run in _recent_runs(repo, workflow):
        if run.get("status") == "completed" and run.get("conclusion") == "success":
            return run
    return None


def _pages_payload(repo: str) -> dict[str, Any] | None:
    payload = _json(["gh", "api", f"repos/{repo}/pages"], allow_failure=True)
    return payload if isinstance(payload, dict) else None


def _repo_evidence(repo: str, *, label: str) -> tuple[list[Evidence], bool]:
    payload = _repo_payload(repo)
    if payload is None:
        return [_fail(f"{label}: repository is not accessible: {repo}")], False

    default_branch = payload.get("defaultBranchRef") or {}
    return (
        [
            _ok(f"{label}: repository is accessible: {payload.get('nameWithOwner')}"),
            _check(
                bool(payload.get("isPrivate")),
                f"{label}: repository is private",
                f"{label}: repository must be private for this staging smoke profile",
            ),
            _check(
                default_branch.get("name") == "main",
                f"{label}: default branch is main",
                f"{label}: expected default branch main, got {default_branch.get('name')!r}",
            ),
        ],
        True,
    )


def _file_evidence(repo: str, *, label: str) -> list[Evidence]:
    return [
        _check(
            _content_exists(repo, path),
            f"{label}: required file exists: {path}",
            f"{label}: missing required file on main: {path}",
        )
        for path in COMMON_REQUIRED_FILES
    ]


def _artifact_evidence(repo: str, *, label: str, expected: set[str]) -> list[Evidence]:
    names = _artifact_names(repo)
    checks = [
        _check(
            artifact in names,
            f"{label}: artifact exists: {artifact}",
            f"{label}: missing artifact: {artifact}",
        )
        for artifact in sorted(expected)
    ]
    unexpected = names - expected
    for artifact in sorted(unexpected):
        checks.append(_warn(f"{label}: non-required dashboard artifact also exists: {artifact}"))
    return checks


def _workflow_evidence(repo: str, *, label: str, workflows: tuple[str, ...]) -> list[Evidence]:
    checks: list[Evidence] = []
    for workflow in workflows:
        run = _latest_success(repo, workflow)
        checks.append(
            _check(
                run is not None,
                f"{label}: latest recent success found for {workflow}",
                f"{label}: no recent successful main-branch run found for {workflow}",
            )
        )
        if run is not None:
            checks.append(_ok(f"{label}: {workflow} success URL: {run.get('url')}"))
    return checks


def _encrypted_pages_evidence(repo: str) -> list[Evidence]:
    payload = _pages_payload(repo)
    if payload is None:
        return [_fail("encrypted fresh: Pages configuration is not accessible")]
    status = payload.get("status")
    source = payload.get("source")
    if isinstance(source, dict):
        source_kind = source.get("branch") or source.get("path")
    else:
        source_kind = source
    return [
        _ok(f"encrypted fresh: Pages URL: {payload.get('html_url')}"),
        _check(
            status in {"built", "building", None},
            f"encrypted fresh: Pages status is acceptable: {status!r}",
            f"encrypted fresh: Pages status is unexpected: {status!r}",
        ),
        _ok(f"encrypted fresh: Pages source payload: {source_kind!r}"),
    ]


def _plain_pages_evidence(repo: str) -> list[Evidence]:
    payload = _pages_payload(repo)
    if payload is None:
        return [_ok("plain history: Pages configuration is absent or inaccessible as expected")]
    return [_fail(f"plain history: Pages configuration must be absent: {payload.get('html_url')}")]


def collect_evidence(args: argparse.Namespace) -> list[Evidence]:
    checks: list[Evidence] = []
    encrypted_repo_checks, encrypted_accessible = _repo_evidence(
        args.encrypted_fresh_repo,
        label="encrypted fresh",
    )
    checks.extend(encrypted_repo_checks)
    if encrypted_accessible:
        checks.extend(_file_evidence(args.encrypted_fresh_repo, label="encrypted fresh"))
        checks.extend(
            _artifact_evidence(
                args.encrypted_fresh_repo,
                label="encrypted fresh",
                expected={"dashboard-data"},
            )
        )
        checks.extend(
            _workflow_evidence(
                args.encrypted_fresh_repo,
                label="encrypted fresh",
                workflows=("setup.yml", "collect-and-publish.yml", "rotate-key.yml", "doctor.yml"),
            )
        )
        checks.extend(_encrypted_pages_evidence(args.encrypted_fresh_repo))

    plain_repo_checks, plain_accessible = _repo_evidence(
        args.plain_history_repo,
        label="plain history",
    )
    checks.extend(plain_repo_checks)
    if plain_accessible:
        checks.extend(_file_evidence(args.plain_history_repo, label="plain history"))
        checks.extend(
            _artifact_evidence(
                args.plain_history_repo,
                label="plain history",
                expected={"dashboard-data", "html-dashboard-plaintext"},
            )
        )
        checks.extend(
            _workflow_evidence(
                args.plain_history_repo,
                label="plain history",
                workflows=("setup.yml", "collect-and-publish.yml", "doctor.yml"),
            )
        )
        checks.extend(_plain_pages_evidence(args.plain_history_repo))
    return checks


def print_evidence(checks: list[Evidence]) -> int:
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encrypted-fresh-repo", default=DEFAULT_ENCRYPTED_FRESH)
    parser.add_argument("--plain-history-repo", default=DEFAULT_PLAIN_HISTORY)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    failures = print_evidence(collect_evidence(args))
    if failures:
        print(f"\nEvidence check failed with {failures} required issue(s).", file=sys.stderr)
        raise SystemExit(1)
    print("\nEvidence check passed.")


if __name__ == "__main__":
    try:
        main()
    except EvidenceError as exc:
        print(f"Evidence error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
