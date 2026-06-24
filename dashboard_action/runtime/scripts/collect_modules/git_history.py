"""Local git-history extraction for contextual repository events."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

from storage import SCHEMA_VERSION

FIELD_SEPARATOR = "\x1f"
RECORD_SEPARATOR = "\x1e"
DEFAULT_CHANGED_PATH_SAMPLE_LIMIT = 12
PULL_REQUEST_PATTERNS = (
    re.compile(r"\(#(?P<number>\d+)\)"),
    re.compile(r"\b(?:pull request|pr)\s+#(?P<number>\d+)\b", re.IGNORECASE),
)


def collect_commit_history_from_clone(
    repo: str,
    repo_path: str | Path,
    captured_at: str,
    *,
    since: str = "",
    max_commits: int = 500,
    changed_path_sample_limit: int = DEFAULT_CHANGED_PATH_SAMPLE_LIMIT,
) -> list[dict[str, Any]]:
    """Extract canonical commit rows from a local clone's current branch."""
    output = _git_log(repo_path, since=since, max_commits=max_commits)
    return [
        _commit_row(repo, chunk, captured_at, changed_path_sample_limit)
        for chunk in _record_chunks(output)
    ]


def _git_log(repo_path: str | Path, *, since: str, max_commits: int) -> str:
    args = [
        "git",
        "-C",
        str(repo_path),
        "log",
        "--first-parent",
        "--reverse",
        "--date=iso-strict",
        f"--max-count={max_commits}",
        (
            "--pretty=format:"
            + RECORD_SEPARATOR
            + "%H"
            + FIELD_SEPARATOR
            + "%P"
            + FIELD_SEPARATOR
            + "%cI"
            + FIELD_SEPARATOR
            + "%aI"
            + FIELD_SEPARATOR
            + "%an"
            + FIELD_SEPARATOR
            + "%ae"
            + FIELD_SEPARATOR
            + "%s"
            + FIELD_SEPARATOR
            + "%b"
            + FIELD_SEPARATOR
        ),
        "--numstat",
    ]
    if since:
        args.insert(5, f"--since={since}")
    result = subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _record_chunks(output: str) -> list[str]:
    return [chunk.strip("\n") for chunk in output.split(RECORD_SEPARATOR) if chunk.strip()]


def _commit_row(
    repo: str,
    chunk: str,
    captured_at: str,
    changed_path_sample_limit: int,
) -> dict[str, Any]:
    fields = chunk.split(FIELD_SEPARATOR, 8)
    if len(fields) != 9:
        raise ValueError("git log record did not match the expected contextual schema")
    (
        sha,
        parents,
        committed_at,
        authored_at,
        author_name,
        author_email,
        subject,
        body,
        stats_text,
    ) = fields
    stats = _parse_numstat(stats_text, sample_limit=changed_path_sample_limit)
    return {
        "repo": repo,
        "sha": sha,
        "parent_sha": parents.split(" ", 1)[0] if parents else "",
        "committed_at": committed_at,
        "authored_at": authored_at,
        "author_name": author_name,
        "author_email_hash": _hash_text(author_email.lower().strip()),
        "author_login": "",
        "committer_login": "",
        "message_subject": subject,
        "message_body_hash": _hash_text(body.strip()),
        "files_changed": stats["files_changed"],
        "additions": stats["additions"],
        "deletions": stats["deletions"],
        "changed_paths_sample": "|".join(stats["changed_paths_sample"]),
        "classification": _classify_commit(subject, stats["changed_paths_sample"]),
        "associated_pr_number": _associated_pr_number(subject, body),
        "source": "git-log",
        "captured_at": captured_at,
        "schema_version": SCHEMA_VERSION,
    }


def _parse_numstat(stats_text: str, *, sample_limit: int) -> dict[str, Any]:
    additions = 0
    deletions = 0
    paths: list[str] = []
    for line in stats_text.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added, deleted, path = parts[0], parts[1], parts[2]
        if added.isdigit():
            additions += int(added)
        if deleted.isdigit():
            deletions += int(deleted)
        paths.append(path)
    return {
        "files_changed": len(paths),
        "additions": additions,
        "deletions": deletions,
        "changed_paths_sample": paths[:sample_limit],
    }


def _hash_text(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _associated_pr_number(subject: str, body: str) -> str:
    haystack = f"{subject}\n{body}"
    for pattern in PULL_REQUEST_PATTERNS:
        match = pattern.search(haystack)
        if match:
            return match.group("number")
    return ""


def _classify_commit(subject: str, paths: list[str]) -> str:
    lowered_subject = subject.lower()
    lowered_paths = [path.lower() for path in paths]
    subject_kind = _conventional_subject_kind(lowered_subject)
    if subject_kind in {"docs", "ci", "test", "tests"}:
        return "tests" if subject_kind == "test" else subject_kind
    if _any_path_prefix(lowered_paths, ("docs/", "doc/")) or any(
        path.endswith((".md", ".mdx", ".rst")) for path in lowered_paths
    ):
        return "docs"
    if _any_path_prefix(lowered_paths, (".github/", "scripts/ci/")):
        return "ci"
    if _any_path_prefix(lowered_paths, ("test/", "tests/")) or any(
        "/test" in path or path.endswith((".test.js", "_test.py")) for path in lowered_paths
    ):
        return "tests"
    if any(token in lowered_subject for token in ("release", "version", "changelog")):
        return "release"
    if any(token in lowered_subject for token in ("dependabot", "dependency", "bump ")):
        return "dependency"
    if lowered_subject.startswith(("fix", "bug", "patch")):
        return "fix"
    if lowered_subject.startswith(("feat", "feature", "add ")):
        return "feature"
    if any(token in lowered_subject for token in ("refactor", "cleanup", "simplify")):
        return "refactor"
    return "unknown"


def _conventional_subject_kind(lowered_subject: str) -> str:
    match = re.match(r"^(?P<kind>[a-z]+)(?:\([^)]+\))?!?:", lowered_subject)
    if match:
        return match.group("kind")
    return ""


def _any_path_prefix(paths: list[str], prefixes: tuple[str, ...]) -> bool:
    return any(path.startswith(prefixes) for path in paths)
