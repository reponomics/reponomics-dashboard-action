"""Commit-message helpers for GitHub API commit context."""

from __future__ import annotations

import re

PULL_REQUEST_PATTERNS = (
    re.compile(r"\(#(?P<number>\d+)\)"),
    re.compile(r"\b(?:pull request|pr)\s+#(?P<number>\d+)\b", re.IGNORECASE),
)


def associated_pr_number(subject: str, body: str) -> str:
    haystack = f"{subject}\n{body}"
    for pattern in PULL_REQUEST_PATTERNS:
        match = pattern.search(haystack)
        if match:
            return match.group("number")
    return ""


def classify_commit(subject: str, paths: list[str]) -> str:
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
