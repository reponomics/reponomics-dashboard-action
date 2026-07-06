from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts import staging_smoke


NONINTERACTIVE_ENV = {
    "CI": "true",
    "GH_PROMPT_DISABLED": "1",
    "GIT_ASKPASS": "/bin/echo",
    "GIT_TERMINAL_PROMPT": "0",
    "GCM_INTERACTIVE": "never",
    "SSH_ASKPASS": "/bin/echo",
}


def _run(command: list[str], cwd: Path) -> str:
    return subprocess.check_output(
        command,
        cwd=cwd,
        env={**os.environ, **NONINTERACTIVE_ENV},
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def _init_repo(path: Path) -> None:
    _run(["git", "init", "-b", "main"], path)
    _run(["git", "config", "core.hooksPath", "/dev/null"], path)
    _run(["git", "config", "user.name", "Test User"], path)
    _run(["git", "config", "user.email", "test@example.invalid"], path)


def test_prepare_staging_smoke_writes_minimal_public_encrypted_config(
    tmp_path: Path,
) -> None:
    output = tmp_path / "staging"
    evidence = tmp_path / "evidence.md"

    result = staging_smoke.prepare_staging_smoke(
        output_dir=output,
        remote="https://github.com/reponomics/reponomics-dashboard-staging.git",
        expected_repo="reponomics/reponomics-dashboard-staging",
        branch="main",
        message="chore: publish staging smoke dashboard",
        repositories=[
            "reponomics/reponomics-dashboard-action",
            "reponomics/reponomics-dashboard",
        ],
        publish_repositories=["reponomics/reponomics-dashboard-action"],
        evidence_file=evidence,
        push=False,
    )

    config = yaml.safe_load((output / "config.yaml").read_text(encoding="utf-8"))
    assert config["i_have_read_the_readme"] is True
    assert config["data_mode"] == "encrypted"
    assert config["publish_pages_dashboard"] is True
    assert config["publish_readme_dashboard"] is False
    assert config["use_github_app"] is False
    assert config["collect"]["repositories"] == [
        "reponomics/reponomics-dashboard-action",
        "reponomics/reponomics-dashboard",
    ]
    assert config["publish"]["repositories"] == [
        "reponomics/reponomics-dashboard-action"
    ]

    record = json.loads(
        (output / ".reponomics" / "staging-smoke.json").read_text(encoding="utf-8")
    )
    assert record["scenario"] == staging_smoke.SCENARIO_NAME
    assert record["target"]["expected_repo"] == "reponomics/reponomics-dashboard-staging"
    assert record["config"]["resolved"]["DATA_MODE"] == "encrypted"
    assert record["config"]["resolved"]["PUBLISH_PAGES_DASHBOARD"] == "true"
    assert record["config"]["resolved"]["PUBLISH_README_DASHBOARD"] == "false"
    assert result.published_commit is None
    assert result.evidence_file == evidence
    assert "prepared dry run" in evidence.read_text(encoding="utf-8")


def test_staging_smoke_rejects_publish_repositories_outside_collect() -> None:
    with pytest.raises(staging_smoke.StagingSmokeError, match="subset"):
        staging_smoke.resolve_repositories(
            ["reponomics/reponomics-dashboard-action"],
            ["reponomics/reponomics-dashboard"],
        )


def test_staging_smoke_rejects_bare_repository_names() -> None:
    with pytest.raises(staging_smoke.StagingSmokeError, match="full GitHub names"):
        staging_smoke.resolve_repositories(["reponomics-dashboard-action"], [])


def test_publish_staging_tree_replaces_legacy_remote_with_force_lease(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy-source"
    source.mkdir()
    _init_repo(source)
    (source / "legacy.txt").write_text("legacy\n", encoding="utf-8")
    _run(["git", "add", "-A"], source)
    _run(["git", "commit", "-m", "legacy"], source)

    remote = tmp_path / "staging.git"
    _run(["git", "init", "--bare", str(remote)], source)
    _run(["git", "remote", "add", "origin", str(remote)], source)
    _run(["git", "push", "-u", "origin", "main"], source)

    output = tmp_path / "output"
    (output / ".reponomics").mkdir(parents=True)
    (output / "config.yaml").write_text("data_mode: encrypted\n", encoding="utf-8")
    (output / ".reponomics" / "staging-smoke.json").write_text("{}\n", encoding="utf-8")
    (output / "README.md").write_text("staging\n", encoding="utf-8")

    published_commit = staging_smoke.publish_staging_tree(
        output,
        remote=str(remote),
        branch="main",
        message="chore: publish staging smoke dashboard",
        expected_repo="staging",
        push=True,
    )

    clone = tmp_path / "clone"
    _run(["git", "clone", "-b", "main", str(remote), str(clone)], tmp_path)
    assert published_commit == _run(["git", "rev-parse", "HEAD"], clone)
    assert not (clone / "legacy.txt").exists()
    assert (clone / "README.md").read_text(encoding="utf-8") == "staging\n"
    assert (clone / ".reponomics" / "staging-smoke.json").is_file()
