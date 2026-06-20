"""Publish a generated output tree to a repository branch."""

from __future__ import annotations

import argparse
import json
import re
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


def _commit_message(
    message: str,
    source_commit: str,
    provenance: dict[str, object] | None = None,
) -> str:
    trailers: list[str] = []
    if source_commit:
        trailers.append(f"Source-Commit: {source_commit}")
    if provenance:
        template = provenance.get("template", {})
        payload = provenance.get("payload", {})
        action = provenance.get("action", {})
        accepted = action.get("accepted_release", {}) if isinstance(action, dict) else {}
        if isinstance(template, dict) and isinstance(template.get("version"), str):
            trailers.append(f"Template-Version: {template['version']}")
        if isinstance(payload, dict) and isinstance(payload.get("digest"), str):
            trailers.append(f"Payload-Digest: {payload['digest']}")
        if isinstance(accepted, dict):
            tag = accepted.get("tag")
            sha = accepted.get("sha")
            if isinstance(tag, str) and isinstance(sha, str):
                trailers.append(f"Accepted-Action: {tag} ({sha})")
    if not trailers:
        return message
    return f"{message}\n\n" + "\n".join(trailers)


def _remote_tag_commit(worktree: Path, tag: str) -> str:
    result = subprocess.run(
        [
            "git",
            "ls-remote",
            "--tags",
            "target",
            f"refs/tags/{tag}",
            f"refs/tags/{tag}^{{}}",
        ],
        cwd=worktree,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "couldn't find remote ref" in stderr and f"refs/tags/{tag}" in stderr:
            return ""
        detail = f": {stderr}" if stderr else ""
        raise PublishError(f"git ls-remote failed for release tag {tag}{detail}")

    output = result.stdout.strip()
    peeled = ""
    direct = ""
    for line in output.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        oid, ref = parts
        if ref == f"refs/tags/{tag}^{{}}":
            peeled = oid
        elif ref == f"refs/tags/{tag}":
            direct = oid
    return peeled or direct


def _write_github_outputs(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def _write_publish_outputs(
    path: Path,
    *,
    published_commit: str,
    payload_digest: str,
    source_commit: str,
    target_branch: str,
    target_repo: str,
) -> None:
    _write_github_outputs(
        path,
        {
            "published_commit": published_commit,
            "payload_digest": payload_digest,
            "source_commit": source_commit,
            "target_branch": target_branch,
            "target_repo": target_repo,
        },
    )


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


def _verify_output_publishable(output_dir: Path, branch: str) -> None:
    with tempfile.TemporaryDirectory(prefix="generated-repo-check-") as tmp:
        worktree = Path(tmp) / "repo"
        shutil.copytree(output_dir, worktree)
        _run(["git", "init", "-b", branch], worktree)
        _run(["git", "add", "-A"], worktree)
        _verify_payload_tracked(worktree)


def _verify_published_ref(output_dir: Path, remote_url: str, ref: str) -> tuple[str, str]:
    expected_provenance = template_provenance.verify_template_provenance(output_dir)
    expected = expected_provenance["payload"]["digest"]
    with tempfile.TemporaryDirectory(prefix="published-template-") as tmp:
        worktree = Path(tmp) / "repo"
        worktree.mkdir()
        _run(["git", "init"], worktree)
        _run(["git", "remote", "add", "target", remote_url], worktree)
        _run(["git", "fetch", "--depth=1", "target", ref], worktree)
        _run(["git", "checkout", "--detach", "FETCH_HEAD"], worktree)
        commit = _output(["git", "rev-parse", "HEAD"], worktree)
        try:
            actual_provenance = template_provenance.verify_template_provenance(worktree)
            actual = actual_provenance["payload"]["digest"]
        except template_provenance.TemplateProvenanceError as exc:
            actual = template_provenance.payload_tree_digest(worktree).digest
            raise PublishError(
                f"Published template payload digest mismatch: expected {expected}, got {actual}"
            ) from exc
    if actual != expected:
        raise PublishError(
            f"Published template payload digest mismatch: expected {expected}, got {actual}"
        )
    if actual_provenance != expected_provenance:
        raise PublishError("Published template provenance mismatch")
    return actual, commit


def _verify_published_digest(output_dir: Path, remote_url: str, branch: str) -> str:
    digest, _commit = _verify_published_ref(output_dir, remote_url, branch)
    return digest


def _replace_worktree_contents(worktree: Path, output_dir: Path) -> None:
    for child in worktree.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    for child in output_dir.iterdir():
        target = worktree / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


def _has_staged_changes(worktree: Path) -> bool:
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=worktree,
        check=False,
    )
    if result.returncode == 0:
        return False
    if result.returncode == 1:
        return True
    result.check_returncode()
    return False


VERSION_RE = re.compile(r"^\d+(?:\.\d+){0,2}(?:[-+].*)?$")


def _template_version(provenance: dict[str, object]) -> str:
    template = provenance.get("template", {})
    version = template.get("version") if isinstance(template, dict) else None
    if not isinstance(version, str) or not version.strip():
        raise PublishError("Template provenance has no template version")
    return version


def _version_key(version: str) -> tuple[int, int, int, str]:
    core = version.split("-", 1)[0].split("+", 1)[0]
    if not VERSION_RE.match(version):
        raise PublishError(f"Unsupported template version for ordering: {version}")
    parts = [int(part) for part in core.split(".")]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2], version)


def _guard_target_not_newer(
    worktree: Path,
    *,
    target_branch: str,
    expected_provenance: dict[str, object],
) -> None:
    try:
        current_provenance = template_provenance.load_template_provenance(worktree)
    except template_provenance.TemplateProvenanceError as exc:
        raise PublishError(
            f"Cannot compare generated target {target_branch}: current provenance is invalid"
        ) from exc

    current_version = _template_version(current_provenance)
    expected_version = _template_version(expected_provenance)
    current_key = _version_key(current_version)
    expected_key = _version_key(expected_version)
    if current_key > expected_key:
        raise PublishError(
            f"Refusing to publish template {expected_version}: target {target_branch} "
            + f"already contains newer template {current_version}"
        )
    if current_key == expected_key and current_provenance != expected_provenance:
        raise PublishError(
            f"Refusing to republish template {expected_version}: target {target_branch} "
            + "already contains different provenance for that version"
        )


def verify_remote_ref(
    output_dir: Path,
    remote: str,
    ref: str,
    *,
    expected_repo: str | None = None,
    github_output: Path | None = None,
) -> str:
    output_dir = output_dir.resolve()
    provenance = template_provenance.verify_template_provenance(output_dir)
    remote_url = _remote_url(remote)
    if expected_repo:
        _assert_expected_repo(remote_url, expected_repo)
    digest, commit = _verify_published_ref(output_dir, remote_url, ref)
    print(f"Verified published template payload digest: {digest}")
    print(f"Verified published generated commit: {commit}")
    if github_output:
        _write_github_outputs(
            github_output,
            {
                "published_commit": commit,
                "payload_digest": provenance["payload"]["digest"],
                "target_ref": ref,
                "target_repo": expected_repo or _remote_repo_path(remote_url),
            },
        )
    return commit


def publish(
    output_dir: Path,
    remote: str,
    branch: str,
    message: str,
    *,
    push: bool,
    expected_repo: str | None = None,
    release_tag: str | None = None,
    github_output: Path | None = None,
) -> str | None:
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
    _verify_output_publishable(output_dir, branch)

    if not push:
        print("Dry run only. Re-run with --push to publish.")
        return None

    published_commit = ""
    tag_push_ref = ""
    with tempfile.TemporaryDirectory(prefix="generated-repo-") as tmp:
        worktree = Path(tmp) / "repo"
        worktree.mkdir()
        _run(["git", "init"], worktree)
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
        _run(["git", "remote", "add", "target", remote_url], worktree)
        if release_tag:
            remote_tag_oid = _remote_tag_commit(worktree, release_tag)
            if remote_tag_oid:
                try:
                    digest, tag_commit = _verify_published_ref(
                        output_dir,
                        remote_url,
                        f"refs/tags/{release_tag}",
                    )
                except PublishError as exc:
                    raise PublishError(
                        f"Generated template release tag {release_tag} does not "
                        + f"match expected output: {exc}"
                    ) from exc
                print(
                    f"Generated template release tag {release_tag} already points to "
                    + f"{tag_commit}."
                )
                print(f"Verified generated template release tag payload digest: {digest}")
                if github_output:
                    _write_publish_outputs(
                        github_output,
                        published_commit=tag_commit,
                        payload_digest=digest,
                        source_commit=source_commit,
                        target_branch=branch,
                        target_repo=expected_repo or _remote_repo_path(remote_url),
                    )
                return tag_commit

        remote_ref = f"refs/heads/{branch}"
        remote_oid = _output(["git", "ls-remote", "--heads", "target", branch], worktree)
        if remote_oid:
            _run(["git", "fetch", "target", remote_ref], worktree)
            _run(["git", "checkout", "-B", branch, "FETCH_HEAD"], worktree)
            _guard_target_not_newer(
                worktree,
                target_branch=branch,
                expected_provenance=provenance,
            )
        else:
            _run(["git", "checkout", "--orphan", branch], worktree)

        _replace_worktree_contents(worktree, output_dir)
        _run(["git", "add", "-A"], worktree)
        if _has_staged_changes(worktree):
            _run(
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "commit",
                    "-m",
                    _commit_message(message, source_commit, provenance),
                ],
                worktree,
            )
        else:
            print(f"Generated template tree already matches target {branch}.")
        published_commit = _output(["git", "rev-parse", "HEAD"], worktree)
        if release_tag:
            _run(
                ["git", "-c", "tag.gpgSign=false", "tag", release_tag, published_commit],
                worktree,
            )
            tag_push_ref = f"refs/tags/{release_tag}:refs/tags/{release_tag}"

        push_args = ["git", "push", "--atomic", "target", f"HEAD:{remote_ref}"]
        if tag_push_ref:
            push_args.append(tag_push_ref)
        _run(push_args, worktree)

    verify_ref = f"refs/tags/{release_tag}" if release_tag else branch
    digest, verified_commit = _verify_published_ref(output_dir, remote_url, verify_ref)
    print(f"Verified published template payload digest: {digest}")
    print(f"Published {output_dir} to {display_remote_url}/{branch}")
    if published_commit:
        print(f"Published generated commit: {published_commit}")
    if verified_commit != published_commit:
        raise PublishError(
            f"Published ref {verify_ref} points to {verified_commit}, not {published_commit}"
        )
    if github_output and published_commit:
        _write_publish_outputs(
            github_output,
            published_commit=published_commit,
            payload_digest=digest,
            source_commit=source_commit,
            target_branch=branch,
            target_repo=expected_repo or _remote_repo_path(remote_url),
        )
    return published_commit or None


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
    parser.add_argument(
        "--release-tag",
        help=(
            "Generated-template release tag for the publication. When set, the tag "
            + "is created or verified at the generated publication commit."
        ),
    )
    parser.add_argument(
        "--verify-ref",
        help="Verify that the target remote ref has the same generated-template payload digest.",
    )
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    if args.verify_ref:
        verify_remote_ref(
            args.output,
            args.remote,
            args.verify_ref,
            expected_repo=args.expected_repo,
            github_output=args.github_output,
        )
        return
    publish(
        args.output,
        args.remote,
        args.branch,
        args.message,
        push=args.push,
        expected_repo=args.expected_repo,
        release_tag=args.release_tag,
        github_output=args.github_output,
    )


if __name__ == "__main__":
    try:
        main()
    except PublishError as exc:
        print(f"Publish error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
