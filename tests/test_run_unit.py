from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from dashboard_action import run


def test_repo_is_public_reads_event_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"repository": {"private": False}}), encoding="utf-8")
    monkeypatch.delenv("GITHUB_EVENT_REPOSITORY_PRIVATE", raising=False)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    assert run._repo_is_public() is True

    event_path.write_text(json.dumps({"repository": {"private": True}}), encoding="utf-8")
    assert run._repo_is_public() is False


def test_repo_is_public_ignores_malformed_event_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.delenv("GITHUB_EVENT_REPOSITORY_PRIVATE", raising=False)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    assert run._repo_is_public() is False


def test_load_config_rejects_invalid_boolean_and_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPONOMICS_COMMIT_OUTPUTS", "maybe")
    with pytest.raises(run.ActionError, match="commit-outputs must be true or false"):
        run.load_config_from_env()

    monkeypatch.setenv("REPONOMICS_COMMIT_OUTPUTS", "false")
    monkeypatch.setenv("REPONOMICS_RETENTION_DAYS", "0")
    with pytest.raises(run.ActionError, match="retention-days must be between 1 and 90"):
        run.load_config_from_env()

    monkeypatch.setenv("REPONOMICS_RETENTION_DAYS", "not-an-int")
    with pytest.raises(run.ActionError, match="retention-days must be an integer"):
        run.load_config_from_env()


def test_restore_artifact_skips_without_github_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    called = False

    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal called
        called = True
        return subprocess.CompletedProcess([], 0)

    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.setattr(run.subprocess, "run", fake_run)

    run._restore_artifact(_config_for_run_tests(tmp_path))

    assert called is False


def test_restore_artifact_invokes_script_with_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(args: list[str], *, check: bool, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        calls.append({"args": args, "check": check, "env": env})
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setenv("GITHUB_REPOSITORY", "demo/repo")
    monkeypatch.setattr(run.shutil, "which", lambda name: "/usr/bin/gh" if name == "gh" else None)
    monkeypatch.setattr(run.subprocess, "run", fake_run)
    config = _config_for_run_tests(tmp_path, github_token="ghp_token")

    run._restore_artifact(config)

    assert calls[0]["args"] == ["bash", str(run.SCRIPTS_DIR / "restore_artifact.sh")]
    assert calls[0]["check"] is True
    assert calls[0]["env"]["ARTIFACT_NAME"] == "traffic-data"
    assert calls[0]["env"]["DATA_DIR"] == config.data_dir.as_posix()
    assert calls[0]["env"]["GH_TOKEN"] == "ghp_token"


def test_summarize_rotation_writes_github_step_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))

    run._summarize_rotation()

    summary = summary_path.read_text(encoding="utf-8")
    assert "Dashboard key rotation complete" in summary
    assert "TRAFFIC_DASHBOARD_NEXT_SECRET" in summary


def test_main_dispatches_modes_and_reports_action_errors(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    called: list[str] = []
    config = _config_for_run_tests(tmp_path, mode="publish")

    monkeypatch.setattr(run, "validate_config", lambda received: called.append(received.mode))
    monkeypatch.setattr(run, "run_publish", lambda received: called.append(f"publish:{received.mode}"))

    run.main(lambda: config)

    assert called == ["publish", "publish:publish"]

    def broken_loader() -> run.RuntimeConfig:
        raise run.ActionError("bad input")

    with pytest.raises(SystemExit) as exc_info:
        run.main(broken_loader)

    assert exc_info.value.code == 1
    assert "Reponomics action error: bad input" in capsys.readouterr().err


def _config_for_run_tests(tmp_path: Path, **overrides: Any) -> run.RuntimeConfig:
    values: dict[str, Any] = {
        "mode": "collect",
        "traffic_token": "ghp_traffic",
        "github_token": "",
        "dashboard_secret": "dashboard-secret-" + ("x" * 40),
        "dashboard_next_secret": "",
        "readme_dashboard": "enabled",
        "pages_dashboard": "plain",
        "artifact_security_mode": "plain",
        "config_path": tmp_path / "config.yaml",
        "data_dir": tmp_path / "data",
        "retention_days": 90,
        "commit_outputs": False,
        "dashboard_path": tmp_path / "docs" / "index.html",
        "readme_path": tmp_path / "README.md",
        "allow_weak_dashboard_secret": False,
        "update_notices": False,
        "action_ref": "v0.2.0",
        "action_repository": "reponomics/reponomics-dashboard-action",
    }
    values.update(overrides)
    return run.RuntimeConfig(**values)
