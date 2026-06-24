from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from dashboard_action import run
from collect_modules.git_history import collect_commit_history_from_clone


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", repo.as_posix(), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )
    return result.stdout.strip()


def _commit(repo: Path, message: list[str], *, when: str) -> str:
    env = {
        "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_DATE": when,
    }
    args = ["commit"]
    for item in message:
        args.extend(["-m", item])
    _git(repo, *args, env=env)
    return _git(repo, "rev-parse", "HEAD")


def test_collect_commit_history_from_clone_shapes_private_context_rows(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Alice Maintainer")
    _git(repo, "config", "user.email", "Alice@Example.com")

    docs_dir = repo / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "docs/guide.md")
    docs_sha = _commit(
        repo,
        ["docs: add guide"],
        when="2026-06-01T12:00:00+00:00",
    )

    src_dir = repo / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
    _git(repo, "add", "src/app.py")
    feature_sha = _commit(
        repo,
        ["feat: add API (#42)", "Body details"],
        when="2026-06-02T12:00:00+00:00",
    )

    rows = collect_commit_history_from_clone(
        "demo/app",
        repo,
        "2026-06-03T00:00:00Z",
    )

    by_sha = {row["sha"]: row for row in rows}
    assert set(by_sha) == {docs_sha, feature_sha}
    assert by_sha[docs_sha]["classification"] == "docs"
    assert by_sha[docs_sha]["files_changed"] == 1
    assert by_sha[docs_sha]["additions"] == 1
    assert by_sha[feature_sha]["classification"] == "feature"
    assert by_sha[feature_sha]["associated_pr_number"] == "42"
    assert by_sha[feature_sha]["changed_paths_sample"] == "src/app.py"
    assert by_sha[feature_sha]["message_body_hash"] == hashlib.sha256(
        b"Body details"
    ).hexdigest()
    assert by_sha[feature_sha]["author_email_hash"] == hashlib.sha256(
        b"alice@example.com"
    ).hexdigest()
    assert by_sha[feature_sha]["author_email_hash"] != "Alice@Example.com"
    assert by_sha[feature_sha]["source"] == "git-log"
    assert by_sha[feature_sha]["schema_version"] == run.storage.SCHEMA_VERSION
