"""Guarded seed helper for the plain-history staging smoke repo."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.repo_paths import find_repo_root
from scripts.staging_smoke.preflight import DEFAULT_PLAIN_HISTORY, DEFAULT_TEMPLATE_STAGING


ROOT = find_repo_root(Path(__file__))


class SeedHistoryError(RuntimeError):
    """Raised when plain-history seed cannot complete safely."""


def _run(args: list[str], *, cwd: Path, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode and not allow_failure:
        detail = result.stderr.strip() or result.stdout.strip()
        raise SeedHistoryError(f"{' '.join(args)} failed: {detail}")
    return result


def _repo_url(repo: str) -> str:
    return f"https://github.com/{repo}.git"


def _default_branch(repo: str) -> str | None:
    result = _run(
        ["gh", "repo", "view", repo, "--json", "defaultBranchRef"],
        cwd=ROOT,
        allow_failure=True,
    )
    if result.returncode:
        raise SeedHistoryError(f"Target repo is not accessible: {repo}")
    payload = json.loads(result.stdout)
    branch = payload.get("defaultBranchRef") or {}
    if isinstance(branch, dict):
        name = branch.get("name")
        return str(name) if name else None
    return None


def build_seed_tree(template_repo: str, work_dir: Path) -> Path:
    template_dir = work_dir / "template"
    _run(["gh", "repo", "clone", template_repo, str(template_dir), "--", "--depth=1"], cwd=ROOT)
    shutil.rmtree(template_dir / ".git")
    _run(["git", "init", "-b", "main"], cwd=template_dir)
    _run(["git", "add", "-A"], cwd=template_dir)
    _run(["git", "commit", "-m", "chore: seed plain history staging template"], cwd=template_dir)
    return template_dir


def seed_plain_history(args: argparse.Namespace) -> None:
    if args.execute and args.confirm_target != args.plain_history_repo:
        raise SeedHistoryError("Refusing to push: --confirm-target must exactly match --plain-history-repo.")

    branch = _default_branch(args.plain_history_repo)
    if branch == "main":
        print(f"Plain-history repo already has main; preserving existing history: {args.plain_history_repo}")
        return
    if branch is not None:
        raise SeedHistoryError(
            f"Plain-history repo already has default branch {branch!r}; refusing to seed."
        )

    with tempfile.TemporaryDirectory(prefix="reponomics-staging-seed-") as raw_tmp:
        work_dir = Path(raw_tmp)
        template_dir = build_seed_tree(args.template_staging_repo, work_dir)
        commit = _run(["git", "rev-parse", "HEAD"], cwd=template_dir).stdout.strip()
        print(f"Prepared plain-history seed tree at commit {commit}.")
        print(f"Source template repo: {args.template_staging_repo}")
        print(f"Target plain-history repo: {args.plain_history_repo}")
        if not args.execute:
            print("Dry run: no push performed.")
            print(
                " ".join(
                    [
                        "Re-run with --execute --confirm-target",
                        args.plain_history_repo,
                        "to seed this empty repo without force-push.",
                    ]
                )
            )
            return

        _run(["git", "remote", "add", "origin", _repo_url(args.plain_history_repo)], cwd=template_dir)
        _run(["git", "push", "origin", "main"], cwd=template_dir)
        print(f"Seeded plain-history repo without force-push: {args.plain_history_repo}.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-staging-repo", default=DEFAULT_TEMPLATE_STAGING)
    parser.add_argument("--plain-history-repo", default=DEFAULT_PLAIN_HISTORY)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-target", default="")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    seed_plain_history(args)


if __name__ == "__main__":
    try:
        main()
    except SeedHistoryError as exc:
        print(f"Plain-history seed error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
