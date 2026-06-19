import json
import os
from pathlib import Path
import subprocess

import pytest

from scripts import enforce_release_policy


def _git(repo: Path, *args: str) -> None:
    env = os.environ.copy()
    env.update(
        {
            "EDITOR": ":",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_EDITOR": ":",
            "VISUAL": ":",
        }
    )
    subprocess.check_call(["git", *args], cwd=repo, env=env)


def _write_manifest(repo: Path, version: str) -> None:
    manifest = repo / ".github" / ".release-please-manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({".": version}) + "\n", encoding="utf-8")


def test_major_release_policy_allows_patch_and_minor_without_release_as() -> None:
    enforce_release_policy.enforce_major_release_policy(
        previous_version="0.24.0",
        current_version="0.24.1",
        messages="fix: repair release flow",
    )
    enforce_release_policy.enforce_major_release_policy(
        previous_version="0.24.0",
        current_version="0.25.0",
        messages="feat: improve release flow",
    )


def test_major_release_policy_rejects_major_without_matching_release_as() -> None:
    with pytest.raises(enforce_release_policy.ReleasePolicyError, match="Release-As: 1.0.0"):
        enforce_release_policy.enforce_major_release_policy(
            previous_version="0.24.0",
            current_version="1.0.0",
            messages="feat!: break the action contract",
        )


def test_major_release_policy_requires_exact_release_as_version() -> None:
    with pytest.raises(enforce_release_policy.ReleasePolicyError, match="found 1.1.0"):
        enforce_release_policy.enforce_major_release_policy(
            previous_version="0.24.0",
            current_version="1.0.0",
            messages="feat!: break the action contract\n\nRelease-As: 1.1.0",
        )


def test_major_release_policy_allows_matching_release_as() -> None:
    enforce_release_policy.enforce_major_release_policy(
        previous_version="0.24.0",
        current_version="1.0.0",
        messages="feat!: break the action contract\n\nRelease-As: 1.0.0",
    )


def test_release_policy_from_git_checks_major_manifest_bump_messages(tmp_path: Path) -> None:
    _git(tmp_path, "-c", "init.defaultBranch=main", "init")
    _git(tmp_path, "config", "user.name", "Test User")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "commit.gpgSign", "false")
    _git(tmp_path, "config", "tag.gpgSign", "false")
    _git(tmp_path, "config", "core.hooksPath", "/dev/null")
    _write_manifest(tmp_path, "0.24.0")
    _git(tmp_path, "add", ".github/.release-please-manifest.json")
    _git(tmp_path, "commit", "-m", "chore: release 0.24.0")
    _git(tmp_path, "tag", "v0.24.0")
    _write_manifest(tmp_path, "1.0.0")
    _git(tmp_path, "add", ".github/.release-please-manifest.json")
    _git(tmp_path, "commit", "-m", "chore: release 1.0.0")

    with pytest.raises(enforce_release_policy.ReleasePolicyError, match="Release-As: 1.0.0"):
        enforce_release_policy.enforce_release_policy_from_git(root=tmp_path)

    _git(tmp_path, "commit", "--amend", "-m", "chore: release 1.0.0", "-m", "Release-As: 1.0.0")

    enforce_release_policy.enforce_release_policy_from_git(root=tmp_path)
