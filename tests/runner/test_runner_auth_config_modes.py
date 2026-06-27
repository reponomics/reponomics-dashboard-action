from __future__ import annotations

import csv
import subprocess
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
    _write_runtime_config,
)


def test_validate_token_401_points_to_fine_grained_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_get(
        _url: str,
        *,
        headers: run.collect_mod.Headers,
        timeout: int,
    ) -> requests.Response:
        return _response(401)

    monkeypatch.setattr(run.collect_mod, "_perform_get", fake_get)

    with pytest.raises(SystemExit):
        run.collect_mod.validate_token({})

    output = capsys.readouterr().out
    assert "fine-grained personal access token" in output
    assert "personal-access-tokens/new" in output
    assert "name=COLLECTION_TOKEN" in output
    assert "name=Reponomics%20Collection%20Token" not in output
    assert "administration=read" in output


def test_validate_token_403_names_required_permission(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_get(
        _url: str,
        *,
        headers: run.collect_mod.Headers,
        timeout: int,
    ) -> requests.Response:
        return _response(403)

    monkeypatch.setattr(run.collect_mod, "_perform_get", fake_get)

    with pytest.raises(SystemExit):
        run.collect_mod.validate_token({})

    output = capsys.readouterr().out
    assert "COLLECTION_TOKEN lacks required permissions" in output
    assert "Administration: read" in output


def test_validate_token_github_app_uses_installation_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen_url = ""

    def fake_get(
        url: str,
        *,
        headers: run.collect_mod.Headers,
        timeout: int,
    ) -> requests.Response:
        nonlocal seen_url
        seen_url = url
        return _response(200, payload={"total_count": 0, "repositories": []})

    monkeypatch.setattr(run.collect_mod, "_perform_get", fake_get)
    monkeypatch.setenv("REPONOMICS_USE_GITHUB_APP", "true")

    run.collect_mod.validate_token({})

    output = capsys.readouterr().out
    assert seen_url.startswith("https://api.github.com/installation/repositories")
    assert "Authenticated as GitHub App installation token" in output


def test_validate_token_reports_network_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary_path = tmp_path / "summary.md"

    def fake_get(
        _url: str,
        *,
        headers: run.collect_mod.Headers,
        timeout: int,
    ) -> requests.Response:
        raise requests.ConnectionError("offline")

    monkeypatch.setenv("GITHUB_STEP_SUMMARY", summary_path.as_posix())
    monkeypatch.setattr(run.collect_mod, "_perform_get", fake_get)

    with pytest.raises(SystemExit):
        run.collect_mod.validate_token({})

    output = capsys.readouterr().out
    assert "could not reach GitHub API" in output
    summary = summary_path.read_text(encoding="utf-8")
    assert "- Outcome: **failed**" in summary
    assert "token validation" in summary
    assert "Network Warnings" in summary


@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    [
        (401, {"repositories": []}, "installation token is invalid or expired"),
        (403, {"repositories": []}, "installation token lacks required permissions"),
        (500, {"repositories": []}, "status 500"),
        (200, [], "was not a JSON object"),
        (200, {"total_count": 0}, "did not include a repositories list"),
    ],
)
def test_validate_token_github_app_rejects_invalid_validation_responses(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: int,
    payload: Any,
    expected: str,
) -> None:
    def fake_get(
        _url: str,
        *,
        headers: run.collect_mod.Headers,
        timeout: int,
    ) -> requests.Response:
        return _response(status, payload=payload)

    monkeypatch.setattr(run.collect_mod, "_perform_get", fake_get)

    with pytest.raises(SystemExit):
        run.collect_mod.validate_token({}, use_github_app=True)

    assert expected in capsys.readouterr().out


def test_get_headers_reports_missing_token_for_github_app(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("REPONOMICS_USE_GITHUB_APP", "true")

    with pytest.raises(SystemExit):
        run.collect_mod.get_headers()

    output = capsys.readouterr().out
    assert "GH_TOKEN environment variable is not set" in output
    assert "GitHub App installation token" in output


def test_get_headers_returns_expected_github_api_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "ghs_installation")

    assert run.collect_mod.get_headers() == {
        "Authorization": "Bearer ghs_installation",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
    }


@pytest.mark.parametrize(
    ("github_event_repository_private", "expected_repo_is_public"),
    [
        ("false", True),
        ("true", False),
    ],
)
def test_input_normalization_from_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    github_event_repository_private: str,
    expected_repo_is_public: bool,
) -> None:
    monkeypatch.setenv("REPONOMICS_MODE", "collect")
    monkeypatch.setenv("REPONOMICS_COLLECTION_TOKEN", "ghp_collection")
    monkeypatch.setenv("REPONOMICS_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("REPONOMICS_DASHBOARD_SECRET", OLD_KEY)
    monkeypatch.setenv("REPONOMICS_DATA_MODE", "encrypted")
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", github_event_repository_private)
    config_path = tmp_path / "config.yaml"
    _write_runtime_config(config_path, artifact_retention_days=30)
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("REPONOMICS_RETENTION_DAYS", "30")
    monkeypatch.setenv("REPONOMICS_GENERATE_README", "false")
    monkeypatch.setenv("REPONOMICS_README_PATH", str(tmp_path / "README.md"))

    config = run.load_config_from_env()

    assert config.mode == "collect"
    assert config.collection_token == "ghp_collection"
    assert config.use_github_app is False
    assert config.github_token == "ghp_test"
    assert config.data_dir == Path("data")
    assert config.pages_index_path == Path("docs/index.html")
    assert config.data_mode == "encrypted"
    assert config.repo_is_public is expected_repo_is_public
    assert config.resolved_data_mode == "encrypted"
    assert config.publish_pages is True
    assert config.retention_days == 30
    assert config.auto_doctor_every_n_days == 0
    assert config.generate_readme is False


def test_use_github_app_input_normalization_from_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("REPONOMICS_MODE", "collect")
    monkeypatch.setenv("REPONOMICS_COLLECTION_TOKEN", "ghs_installation_token")
    monkeypatch.setenv("REPONOMICS_USE_GITHUB_APP", "true")
    monkeypatch.setenv("REPONOMICS_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("REPONOMICS_DASHBOARD_SECRET", OLD_KEY)
    monkeypatch.setenv("REPONOMICS_DATA_MODE", "encrypted")
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    config_path = tmp_path / "config.yaml"
    _write_runtime_config(
        config_path,
        artifact_retention_days=30,
        use_github_app=True,
    )
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("REPONOMICS_RETENTION_DAYS", "30")
    monkeypatch.setenv("REPONOMICS_GENERATE_README", "false")
    monkeypatch.setenv("REPONOMICS_README_PATH", str(tmp_path / "README.md"))

    config = run.load_config_from_env()

    assert config.use_github_app is True


def test_auto_doctor_every_n_days_uses_config_and_defaults_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_runtime_config(config_path, auto_doctor_every_n_days=14)
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(config_path))

    assert run.load_config_from_env().auto_doctor_every_n_days == 14

    config_path.write_text(
        "\n".join(
            line
            for line in config_path.read_text(encoding="utf-8").splitlines()
            if not line.startswith("auto_doctor_every_n_days:")
        )
        + "\n",
        encoding="utf-8",
    )

    assert run.load_config_from_env().auto_doctor_every_n_days == 0


@pytest.mark.parametrize("value", [-1, 31, "weekly", True])
def test_auto_doctor_every_n_days_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    value: Any,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_runtime_config(config_path, auto_doctor_every_n_days=value)
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(config_path))

    with pytest.raises(run.ActionError, match="auto_doctor_every_n_days"):
        run.load_config_from_env()


@pytest.mark.parametrize(
    (
        "data_mode",
        "publish_pages_requested",
        "expected_data_mode",
        "expected_publish_pages",
    ),
    [
        ("encrypted", True, "encrypted", True),
        ("encrypted", False, "encrypted", False),
        ("plaintext", True, "plaintext", False),
        ("plaintext", False, "plaintext", False),
    ],
)
def test_publish_pages_values_follow_data_mode(
    tmp_path: Path,
    data_mode: str,
    publish_pages_requested: bool,
    expected_data_mode: str,
    expected_publish_pages: bool,
) -> None:
    config = _config(
        tmp_path,
        data_mode=data_mode,
        publish_pages_requested=publish_pages_requested,
        dashboard_secret="" if data_mode == "plaintext" else OLD_KEY,
    )

    assert config.resolved_data_mode == expected_data_mode
    assert config.publish_pages is expected_publish_pages


def test_publish_pages_input_normalization_from_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("REPONOMICS_MODE", "publish")
    monkeypatch.setenv("REPONOMICS_COLLECTION_TOKEN", "ghp_collection")
    monkeypatch.setenv("REPONOMICS_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("REPONOMICS_DASHBOARD_SECRET", OLD_KEY)
    monkeypatch.setenv("REPONOMICS_DATA_MODE", "encrypted")
    monkeypatch.setenv("REPONOMICS_PUBLISH_PAGES", "false")
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    config_path = tmp_path / "config.yaml"
    _write_runtime_config(
        config_path,
        artifact_retention_days=30,
        publish_pages_dashboard=False,
    )
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("REPONOMICS_RETENTION_DAYS", "30")
    monkeypatch.setenv("REPONOMICS_GENERATE_README", "false")
    monkeypatch.setenv("REPONOMICS_README_PATH", str(tmp_path / "README.md"))

    config = run.load_config_from_env()

    assert config.publish_pages_requested is False
    assert config.publish_pages is False


def test_generate_readme_uses_config_when_input_is_unset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_runtime_config(config_path, publish_readme_dashboard=False)
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "false")
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("REPONOMICS_GENERATE_README", raising=False)

    config = run.load_config_from_env()

    assert config.generate_readme is False


def test_runtime_config_requires_config_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(tmp_path / "missing.yaml"))

    with pytest.raises(run.ActionError, match="Required config file is missing"):
        run.load_config_from_env()


def test_runtime_config_requires_setup_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """collect:
  repositories:
    - demo/reponomics
publish:
  repositories:
    - demo/reponomics
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(config_path))

    with pytest.raises(run.ActionError, match="missing explicit decision field"):
        run.load_config_from_env()


def test_runtime_config_defaults_optional_config_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_runtime_config(config_path)
    config_path.write_text(
        "\n".join(
            line
            for line in config_path.read_text(encoding="utf-8").splitlines()
            if not line.startswith(("artifact_retention_days:", "use_github_app:"))
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(config_path))

    config = run.load_config_from_env()

    assert config.retention_days == 90
    assert config.use_github_app is False


def test_runtime_config_rejects_duplicate_setup_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_runtime_config(config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8") + "data_mode: plaintext\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(config_path))

    with pytest.raises(run.ActionError, match="duplicate key 'data_mode'"):
        run.load_config_from_env()


def test_runtime_config_rejects_non_string_top_level_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_runtime_config(config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8") + "123: unexpected\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(config_path))

    with pytest.raises(run.ActionError, match="top-level keys must be strings"):
        run.load_config_from_env()


@pytest.mark.parametrize(
    ("env_name", "env_value", "config_override", "expected"),
    [
        ("REPONOMICS_DATA_MODE", "plaintext", {}, "data-mode"),
        ("REPONOMICS_RETENTION_DAYS", "30", {}, "retention-days"),
        ("REPONOMICS_PUBLISH_PAGES", "false", {}, "publish-pages"),
        ("REPONOMICS_GENERATE_README", "true", {}, "generate-readme"),
        ("REPONOMICS_USE_GITHUB_APP", "true", {}, "use-github-app"),
    ],
)
def test_runtime_config_rejects_input_config_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    env_name: str,
    env_value: str,
    config_override: dict[str, Any],
    expected: str,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_runtime_config(config_path, **config_override)
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(config_path))
    monkeypatch.setenv(env_name, env_value)

    with pytest.raises(run.ActionError, match=expected):
        run.load_config_from_env()


def test_runtime_outputs_include_pages_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "github-output.txt"
    config = _config(tmp_path)
    _seed_log(config.data_dir)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    run._write_outputs(config, {"readme": "", "dashboard": ""})

    output = output_path.read_text(encoding="utf-8")
    assert "publish-pages=true" in output
    assert f"pages-path={config.pages_index_path.parent.as_posix()}" in output
    assert "update-docs-reason=" not in output
    assert "docs-action-version=" in output
    assert "docs-updated-at=" in output


def test_generate_readme_stages_readme_and_svg_assets_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []
    config = _config(tmp_path, generate_readme=True)
    assets_dir = config.pages_index_path.parent / "assets"
    assets_dir.mkdir(parents=True)
    svg_asset = assets_dir / "hero-stats.svg"
    light_svg_asset = assets_dir / "hero-stats-light.svg"
    chart_asset = assets_dir / "chart.umd.min.js"
    export_asset = assets_dir / "export-data-deadbeefdeadbeef.enc"
    svg_asset.write_text("<svg />", encoding="utf-8")
    light_svg_asset.write_text("<svg />", encoding="utf-8")
    chart_asset.write_text("chart", encoding="utf-8")
    export_asset.write_bytes(b"ciphertext")

    def fake_run(args, **kwargs):
        calls.append(list(args))
        if list(args) == ["git", "rev-parse", "--is-inside-work-tree"]:
            return subprocess.CompletedProcess(args, 0, stdout="true", stderr="")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(run.subprocess, "run", fake_run)

    run._git_commit_readme(config, "chore: test")

    assert [
        "git",
        "add",
        config.readme_path.as_posix(),
        light_svg_asset.as_posix(),
        svg_asset.as_posix(),
    ] in calls
    assert all(config.pages_index_path.as_posix() not in call for call in calls)
    assert all(chart_asset.as_posix() not in call for call in calls)
    assert all(export_asset.as_posix() not in call for call in calls)


def test_update_docs_mode_writes_outputs_and_commits_managed_namespace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []
    output_path = tmp_path / "github-output.txt"
    summary_path = tmp_path / "summary.md"
    config = _config(tmp_path, mode="update-docs")

    def fake_run(args, **kwargs):
        command = list(args)
        calls.append(command)
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return subprocess.CompletedProcess(args, 0, stdout="true", stderr="")
        if command == ["git", "diff", "--cached", "--quiet", "--", "docs/reponomics"]:
            return subprocess.CompletedProcess(args, 1)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    monkeypatch.setattr(run.subprocess, "run", fake_run)

    run.run_update_docs(config)

    output = output_path.read_text(encoding="utf-8")
    summary = summary_path.read_text(encoding="utf-8")
    assert (tmp_path / "docs" / "reponomics" / "README.md").is_file()
    assert (tmp_path / "docs" / "reponomics" / ".manifest.json").is_file()
    assert "update-docs-state=written" in output
    assert f"docs-action-version={run.VERSION}" in output
    assert "docs-updated-at=" in output
    assert "Managed Reponomics docs" in summary
    assert ["git", "add", "--", "docs/reponomics"] in calls
    assert any(
        command[:3] == ["git", "commit", "-m"] and command[-2:] == ["--", "docs/reponomics"]
        for command in calls
    )
    assert ["git", "push"] in calls


def test_update_docs_mode_reports_permission_missing_for_push_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "github-output.txt"
    config = _config(tmp_path, mode="update-docs")

    def fake_run(args, **kwargs):
        command = list(args)
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return subprocess.CompletedProcess(args, 0, stdout="true", stderr="")
        if command == ["git", "diff", "--cached", "--quiet", "--", "docs/reponomics"]:
            return subprocess.CompletedProcess(args, 1)
        if command == ["git", "push"]:
            raise subprocess.CalledProcessError(1, args, stderr="remote: Permission denied 403")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    monkeypatch.setattr(run.subprocess, "run", fake_run)

    run.run_update_docs(config)

    output = output_path.read_text(encoding="utf-8")
    assert "update-docs-state=permission_missing" in output
    assert "update-docs-reason=" not in output
    assert f"docs-action-version={run.VERSION}" in output


def test_bootstrap_creates_empty_data_files_and_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setattr(run.bootstrap, "DATA_DIR", data_dir.as_posix())

    run.bootstrap.bootstrap()
    run.bootstrap.bootstrap()

    assert (data_dir / "manifest.json").exists()
    for filename, (fieldnames, _date_field) in run.storage.CSV_REGISTRY.items():
        path = data_dir / filename
        assert path.exists()
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            assert next(reader) == fieldnames
            assert list(reader) == []


def test_registered_csvs_have_lineage_identity_and_primary_date_fields() -> None:
    assert set(run.storage.CSV_REGISTRY) == set(run.lineage.ROW_IDENTITY_FIELDS)

    for filename, (fieldnames, date_field) in run.storage.CSV_REGISTRY.items():
        assert date_field in fieldnames, filename
        for identity_field in run.lineage.ROW_IDENTITY_FIELDS[filename]:
            assert identity_field in fieldnames, filename


def test_invalid_mode_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPONOMICS_MODE", "setup")

    with pytest.raises(run.ActionError):
        run.load_config_from_env()


def test_public_plaintext_data_mode_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, data_mode="plaintext", repo_is_public=True)

    with pytest.raises(
        run.ActionError, match="plaintext is only supported for private repositories"
    ):
        run.validate_config(config)


def test_encrypted_collect_requires_non_empty_secret(tmp_path: Path) -> None:
    config = _config(tmp_path, dashboard_secret="")

    with pytest.raises(run.ActionError):
        run.validate_config(config)


def test_collect_requires_github_token_before_upload(tmp_path: Path) -> None:
    config = _config(tmp_path, github_token="")

    with pytest.raises(run.ActionError, match="github-token"):
        run.validate_config(config)


def test_encrypted_data_mode_allows_short_non_empty_secret(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        dashboard_secret="too-short",
        data_mode="encrypted",
    )

    run.validate_config(config)


def test_secret_validation_for_rotate_key(tmp_path: Path) -> None:
    config = _config(tmp_path, mode="rotate-key", dashboard_next_secret="")

    with pytest.raises(run.ActionError):
        run.validate_config(config)


def test_incident_reset_requires_confirmations(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        mode="incident-reset",
        dashboard_next_secret=NEXT_KEY,
    )

    with pytest.raises(run.ActionError, match="incident-confirm-mode"):
        run.validate_config(config)


def test_incident_reset_requires_next_secret_confirmation(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        mode="incident-reset",
        dashboard_next_secret=NEXT_KEY,
        incident_confirm_mode=run.INCIDENT_CONFIRM_MODE,
        incident_confirm_purge=run.INCIDENT_CONFIRM_PURGE,
        incident_confirm_irreversible=run.INCIDENT_CONFIRM_IRREVERSIBLE,
    )

    with pytest.raises(run.ActionError, match="incident-confirm-next-secret"):
        run.validate_config(config)


def test_incident_reset_validation_accepts_confirmed_inputs(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        mode="incident-reset",
        dashboard_next_secret=NEXT_KEY,
        incident_confirm_mode=run.INCIDENT_CONFIRM_MODE,
        incident_confirm_purge=run.INCIDENT_CONFIRM_PURGE,
        incident_confirm_next_secret=run.INCIDENT_CONFIRM_NEXT_SECRET,
        incident_confirm_irreversible=run.INCIDENT_CONFIRM_IRREVERSIBLE,
    )

    run.validate_config(config)
