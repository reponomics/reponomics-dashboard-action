"""Publish a generated output tree to a repository branch."""

from __future__ import annotations

import argparse
import json
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import template_provenance  # noqa: E402


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


def _payload_paths(root: Path) -> set[str]:
    paths: set[str] = set()
    for line in template_provenance.canonical_tree_manifest(root).splitlines():
        if not line:
            continue
        payload = json.loads(line)
        paths.add(str(payload["path"]))
    return paths


def _tracked_paths(worktree: Path) -> set[str]:
    output = _output(["git", "ls-files"], worktree)
    return {line for line in output.splitlines() if line}


def _verify_payload_tracked(worktree: Path) -> None:
    payload_paths = _payload_paths(worktree)
    tracked_paths = _tracked_paths(worktree)
    unpublished = sorted(payload_paths - tracked_paths)
    if unpublished:
        sample = "\n".join(f"  - {path}" for path in unpublished[:20])
        suffix = "\n  - ..." if len(unpublished) > 20 else ""
        raise PublishError(
            "Generated template payload contains file(s) that git will not publish:\n"
            + sample
            + suffix
        )


def _verify_published_digest(output_dir: Path, remote_url: str, branch: str) -> str:
    expected = template_provenance.verify_template_provenance(output_dir)["payload"]["digest"]
    with tempfile.TemporaryDirectory(prefix="published-template-") as tmp:
        worktree = Path(tmp) / "repo"
        worktree.mkdir()
        _run(["git", "init"], worktree)
        _run(["git", "remote", "add", "target", remote_url], worktree)
        _run(["git", "fetch", "--depth=1", "target", branch], worktree)
        _run(["git", "checkout", "--detach", "FETCH_HEAD"], worktree)
        try:
            actual = template_provenance.verify_template_provenance(worktree)["payload"]["digest"]
        except template_provenance.TemplateProvenanceError as exc:
            actual = template_provenance.payload_tree_digest(worktree).digest
            raise PublishError(
                f"Published template payload digest mismatch: expected {expected}, got {actual}"
            ) from exc
    if actual != expected:
        raise PublishError(
            f"Published template payload digest mismatch: expected {expected}, got {actual}"
        )
    return actual


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
    provenance = template_provenance.verify_template_provenance(output_dir)

    remote_url = _remote_url(remote)
    if expected_repo:
        _assert_expected_repo(remote_url, expected_repo)
    source_commit = _git_value("rev-parse", "HEAD")
    display_remote_url = _display_remote_url(remote_url)
    print(f"Preparing {len(files)} files from {output_dir}")
    print(f"Target: {display_remote_url} {branch}")
    if source_commit:
        print(f"Source commit: {source_commit}")
    print(f"Template payload digest: {provenance['payload']['digest']}")

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
        _verify_payload_tracked(worktree)
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

    digest = _verify_published_digest(output_dir, remote_url, branch)
    print(f"Verified published template payload digest: {digest}")
    print(f"Published {output_dir} to {display_remote_url}/{branch}")


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
