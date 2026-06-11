"""Publish a generated output tree to a repository branch."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]


class PublishError(RuntimeError):
    """Raised when a generated repository cannot be published."""


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def _output(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(
        args,
        cwd=cwd,
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def _git_value(*args: str) -> str:
    try:
        return _output(["git", *args], ROOT)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _output_files(output_dir: Path) -> list[str]:
    return sorted(
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file()
    )


def _remote_url(remote: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "remote", "get-url", remote],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError as exc:
        if "/" in _remote_repo_path(remote):
            return remote
        raise PublishError(f"Unknown git remote or repository URL: {remote}") from exc


def _remote_repo_path(remote_url: str) -> str:
    parsed = urlparse(remote_url)
    if parsed.scheme:
        path = parsed.path
    elif ":" in remote_url and not remote_url.startswith("/"):
        path = remote_url.split(":", 1)[1]
    else:
        path = remote_url

    path = path.strip().rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    if parts:
        return parts[-1]
    return ""


def _assert_expected_repo(remote_url: str, expected_repo: str) -> None:
    actual = _remote_repo_path(remote_url)
    expected = expected_repo.removesuffix(".git").strip("/")
    if "/" in expected:
        matched = actual == expected
    else:
        matched = actual == expected or actual.endswith(f"/{expected}")
    if not matched:
        raise PublishError(
            f"Remote safety check failed: expected {expected_repo}, got {actual or remote_url}"
        )


def _commit_message(message: str, source_commit: str) -> str:
    if not source_commit:
        return message
    return f"{message}\n\nSource-Commit: {source_commit}"


def publish(
    output_dir: Path,
    remote: str,
    branch: str,
    message: str,
    *,
    push: bool,
    expected_repo: str | None = None,
) -> None:
    output_dir = output_dir.resolve()
    if not output_dir.exists():
        raise PublishError(f"Generated output does not exist: {output_dir}")
    files = _output_files(output_dir)
    if not files:
        raise PublishError(f"Generated output is empty: {output_dir}")

    remote_url = _remote_url(remote)
    if expected_repo:
        _assert_expected_repo(remote_url, expected_repo)
    source_commit = _git_value("rev-parse", "HEAD")
    print(f"Preparing {len(files)} files from {output_dir}")
    print(f"Target: {remote_url} {branch}")
    if source_commit:
        print(f"Source commit: {source_commit}")

    if not push:
        print("Dry run only. Re-run with --push to publish.")
        return

    with tempfile.TemporaryDirectory(prefix="generated-repo-") as tmp:
        worktree = Path(tmp) / "repo"
        shutil.copytree(output_dir, worktree)
        _run(["git", "init", "-b", branch], worktree)
        _run(["git", "config", "user.name", "reponomics-dashboard[bot]"], worktree)
        _run(
            [
                "git",
                "config",
                "user.email",
                "286571062+reponomics-dashboard[bot]@users.noreply.github.com",
            ],
            worktree,
        )
        _run(["git", "add", "-A"], worktree)
        _run(["git", "commit", "-m", _commit_message(message, source_commit)], worktree)
        _run(["git", "remote", "add", "target", remote_url], worktree)
        remote_ref = f"refs/heads/{branch}"
        lease_ref = f"refs/remotes/target/{branch}"
        remote_oid = _output(["git", "ls-remote", "--heads", "target", branch], worktree)
        if remote_oid:
            expected_oid = remote_oid.split()[0]
            _run(["git", "fetch", "target", f"{remote_ref}:{lease_ref}"], worktree)
            lease = f"--force-with-lease={remote_ref}:{expected_oid}"
        else:
            lease = f"--force-with-lease={remote_ref}:"
        _run(["git", "push", lease, "target", f"HEAD:{remote_ref}"], worktree)

    print(f"Published {output_dir} to {remote}/{branch}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--message", default="chore: publish generated repository")
    parser.add_argument(
        "--expected-repo",
        help="Reject the publish if the target remote does not resolve to this repository name.",
    )
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    publish(
        args.output,
        args.remote,
        args.branch,
        args.message,
        push=args.push,
        expected_repo=args.expected_repo,
    )


if __name__ == "__main__":
    try:
        main()
    except PublishError as exc:
        print(f"Publish error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
