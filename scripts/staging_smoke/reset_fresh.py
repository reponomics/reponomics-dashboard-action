"""Guarded reset helper for the encrypted-fresh staging smoke repo."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.repo_paths import find_repo_root
from scripts.staging_smoke.preflight import DEFAULT_ENCRYPTED_FRESH, DEFAULT_TEMPLATE_STAGING


ROOT = find_repo_root(Path(__file__))


class ResetFreshError(RuntimeError):
    """Raised when encrypted-fresh reset cannot complete."""


def _run(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ResetFreshError(f"{' '.join(args)} failed: {detail}")
    return result


def _repo_url(repo: str) -> str:
    return f"https://github.com/{repo}.git"


def _configure_git_author(repo_dir: Path) -> None:
    _run(["git", "config", "user.name", "Reponomics Staging Smoke"], cwd=repo_dir)
    _run(["git", "config", "user.email", "reponomics-staging-smoke@example.invalid"], cwd=repo_dir)


def build_fresh_tree(template_repo: str, work_dir: Path) -> Path:
    template_dir = work_dir / "template"
    _run(["gh", "repo", "clone", template_repo, str(template_dir), "--", "--depth=1"], cwd=ROOT)
    shutil.rmtree(template_dir / ".git")
    _run(["git", "init", "-b", "main"], cwd=template_dir)
    _configure_git_author(template_dir)
    _run(["git", "add", "-A"], cwd=template_dir)
    _run(["git", "commit", "-m", "chore: reset encrypted fresh staging template"], cwd=template_dir)
    return template_dir


def reset_fresh(args: argparse.Namespace) -> None:
    if args.execute and args.confirm_target != args.encrypted_fresh_repo:
        raise ResetFreshError(
            "Refusing to push: --confirm-target must exactly match --encrypted-fresh-repo."
        )

    with tempfile.TemporaryDirectory(prefix="reponomics-staging-reset-") as raw_tmp:
        work_dir = Path(raw_tmp)
        template_dir = build_fresh_tree(args.template_staging_repo, work_dir)
        commit = _run(["git", "rev-parse", "HEAD"], cwd=template_dir).stdout.strip()
        print(f"Prepared fresh encrypted staging tree at commit {commit}.")
        print(f"Source template repo: {args.template_staging_repo}")
        print(f"Target encrypted fresh repo: {args.encrypted_fresh_repo}")
        if not args.execute:
            print("Dry run: no force-push performed.")
            print(
                " ".join(
                    [
                        "Re-run with --execute --confirm-target",
                        args.encrypted_fresh_repo,
                        "to force-push this fresh root history.",
                    ]
                )
            )
            return

        _run(["git", "remote", "add", "origin", _repo_url(args.encrypted_fresh_repo)], cwd=template_dir)
        _run(["git", "push", "--force", "origin", "main"], cwd=template_dir)
        print(f"Force-pushed fresh root history to {args.encrypted_fresh_repo}.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-staging-repo", default=DEFAULT_TEMPLATE_STAGING)
    parser.add_argument("--encrypted-fresh-repo", default=DEFAULT_ENCRYPTED_FRESH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-target", default="")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    reset_fresh(args)


if __name__ == "__main__":
    try:
        main()
    except ResetFreshError as exc:
        print(f"Encrypted-fresh reset error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
