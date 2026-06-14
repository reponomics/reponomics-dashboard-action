"""Guarded one-time provisioning helper for staging smoke repositories."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.repo_paths import find_repo_root
from scripts.staging_smoke.preflight import (
    DEFAULT_ENCRYPTED_FRESH,
    DEFAULT_OWNER,
    DEFAULT_PLAIN_HISTORY,
    DEFAULT_TEMPLATE_STAGING,
)


ROOT = find_repo_root(Path(__file__))
SLOW_GH = "venv/bin/python scripts/staging_smoke/slow_gh.py"


@dataclass(frozen=True)
class RepoProvisionSpec:
    label: str
    repo: str
    description: str


class ProvisionError(RuntimeError):
    """Raised when a provisioning command fails."""


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
        detail = result.stderr.strip() or result.stdout.strip()
        raise ProvisionError(f"{' '.join(args)} failed: {detail}")
    return result


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _repo_exists(repo: str) -> bool:
    result = _run(["gh", "repo", "view", repo, "--json", "nameWithOwner"], allow_failure=True)
    return result.returncode == 0


def _repo_payload(repo: str) -> dict[str, object] | None:
    result = _run(
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
    if result.returncode:
        return None
    payload = json.loads(result.stdout)
    return payload if isinstance(payload, dict) else None


def _create_command(spec: RepoProvisionSpec) -> str:
    return " ".join(
        [
            SLOW_GH,
            "repo",
            "create",
            _quote(spec.repo),
            "--private",
            "--disable-issues",
            "--disable-wiki",
            "--description",
            _quote(spec.description),
        ]
    )


def _create_args(spec: RepoProvisionSpec) -> list[str]:
    return [
        "gh",
        "repo",
        "create",
        spec.repo,
        "--private",
        "--disable-issues",
        "--disable-wiki",
        "--description",
        spec.description,
    ]


def repo_specs(args: argparse.Namespace) -> tuple[RepoProvisionSpec, ...]:
    return (
        RepoProvisionSpec(
            "template staging",
            args.template_staging_repo,
            "Private generated Reponomics dashboard template staging surface.",
        ),
        RepoProvisionSpec(
            "encrypted fresh",
            args.encrypted_fresh_repo,
            "Private disposable encrypted Reponomics dashboard smoke repository.",
        ),
        RepoProvisionSpec(
            "plain history",
            args.plain_history_repo,
            "Private durable plaintext Reponomics dashboard smoke repository.",
        ),
    )


def print_plan(args: argparse.Namespace) -> None:
    print("Dry run: no GitHub repositories will be created.\n")
    for spec in repo_specs(args):
        payload = _repo_payload(spec.repo)
        if payload is None:
            print(f"[MISSING] {spec.label}: {spec.repo}")
            print(f"  create: {_create_command(spec)}")
        else:
            branch = payload.get("defaultBranchRef") or {}
            branch_name = branch.get("name") if isinstance(branch, dict) else None
            print(f"[EXISTS] {spec.label}: {payload.get('nameWithOwner')}")
            print(f"  private: {payload.get('isPrivate')}")
            print(f"  default branch: {branch_name!r}")
    print("\nAfter repositories exist, configure source repository credentials manually:")
    print(
        " ".join(
            [
                "  gh variable set TEMPLATE_STAGING_PUBLISH_APP_CLIENT_ID",
                f"--repo {_quote(args.source_repo)}",
                "--body '<app-client-id>'",
            ]
        )
    )
    print(
        " ".join(
            [
                "  gh secret set TEMPLATE_STAGING_PUBLISH_APP_PRIVATE_KEY",
                f"--repo {_quote(args.source_repo)}",
            ]
        )
    )
    print(
        " ".join(
            [
                "\nConsumer collection/dashboard secrets are provisioned during the bootstrap smoke pass;",
                "setup.yml writes generated repository config and setup files.",
            ]
        )
    )


def execute(args: argparse.Namespace) -> None:
    for spec in repo_specs(args):
        if _repo_exists(spec.repo):
            print(f"[SKIP] {spec.label}: repository already exists: {spec.repo}")
            continue
        print(f"[CREATE] {spec.label}: {spec.repo}")
        _run(_create_args(spec))
    print("\nProvisioning pass complete. Run make staging-smoke-preflight next.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", default=f"{DEFAULT_OWNER}/reponomics-dashboard-action")
    parser.add_argument("--template-staging-repo", default=DEFAULT_TEMPLATE_STAGING)
    parser.add_argument("--encrypted-fresh-repo", default=DEFAULT_ENCRYPTED_FRESH)
    parser.add_argument("--plain-history-repo", default=DEFAULT_PLAIN_HISTORY)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Create missing private staging repositories. Secrets are still manual.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    if args.execute:
        execute(args)
    else:
        print_plan(args)


if __name__ == "__main__":
    try:
        main()
    except ProvisionError as exc:
        print(f"Provisioning error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
