"""Publish the generated public demo repository."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

try:
    from scripts.repo_paths import find_repo_root
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_paths import find_repo_root  # type: ignore[import-not-found,no-redef]


ROOT = find_repo_root(Path(__file__))
DEMO_PROVENANCE_PATH = Path(".reponomics/demo-provenance.json")


class DemoPublishError(RuntimeError):
    """Raised when the demo repository cannot be published."""


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def _output(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()


def _git_value(*args: str) -> str:
    try:
        return _output(["git", *args], ROOT)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


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
        raise DemoPublishError(f"Unknown git remote or repository URL: {remote}") from exc


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
    return parts[-1] if parts else ""


def _display_remote_url(remote_url: str) -> str:
    parsed = urlparse(remote_url)
    if parsed.scheme and parsed.hostname and "@" in parsed.netloc:
        host = parsed.hostname
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        return parsed._replace(netloc=host).geturl()
    return remote_url


def _assert_expected_repo(remote_url: str, expected_repo: str) -> None:
    actual = _remote_repo_path(remote_url)
    expected = expected_repo.removesuffix(".git").strip("/")
    if actual != expected:
        raise DemoPublishError(
            f"Remote safety check failed: expected {expected_repo}, got {actual or remote_url}"
        )


def _output_files(output_dir: Path) -> list[str]:
    return sorted(
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file()
    )


def _assert_publish_tree_shape(output_dir: Path) -> None:
    for relative in ("data", "dist", ".dashboard-data-artifact"):
        if (output_dir / relative).exists():
            raise DemoPublishError(f"Generated demo publish tree must not include {relative}/")


def _git_ls_files(cwd: Path) -> list[str]:
    raw = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=cwd,
        stderr=subprocess.DEVNULL,
    )
    return sorted(item.decode("utf-8") for item in raw.split(b"\0") if item)


def _staged_files_after_git_add(output_dir: Path, branch: str) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="generated-demo-stage-check-") as tmp:
        worktree = Path(tmp) / "repo"
        shutil.copytree(output_dir, worktree)
        _run(["git", "init", "-b", branch], worktree)
        _run(["git", "add", "-A"], worktree)
        return _git_ls_files(worktree)


def _assert_git_add_stages_publish_tree(output_dir: Path, branch: str, expected_files: list[str]) -> None:
    staged_files = _staged_files_after_git_add(output_dir, branch)
    if staged_files == expected_files:
        return
    missing = sorted(set(expected_files) - set(staged_files))
    unexpected = sorted(set(staged_files) - set(expected_files))
    details = []
    if missing:
        details.append("missing from git add -A: " + ", ".join(missing[:10]))
    if unexpected:
        details.append("unexpectedly staged: " + ", ".join(unexpected[:10]))
    if len(missing) > 10:
        details.append(f"{len(missing) - 10} additional missing file(s)")
    if len(unexpected) > 10:
        details.append(f"{len(unexpected) - 10} additional unexpected file(s)")
    raise DemoPublishError(
        "Generated demo publish tree does not match files staged by git add -A: "
        + "; ".join(details)
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
    expected_repo: str,
) -> None:
    output_dir = output_dir.resolve()
    if not output_dir.exists():
        raise DemoPublishError(f"Generated demo output does not exist: {output_dir}")
    if not (output_dir / DEMO_PROVENANCE_PATH).is_file():
        raise DemoPublishError(f"Generated demo output is missing {DEMO_PROVENANCE_PATH}")
    _assert_publish_tree_shape(output_dir)
    files = _output_files(output_dir)
    if not files:
        raise DemoPublishError(f"Generated demo output is empty: {output_dir}")
    _assert_git_add_stages_publish_tree(output_dir, branch, files)
    remote_url = _remote_url(remote)
    _assert_expected_repo(remote_url, expected_repo)
    source_commit = _git_value("rev-parse", "HEAD")
    display_remote_url = _display_remote_url(remote_url)
    print(f"Preparing {len(files)} demo files from {output_dir}")
    print(f"Target: {display_remote_url} {branch}")
    if source_commit:
        print(f"Source commit: {source_commit}")
    if not push:
        print("Dry run only. Re-run with --push to publish.")
        return

    with tempfile.TemporaryDirectory(prefix="generated-demo-repo-") as tmp:
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
        _run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "commit",
                "-m",
                _commit_message(message, source_commit),
            ],
            worktree,
        )
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
    print(f"Published {output_dir} to {display_remote_url}/{branch}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--expected-repo", default="reponomics/reponomics-dashboard-demo")
    parser.add_argument("--message", default="chore: publish generated demo")
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
    except DemoPublishError as exc:
        print(f"Demo publish error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
