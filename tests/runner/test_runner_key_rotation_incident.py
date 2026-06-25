from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import requests

from dashboard_action import run

from runner_support import (
    NEXT_KEY,
    OLD_KEY,
    _config,
    _response,
    _seed_log,
)


def test_rotate_key_fixture_reencrypts_with_next_secret(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path)
    _seed_log(config.data_dir)
    run.run_collect(config, restore_artifact=False, execute_collect=False)

    encrypted_path = tmp_path / ".dashboard-data-artifact" / "dashboard-data.enc"
    config.data_dir.mkdir(exist_ok=True)
    for path in config.data_dir.iterdir():
        path.unlink()
    (config.data_dir / "dashboard-data.enc").write_text(
        encrypted_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    rotated = _config(
        tmp_path,
        mode="rotate-key",
        dashboard_next_secret=NEXT_KEY,
    )
    run.validate_config(rotated)
    run.run_rotate_key(rotated, restore_artifact=False)

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
    assert (rotated.data_dir / "traffic-daily.csv").exists()

    run.crypto_artifact.encrypt(rotated.data_dir, encrypted_path, "DASHBOARD_SECRET_DO_NOT_REPLACE")
    for path in rotated.data_dir.iterdir():
        path.unlink()
    (rotated.data_dir / "dashboard-data.enc").write_text(
        encrypted_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setenv("DASHBOARD_SECRET_DO_NOT_REPLACE", OLD_KEY)
    with pytest.raises(Exception):
        run.crypto_artifact.decrypt(
            rotated.data_dir / "dashboard-data.enc",
            rotated.data_dir,
            "DASHBOARD_SECRET_DO_NOT_REPLACE",
        )


def test_purge_workflow_history_deletes_old_runs_and_related_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _config(
        tmp_path,
        mode="incident-reset",
        dashboard_next_secret=NEXT_KEY,
    )
    monkeypatch.setenv("GITHUB_REPOSITORY", "demo/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "400")
    captured_headers: list[dict[str, str]] = []

    def fake_fetch_json(url: str, headers: dict[str, str], allow_not_found: bool = False) -> Any:
        del allow_not_found
        captured_headers.append(headers)
        if "/actions/artifacts" in url and "page=1" in url:
            return {
                "artifacts": [
                    {"id": 11, "workflow_run": {"id": 399}},
                    {"id": 12, "workflow_run": {"id": 400}},
                    {"id": 13, "workflow_run": {"id": 397}},
                    {"id": 14, "workflow_run": None},
                ]
            }
        if "/actions/artifacts" in url and "page=2" in url:
            return {"artifacts": []}
        raise AssertionError(f"Unexpected URL: {url}")

    deleted_urls: list[str] = []

    def fake_delete(url: str, *, headers: dict[str, str], timeout: int) -> requests.Response:
        assert timeout == run.INCIDENT_API_TIMEOUT_SECONDS
        assert headers["Authorization"] == f"Bearer {config.github_token}"
        deleted_urls.append(url)
        return _response(204)

    monkeypatch.setattr(run.collect_mod, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(run.requests, "delete", fake_delete)

    result = run._purge_workflow_history(config)

    assert result.candidate_artifacts == 3
    assert result.candidate_runs == 2
    assert result.deleted_runs == 2
    assert result.deleted_fallback_artifacts == 1
    assert set(deleted_urls) == {
        "https://api.github.com/repos/demo/repo/actions/runs/399",
        "https://api.github.com/repos/demo/repo/actions/runs/397",
        "https://api.github.com/repos/demo/repo/actions/artifacts/14",
    }
    assert captured_headers
    assert all(
        headers["Authorization"] == f"Bearer {config.github_token}" for headers in captured_headers
    )


def test_collect_cleanup_deletes_only_next_superseded_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    monkeypatch.setenv("GITHUB_REPOSITORY", "demo/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "400")

    def fake_fetch_json(url: str, headers: dict[str, str], allow_not_found: bool = False) -> Any:
        del headers, allow_not_found
        if "/actions/artifacts" in url and "page=1" in url:
            return {
                "artifacts": [
                    {"id": 50, "created_at": "2026-06-05T12:00:00Z", "workflow_run": {"id": 400}},
                    {"id": 41, "created_at": "2026-06-04T12:00:00Z", "workflow_run": {"id": 399}},
                    {"id": 31, "created_at": "2026-06-03T12:00:00Z", "workflow_run": {"id": 398}},
                    {"id": 21, "created_at": "2026-06-02T12:00:00Z", "workflow_run": {"id": 397}},
                    {"id": 11, "created_at": "2026-06-01T12:00:00Z", "workflow_run": {"id": 396}},
                ]
            }
        if "/actions/artifacts" in url and "page=2" in url:
            return {"artifacts": []}
        raise AssertionError(f"Unexpected URL: {url}")

    deleted_urls: list[str] = []

    def fake_delete(url: str, *, headers: dict[str, str], timeout: int) -> requests.Response:
        assert timeout == run.INCIDENT_API_TIMEOUT_SECONDS
        assert headers["Authorization"] == f"Bearer {config.github_token}"
        deleted_urls.append(url)
        return _response(204)

    monkeypatch.setattr(run.collect_mod, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(run.requests, "delete", fake_delete)

    result = run._cleanup_superseded_collect_artifacts(config)

    assert result.prior_artifacts == 4
    assert result.retained_prior_artifacts == 2
    assert result.delete_candidates == 2
    assert result.deleted_artifacts == 1
    assert deleted_urls == [
        "https://api.github.com/repos/demo/repo/actions/artifacts/21",
    ]
    assert not any("/actions/runs/" in url for url in deleted_urls)


def test_incident_reset_reencrypts_without_rendering_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path)
    _seed_log(config.data_dir)
    run.run_collect(config, restore_artifact=False, execute_collect=False)

    encrypted_path = tmp_path / ".dashboard-data-artifact" / "dashboard-data.enc"
    config.data_dir.mkdir(exist_ok=True)
    for path in config.data_dir.iterdir():
        path.unlink()
    (config.data_dir / "dashboard-data.enc").write_text(
        encrypted_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    incident = _config(
        tmp_path,
        mode="incident-reset",
        dashboard_next_secret=NEXT_KEY,
        incident_confirm_mode=run.INCIDENT_CONFIRM_MODE,
        incident_confirm_purge=run.INCIDENT_CONFIRM_PURGE,
        incident_confirm_next_secret=run.INCIDENT_CONFIRM_NEXT_SECRET,
        incident_confirm_irreversible=run.INCIDENT_CONFIRM_IRREVERSIBLE,
    )
    purge_called = False

    def fake_purge(_config: run.RuntimeConfig) -> run.IncidentPurgeResult:
        nonlocal purge_called
        purge_called = True
        return run.IncidentPurgeResult(0, 0, 0, 0)

    monkeypatch.setattr(run, "_purge_workflow_history", fake_purge)

    run.validate_config(incident)
    run.run_incident_reset(incident, restore_artifact=False)

    assert purge_called is False
    assert not incident.readme_path.exists()
    assert not incident.pages_index_path.exists()

    for path in incident.data_dir.iterdir():
        path.unlink()
    (incident.data_dir / "dashboard-data.enc").write_text(
        encrypted_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    monkeypatch.setenv("DASHBOARD_SECRET_DO_NOT_REPLACE", NEXT_KEY)
    run.crypto_artifact.decrypt(
        incident.data_dir / "dashboard-data.enc",
        incident.data_dir,
        "DASHBOARD_SECRET_DO_NOT_REPLACE",
    )
    assert (incident.data_dir / "traffic-daily.csv").exists()
