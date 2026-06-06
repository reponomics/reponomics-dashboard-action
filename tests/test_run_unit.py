from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import requests

from dashboard_action import run


@pytest.fixture(autouse=True)
def _restore_run_environment() -> Any:
    keys = {
        "ARTIFACT_SECURITY_MODE",
        "DASHBOARD_ACCESS_MODE",
        "DASHBOARD_KEY",
        "DASHBOARD_NEXT_SECRET",
        "DASHBOARD_SECRET_DO_NOT_REPLACE",
        "DATA_DIR",
        "GH_TOKEN",
        "PUBLISH_PAGES",
        "REPONOMICS_ACTION_REF",
        "REPONOMICS_ACTION_REPOSITORY",
        "REPONOMICS_USE_GITHUB_APP",
        "RETENTION_DAYS",
        run.DOCS_ACTION_VERSION_ENV,
        run.DOCS_SYNC_STATE_ENV,
        run.DOCS_UPDATED_AT_ENV,
    }
    before = {key: os.environ.get(key) for key in keys}
    yield
    for key, value in before.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_repo_is_public_reads_event_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
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

    with pytest.raises(run.ActionError, match="GITHUB_EVENT_PATH"):
        run._repo_is_public()


@pytest.mark.parametrize(
    ("event_repository_private", "event_body", "expected_fragment"),
    [
        ("maybe", None, "GITHUB_EVENT_REPOSITORY_PRIVATE"),
        ("", "{not-json", "GITHUB_EVENT_PATH"),
        ("", "{}", "repository.private is missing"),
    ],
)
def test_repo_is_public_fails_closed_when_context_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    event_repository_private: str,
    event_body: str | None,
    expected_fragment: str,
) -> None:
    if event_repository_private:
        monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", event_repository_private)
    else:
        monkeypatch.delenv("GITHUB_EVENT_REPOSITORY_PRIVATE", raising=False)

    if event_body is None:
        monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    else:
        event_path = tmp_path / "event.json"
        event_path.write_text(event_body, encoding="utf-8")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    with pytest.raises(run.ActionError, match=expected_fragment):
        run._repo_is_public()


def test_load_config_rejects_invalid_boolean_and_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "false")
    monkeypatch.setenv("REPONOMICS_GENERATE_README", "maybe")
    with pytest.raises(run.ActionError, match="generate-readme must be true or false"):
        run.load_config_from_env()

    monkeypatch.setenv("REPONOMICS_GENERATE_README", "false")
    monkeypatch.setenv("REPONOMICS_PUBLISH_PAGES", "sometimes")
    with pytest.raises(run.ActionError, match="publish-pages must be true or false"):
        run.load_config_from_env()

    monkeypatch.setenv("REPONOMICS_PUBLISH_PAGES", "true")
    monkeypatch.setenv("REPONOMICS_RETENTION_DAYS", "0")
    with pytest.raises(run.ActionError, match="retention-days must be between 1 and 90"):
        run.load_config_from_env()

    monkeypatch.setenv("REPONOMICS_RETENTION_DAYS", "not-an-int")
    with pytest.raises(run.ActionError, match="retention-days must be an integer"):
        run.load_config_from_env()


def test_validate_config_rejects_public_readme_generation(tmp_path: Path) -> None:
    config = _config_for_run_tests(
        tmp_path,
        privacy_mode="strong",
        repo_is_public=True,
        generate_readme=True,
        github_token="ghp_test",
    )

    with pytest.raises(run.ActionError, match="generate-readme is only supported"):
        run.validate_config(config)


def test_load_config_rejects_invalid_artifact_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    monkeypatch.setenv("REPONOMICS_MODE", "publish")
    monkeypatch.setenv("REPONOMICS_PRIVACY_MODE", "plain")
    monkeypatch.setenv("REPONOMICS_ARTIFACT_RUN_ID", "latest")

    with pytest.raises(run.ActionError, match="artifact-run-id must be a positive integer"):
        run.load_config_from_env()


def test_load_config_supports_auto_and_legacy_privacy_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "false")
    monkeypatch.setenv("REPONOMICS_PRIVACY_MODE", "auto")
    assert run.load_config_from_env().privacy_mode == "strong"

    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    assert run.load_config_from_env().privacy_mode == "plain"

    monkeypatch.setenv("REPONOMICS_PRIVACY_MODE", "encrypted")
    assert run.load_config_from_env().privacy_mode == "strong"


def test_allow_docs_sync_config_file_errors_and_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    assert run._config_allow_docs_sync(config_path) is None

    config_path.write_text("allow_docs_sync: false\n", encoding="utf-8")
    assert run._config_allow_docs_sync(config_path) is False

    config_path.write_text("allow_docs_sync: not-a-bool\n", encoding="utf-8")
    with pytest.raises(run.ActionError, match="allow_docs_sync"):
        run._config_allow_docs_sync(config_path)

    config_path.write_text("allow_docs_sync: [", encoding="utf-8")
    with pytest.raises(run.ActionError, match="Could not read allow_docs_sync"):
        run._config_allow_docs_sync(config_path)


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
    assert calls[0]["env"]["ARTIFACT_NAME"] == "dashboard-data"
    assert calls[0]["env"]["DATA_DIR"] == config.data_dir.as_posix()
    assert calls[0]["env"]["GH_TOKEN"] == "ghp_token"


def test_restore_artifact_passes_run_id(
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
    config = _config_for_run_tests(tmp_path, artifact_run_id="123456")

    run._restore_artifact(config)

    assert calls[0]["env"]["ARTIFACT_RUN_ID"] == "123456"


def test_runtime_env_sets_optional_tokens_and_next_dashboard_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    links: list[run.RuntimeConfig] = []
    monkeypatch.setattr(run, "_set_managed_docs_link_env", links.append)
    config = _config_for_run_tests(
        tmp_path,
        use_github_app=True,
        collection_token="ghp_collect",
        dashboard_secret="old-secret",
        dashboard_next_secret="next-secret",
        action_ref="refs/tags/v1",
        action_repository="demo/action",
        privacy_mode="strong",
    )

    run._set_runtime_env(config, next_key=True)

    assert links == [config]
    assert run.os.environ["GH_TOKEN"] == "ghp_collect"
    assert run.os.environ["REPONOMICS_USE_GITHUB_APP"] == "true"
    assert run.os.environ["DASHBOARD_SECRET_DO_NOT_REPLACE"] == "old-secret"
    assert run.os.environ["DASHBOARD_NEXT_SECRET"] == "next-secret"
    assert run.os.environ["DASHBOARD_KEY"] == "next-secret"
    assert run.os.environ["REPONOMICS_ACTION_REF"] == "refs/tags/v1"
    assert run.os.environ["REPONOMICS_ACTION_REPOSITORY"] == "demo/action"


def test_set_managed_docs_status_env_handles_absent_invalid_current_and_stale(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(run.DOCS_SYNC_STATE_ENV, raising=False)
    run._set_managed_docs_status_env()
    assert run.os.environ[run.DOCS_SYNC_STATE_ENV] == ""

    namespace = tmp_path / run.MANAGED_DOCS_NAMESPACE
    namespace.mkdir(parents=True)
    manifest_path = namespace / run.managed_docs.MANIFEST_NAME
    manifest_path.write_text("{not-json", encoding="utf-8")
    run._set_managed_docs_status_env()
    assert run.os.environ[run.DOCS_SYNC_STATE_ENV] == run.managed_docs.STATE_MANIFEST_INCONSISTENT

    monkeypatch.delenv(run.DOCS_SYNC_STATE_ENV, raising=False)
    manifest_path.write_text(
        json.dumps({"action_version": run.VERSION, "updated_at": "2026-06-06T12:00:00Z"}),
        encoding="utf-8",
    )
    run._set_managed_docs_status_env()
    assert run.os.environ[run.DOCS_SYNC_STATE_ENV] == run.managed_docs.STATE_UNCHANGED
    assert run.os.environ[run.DOCS_ACTION_VERSION_ENV] == run.VERSION

    monkeypatch.delenv(run.DOCS_SYNC_STATE_ENV, raising=False)
    monkeypatch.delenv(run.DOCS_ACTION_VERSION_ENV, raising=False)
    manifest_path.write_text(json.dumps({"action_version": "0.1.0"}), encoding="utf-8")
    run._set_managed_docs_status_env()
    assert run.os.environ[run.DOCS_SYNC_STATE_ENV] == run.DOCS_STATE_STALE


def test_run_scoped_artifact_restore_paginates_artifacts() -> None:
    script = (run.SCRIPTS_DIR / "restore_artifact.sh").read_text(encoding="utf-8")
    artifact_lookup = script.split("# Find the requested artifact.", 1)[1]
    run_scoped_query = artifact_lookup.split('if [ -n "$ARTIFACT_RUN_ID" ]; then', 1)[1].split(
        "else",
        1,
    )[0]

    assert "gh api --paginate" in run_scoped_query
    assert "actions/runs/${ARTIFACT_RUN_ID}/artifacts?per_page=100" in run_scoped_query


def test_summarize_rotation_writes_github_step_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))

    run._summarize_rotation()

    summary = summary_path.read_text(encoding="utf-8")
    assert "Dashboard key rotation complete" in summary
    assert "DASHBOARD_NEXT_SECRET" in summary


def test_incident_and_docs_summaries_write_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    run._summarize_incident_reset_prepared()
    run._summarize_incident_reset_purge(run.IncidentPurgeResult(3, 2, 1, 1))
    run._summarize_active_retention_cleanup(run.ActiveRetentionCleanupResult(4, 2, 2, 1))
    run._summarize_docs_sync(
        run.managed_docs.ManagedDocsResult(
            state=run.managed_docs.STATE_PUSH_RACE,
            reason="push race",
            manifest_action_version="0.1.0",
            docs_updated_at="2026-06-06T12:00:00Z",
            namespace=Path("docs/reponomics"),
            changed=True,
        )
    )

    output = capsys.readouterr().out
    assert "Incident reset artifact prepared" in output
    assert "Deleted workflow runs: 1" in output
    assert "Dashboard data retention cleanup complete" in output
    assert "could not be pushed after a bounded retry" in output


def test_mask_secret_filters_short_values_and_escapes_commands(
    capfd: pytest.CaptureFixture[str],
) -> None:
    run._mask_secret("xy\nabc%123\nzztop")

    captured = capfd.readouterr()
    # "xy" is intentionally absent: values shorter than MIN_MASK_LENGTH (3)
    # are filtered and do not produce ::add-mask:: commands.
    assert captured.out == "::add-mask::abc%25123\n::add-mask::zztop\n"
    assert captured.err == ""


def test_mask_config_secrets_masks_each_secret_line(
    capfd: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    config = _config_for_run_tests(
        tmp_path,
        collection_token="ghp_collection",
        github_token="ghp_github",
        dashboard_secret="dashboard%secret",
        dashboard_next_secret="next-secret",
    )

    run._mask_config_secrets(config)

    captured = capfd.readouterr()
    assert captured.out.splitlines() == [
        "::add-mask::ghp_collection",
        "::add-mask::ghp_github",
        "::add-mask::dashboard%25secret",
        "::add-mask::next-secret",
    ]
    assert captured.err == ""


def test_main_dispatches_modes_and_reports_action_errors(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    called: list[str] = []
    config = _config_for_run_tests(tmp_path, mode="publish")

    monkeypatch.setattr(run, "validate_config", lambda received: called.append(received.mode))
    monkeypatch.setattr(run, "_mask_config_secrets", lambda _config: None)
    monkeypatch.setattr(run, "run_publish", lambda received: called.append(f"publish:{received.mode}"))

    run.main(lambda: config)

    assert called == ["publish", "publish:publish"]

    def broken_loader() -> run.RuntimeConfig:
        raise run.ActionError("bad input")

    with pytest.raises(SystemExit) as exc_info:
        run.main(broken_loader)

    assert exc_info.value.code == 1
    assert "Reponomics action error: bad input" in capsys.readouterr().err


def test_main_dispatches_incident_reset_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    called: list[str] = []
    config = _config_for_run_tests(tmp_path, mode="incident-reset")

    monkeypatch.setattr(run, "validate_config", lambda received: called.append(received.mode))
    monkeypatch.setattr(run, "_mask_config_secrets", lambda _config: None)
    monkeypatch.setattr(
        run,
        "run_incident_reset",
        lambda received: called.append(f"incident:{received.mode}"),
    )

    run.main(lambda: config)

    assert called == ["incident-reset", "incident:incident-reset"]


def test_main_dispatches_incident_reset_purge_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    called: list[str] = []
    config = _config_for_run_tests(tmp_path, mode="incident-reset")

    monkeypatch.setenv("REPONOMICS_INCIDENT_RESET_PURGE_ONLY", "true")
    monkeypatch.setattr(run, "validate_config", lambda received: called.append(received.mode))
    monkeypatch.setattr(run, "_mask_config_secrets", lambda _config: None)
    monkeypatch.setattr(
        run,
        "run_incident_reset_purge",
        lambda received: called.append(f"purge:{received.mode}"),
    )

    run.main(lambda: config)

    assert called == ["incident-reset", "purge:incident-reset"]


def test_main_dispatches_docs_sync_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    called: list[str] = []
    config = _config_for_run_tests(tmp_path, mode="docs-sync")

    monkeypatch.setattr(run, "validate_config", lambda received: called.append(received.mode))
    monkeypatch.setattr(run, "_mask_config_secrets", lambda _config: None)
    monkeypatch.setattr(
        run,
        "run_docs_sync",
        lambda received: called.append(f"docs:{received.mode}"),
    )

    run.main(lambda: config)

    assert called == ["docs-sync", "docs:docs-sync"]


def test_main_dispatches_collect_cleanup_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    called: list[str] = []
    config = _config_for_run_tests(tmp_path, mode="collect", github_token="ghp_test")

    monkeypatch.setenv("REPONOMICS_COLLECT_RETENTION_CLEANUP_ONLY", "true")
    monkeypatch.setattr(run, "_mask_config_secrets", lambda _config: None)
    monkeypatch.setattr(run, "run_collect_retention_cleanup", lambda received: called.append(received.mode))

    run.main(lambda: config)

    assert called == ["collect"]


def test_validate_config_covers_encrypted_modes_and_incident_failures(tmp_path: Path) -> None:
    with pytest.raises(run.ActionError, match="collection-token"):
        run.validate_config(_config_for_run_tests(tmp_path, collection_token="", github_token="ghp_test"))

    with pytest.raises(run.ActionError, match="github-token"):
        run.validate_config(_config_for_run_tests(tmp_path, github_token=""))

    with pytest.raises(run.ActionError, match="privacy-mode plain"):
        run.validate_config(
            _config_for_run_tests(
                tmp_path,
                github_token="ghp_test",
                repo_is_public=True,
                privacy_mode="plain",
            )
        )

    with pytest.raises(run.ActionError, match="requires strong or casual"):
        run.validate_config(_config_for_run_tests(tmp_path, mode="rotate-key", privacy_mode="plain"))

    with pytest.raises(run.ActionError, match="dashboard-next-secret"):
        run.validate_config(
            _config_for_run_tests(
                tmp_path,
                mode="rotate-key",
                privacy_mode="strong",
                dashboard_next_secret="",
            )
        )

    with pytest.raises(run.ActionError, match="incident-reset requires"):
        run.validate_config(_config_for_run_tests(tmp_path, mode="incident-reset", privacy_mode="plain"))

    with pytest.raises(run.ActionError, match="incident-confirm-mode"):
        run.validate_config(
            _config_for_run_tests(
                tmp_path,
                mode="incident-reset",
                privacy_mode="casual",
                github_token="ghp_test",
                dashboard_next_secret="next",
            )
        )


def test_github_helpers_parse_context_and_wrap_fetch_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert run._github_api_headers("ghp_test")["Authorization"] == "Bearer ghp_test"

    monkeypatch.setenv("GITHUB_REPOSITORY", "demo/repo")
    assert run._github_repository() == ("demo", "repo")

    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    assert run._github_run_id() == 123

    monkeypatch.setenv("GITHUB_REPOSITORY", "bad")
    with pytest.raises(run.ActionError, match="owner/repo"):
        run._github_repository()

    monkeypatch.setenv("GITHUB_RUN_ID", "abc")
    with pytest.raises(run.ActionError, match="invalid GITHUB_RUN_ID"):
        run._github_run_id()

    monkeypatch.setattr(run.collect_mod, "fetch_json", lambda _url, _headers: (_ for _ in ()).throw(requests.Timeout("slow")))
    with pytest.raises(run.ActionError, match="slow"):
        run._github_fetch_json("https://api.github.test/repos", {})


def test_github_delete_retries_and_reports_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses: list[requests.Response | requests.RequestException] = [
        requests.ConnectionError("offline"),
        _response(500, text="server"),
        _response(204),
    ]
    sleeps: list[float] = []

    def fake_delete(_url: str, *, headers: dict[str, str], timeout: int) -> requests.Response:
        assert headers == {"Authorization": "Bearer test"}
        assert timeout == run.INCIDENT_API_TIMEOUT_SECONDS
        next_response = responses.pop(0)
        if isinstance(next_response, requests.RequestException):
            raise next_response
        return next_response

    monkeypatch.setattr(run.requests, "delete", fake_delete)
    monkeypatch.setattr(run.time, "sleep", sleeps.append)
    monkeypatch.setattr(run.collect_mod, "_retry_delay_with_jitter", lambda attempt: float(attempt))

    assert run._github_delete("https://api.github.test/delete", {"Authorization": "Bearer test"}) == 204
    assert sleeps == [1.0, 2.0]

    monkeypatch.setattr(run.requests, "delete", lambda *_args, **_kwargs: _response(400, text="bad\nbody"))
    with pytest.raises(run.ActionError, match="bad body"):
        run._github_delete("https://api.github.test/delete", {})


def test_github_pagination_helpers_filter_and_validate_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_pages = [
        {"workflow_runs": [{"id": 1}, {"id": 2}, "bad"]},
        {"workflow_runs": []},
    ]
    artifact_pages = [
        {
            "artifacts": [
                {"id": 10, "workflow_run": {"id": 1}, "created_at": "2026-06-01T00:00:00Z"},
                {"id": 11, "workflow_run": {"id": 99}, "created_at": "2026-06-02T00:00:00Z"},
                {"id": "bad"},
            ]
        },
        {"artifacts": []},
    ]

    def fake_fetch(url: str, _headers: dict[str, str]) -> Any:
        if "/runs" in url:
            return workflow_pages.pop(0)
        return artifact_pages.pop(0)

    monkeypatch.setattr(run, "_github_fetch_json", fake_fetch)

    assert run._list_workflow_run_ids("demo", "repo", 5, current_run_id=2, headers={}) == [1]
    artifacts = run._list_old_dashboard_data_artifacts("demo", "repo", current_run_id=99, headers={})
    assert artifacts == [
        run.DashboardDataArtifactRef(
            artifact_id=10,
            workflow_run_id=1,
            created_at="2026-06-01T00:00:00Z",
        )
    ]

    monkeypatch.setattr(run, "_github_fetch_json", lambda *_args, **_kwargs: [])
    with pytest.raises(run.ActionError, match="unexpected workflow-runs"):
        run._list_workflow_run_ids("demo", "repo", 5, current_run_id=2, headers={})


def _response(
    status: int,
    *,
    text: str = "",
) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = text.encode("utf-8")
    response.url = "https://api.github.test/example"
    return response


def _config_for_run_tests(tmp_path: Path, **overrides: Any) -> run.RuntimeConfig:
    values: dict[str, Any] = {
        "mode": "collect",
        "collection_token": "ghp_collection",
        "use_github_app": False,
        "github_token": "",
        "dashboard_secret": "dashboard-secret-" + ("x" * 40),
        "dashboard_next_secret": "",
        "privacy_mode": "plain",
        "repo_is_public": False,
        "config_path": tmp_path / "config.yaml",
        "data_dir": tmp_path / "data",
        "retention_days": 90,
        "artifact_run_id": "",
        "publish_pages_requested": True,
        "generate_readme": False,
        "allow_docs_sync": True,
        "pages_index_path": tmp_path / "docs" / "index.html",
        "readme_path": tmp_path / "README.md",
        "incident_confirm_mode": "",
        "incident_confirm_purge": "",
        "incident_confirm_irreversible": "",
        "action_ref": "v0.2.0",
        "action_repository": "reponomics/reponomics-dashboard-action",
    }
    values.update(overrides)
    return run.RuntimeConfig(**values)
