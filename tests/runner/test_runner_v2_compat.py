from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from dashboard_action import run

from runner_support import (
    NEXT_KEY,
    _config,
    _copy_fixture,
    _seed_log,
    _stub_context_collectors,
)


def test_publish_plaintext_rejects_encrypted_retained_artifact_before_migration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    encrypted_artifact = data_dir / "dashboard-data.enc"
    encrypted_artifact.write_text("not a plaintext data directory", encoding="utf-8")
    config = _config(
        tmp_path,
        mode="publish",
        data_dir=data_dir,
        data_mode="plaintext",
        dashboard_secret="",
        publish_pages_requested=False,
    )

    with pytest.raises(run.ActionError, match="artifact is encrypted"):
        run.run_publish(config, restore_artifact=False)

    assert encrypted_artifact.read_text(encoding="utf-8") == "not a plaintext data directory"
    assert not (data_dir / "traffic-log.csv").exists()


def test_collect_from_v2_fixture_migrates_and_keeps_old_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    fixture = _copy_fixture("compat_v2", tmp_path)
    config = _config(
        tmp_path,
        config_path=fixture / "config.yaml",
        data_dir=fixture / "data",
    )
    before_config = config.config_path.read_text(encoding="utf-8")
    assert "repo_growth" not in before_config
    assert "data_families" not in before_config

    monkeypatch.setattr(run.collect_mod, "get_headers", lambda: {})
    monkeypatch.setattr(run.collect_mod, "validate_token", lambda headers: None)
    monkeypatch.setattr(
        run.collect_mod,
        "discover_repositories",
        lambda headers: [
            {
                "full_name": "demo/reponomics",
                "id": 123,
                "node_id": "R_123",
                "permissions": {"push": True},
                "fork": False,
                "archived": False,
                "disabled": False,
                "private": False,
                "created_at": "2025-01-01T00:00:00Z",
                "stargazers_count": 1,
                "watchers_count": 999,
                "subscribers_count": 1,
                "forks_count": 1,
            }
        ],
    )
    detail_calls: list[str] = []
    community_calls: list[str] = []

    def fake_fetch_json(url: str, headers, allow_not_found: bool = False):
        assert allow_not_found is False
        if url == "https://api.github.com/repos/demo/reponomics/community/profile":
            community_calls.append(url)
            return {
                "health_percentage": 57,
                "documentation": "",
                "updated_at": "2026-05-16T12:00:00Z",
                "files": {
                    "code_of_conduct": None,
                    "contributing": None,
                    "issue_template": None,
                    "pull_request_template": None,
                    "readme": {"html_url": "https://example.com/readme"},
                    "license": {"html_url": "https://example.com/license"},
                },
            }
        assert url == "https://api.github.com/repos/demo/reponomics"
        detail_calls.append(url)
        return {
            "id": 123,
            "node_id": "R_123",
            "stargazers_count": 15,
            "watchers_count": 999,
            "subscribers_count": 3,
            "forks_count": 2,
            "open_issues_count": 4,
            "size": 512,
            "created_at": "2025-01-01T00:00:00Z",
            "pushed_at": "2026-05-16T10:00:00Z",
            "updated_at": "2026-05-16T10:30:00Z",
            "language": "Python",
            "visibility": "public",
            "default_branch": "main",
            "has_pages": False,
            "has_discussions": True,
            "archived": False,
            "disabled": False,
        }

    monkeypatch.setattr(run.collect_mod, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(run.collect_mod, "collect_views_clones", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_referrers", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_paths", lambda *args: [])
    _stub_context_collectors(monkeypatch)

    run.run_collect(config, restore_artifact=False, execute_collect=True)

    assert config.config_path.read_text(encoding="utf-8") == before_config
    with (config.data_dir / "repo-metrics.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert detail_calls == ["https://api.github.com/repos/demo/reponomics"]
    assert community_calls == ["https://api.github.com/repos/demo/reponomics/community/profile"]
    assert rows[-1]["repo_id"] == "123"
    assert rows[-1]["stargazers_count"] == "15"
    assert rows[-1]["subscribers_count"] == "3"
    assert rows[-1]["forks_count"] == "2"
    assert rows[-1]["open_issues_count"] == "4"
    assert rows[-1]["size_kb"] == "512"
    assert rows[-1]["default_branch"] == "main"
    assert rows[-1]["source"] == "repo-detail"
    assert rows[-1]["schema_version"] == run.storage.SCHEMA_VERSION
    assert (tmp_path / ".dashboard-data-artifact" / "dashboard-data.enc").exists()


def test_publish_from_v2_fixture_migrates_without_config_rewrite(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    fixture = _copy_fixture("compat_v2", tmp_path)
    config = _config(
        tmp_path,
        mode="publish",
        generate_readme=True,
        config_path=fixture / "config.yaml",
        data_dir=fixture / "data",
    )
    before_config = config.config_path.read_text(encoding="utf-8")

    run.run_publish(config, restore_artifact=False)

    assert config.config_path.read_text(encoding="utf-8") == before_config
    assert config.readme_path.exists()
    assert config.pages_index_path.exists()
    manifest = json.loads((config.data_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == run.storage.SCHEMA_VERSION
    header = (config.data_dir / "repo-metrics.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == run.storage.REPO_METRIC_FIELDS
    readme = config.readme_path.read_text(encoding="utf-8")
    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    assert "Growth (14d)" in readme
    assert "now 11 / 2" in readme
    assert "Reponomics Dashboard" in dashboard
    assert "encrypted-dashboard-data" in dashboard


def test_rotate_key_from_v2_encrypted_fixture_migrates_without_config_rewrite(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    fixture = _copy_fixture("compat_v2", tmp_path)
    config = _config(
        tmp_path,
        config_path=fixture / "config.yaml",
        data_dir=fixture / "data",
    )
    before_config = config.config_path.read_text(encoding="utf-8")

    run._patch_runtime_paths(config)
    run._set_runtime_env(config)
    encrypted_path = tmp_path / ".dashboard-data-artifact" / "dashboard-data.enc"
    run.crypto_artifact.encrypt(config.data_dir, encrypted_path, "DASHBOARD_SECRET_DO_NOT_REPLACE")
    for path in config.data_dir.iterdir():
        path.unlink()
    (config.data_dir / "dashboard-data.enc").write_text(
        encrypted_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    rotated = _config(
        tmp_path,
        mode="rotate-key",
        config_path=config.config_path,
        data_dir=config.data_dir,
        dashboard_next_secret=NEXT_KEY,
    )
    run.validate_config(rotated)
    run.run_rotate_key(rotated, restore_artifact=False)

    assert rotated.config_path.read_text(encoding="utf-8") == before_config
    assert encrypted_path.exists()

    for path in rotated.data_dir.iterdir():
        path.unlink()
    (rotated.data_dir / "dashboard-data.enc").write_text(
        encrypted_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setenv("DASHBOARD_SECRET_DO_NOT_REPLACE", NEXT_KEY)
    run.crypto_artifact.decrypt(
        rotated.data_dir / "dashboard-data.enc",
        rotated.data_dir,
        "DASHBOARD_SECRET_DO_NOT_REPLACE",
    )

    manifest = json.loads((rotated.data_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == run.storage.SCHEMA_VERSION
    assert rotated.config_path.read_text(encoding="utf-8") == before_config
    header = (rotated.data_dir / "repo-metrics.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == run.storage.REPO_METRIC_FIELDS


def test_publish_degrades_when_repo_metrics_history_is_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish", generate_readme=True)
    _seed_log(config.data_dir)
    (config.data_dir / "repo-metrics.csv").unlink()

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    readme = config.readme_path.read_text(encoding="utf-8")
    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    assert config.readme_path.exists()
    assert config.pages_index_path.exists()
    assert "Growth (14d)" not in readme
    assert "Reponomics Dashboard" in dashboard
    assert "encrypted-dashboard-data" in dashboard
