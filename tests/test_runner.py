from __future__ import annotations

import base64
import csv
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
import zipfile

import pytest
import requests

from dashboard_action import run


OLD_KEY = "old-dashboard-secret-" + ("x" * 40)
NEXT_KEY = "next-dashboard-secret-" + ("y" * 40)
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class DashboardHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[dict[str, str | None]] = []
        self.canvases: set[str] = set()
        self.forms: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script":
            self.scripts.append(attributes)
        elif tag == "canvas" and attributes.get("id"):
            self.canvases.add(str(attributes["id"]))
        elif tag == "form" and attributes.get("id"):
            self.forms.add(str(attributes["id"]))


def _parse_dashboard_html(html: str) -> DashboardHtmlParser:
    parser = DashboardHtmlParser()
    parser.feed(html)
    return parser


def _script_json(html: str, script_id: str) -> dict[str, Any]:
    match = re.search(
        rf'<script id="{re.escape(script_id)}" type="application/json">(.*?)</script>',
        html,
        flags=re.S,
    )
    if not match:
        raise AssertionError(f"missing script payload for {script_id}")
    return json.loads(match.group(1))


def _config(tmp_path: Path, **overrides) -> run.RuntimeConfig:
    values: dict[str, Any] = {
        "mode": "collect",
        "traffic_token": "ghp_traffic",
        "github_token": "ghp_test",
        "dashboard_secret": OLD_KEY,
        "dashboard_next_secret": "",
        "privacy_mode": "strong",
        "repo_is_public": False,
        "config_path": tmp_path / "config.yaml",
        "data_dir": tmp_path / "data",
        "retention_days": 90,
        "generate_readme": False,
        "dashboard_path": tmp_path / "docs" / "index.html",
        "readme_path": tmp_path / "README.md",
        "update_notices": False,
        "incident_confirm_mode": "",
        "incident_confirm_purge": "",
        "incident_confirm_irreversible": "",
        "action_ref": "v0.1.0",
        "action_repository": "reponomics/reponomics-dashboard-action",
    }
    values.update(overrides)
    return run.RuntimeConfig(**values)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _seed_log(data_dir: Path) -> None:
    _write_csv(
        data_dir / "traffic-log.csv",
        run.storage.LOG_FIELDS,
        [
            {
                "repo": "demo/reponomics",
                "ts": "2026-05-01",
                "views_count": "12",
                "views_uniques": "7",
                "clones_count": "3",
                "clones_uniques": "2",
                "captured_at": "2026-05-01T12:00:00Z",
                "source": "fixture",
                "schema_version": run.storage.SCHEMA_VERSION,
            }
        ],
    )
    _write_csv(
        data_dir / "traffic-referrers.csv",
        run.storage.REFERRER_FIELDS,
        [
            {
                "repo": "demo/reponomics",
                "captured_at": "2026-05-01T12:00:00Z",
                "referrer": "github.com",
                "count": "5",
                "uniques": "3",
                "schema_version": run.storage.SCHEMA_VERSION,
            }
        ],
    )
    _write_csv(
        data_dir / "traffic-paths.csv",
        run.storage.PATH_FIELDS,
        [
            {
                "repo": "demo/reponomics",
                "captured_at": "2026-05-01T12:00:00Z",
                "path": "/demo/reponomics",
                "title": "Repository overview",
                "count": "8",
                "uniques": "4",
                "schema_version": run.storage.SCHEMA_VERSION,
            }
        ],
    )
    _write_csv(
        data_dir / "repo-metrics.csv",
        run.storage.REPO_METRIC_FIELDS,
        [
            {
                "repo": "demo/reponomics",
                "repo_id": "123",
                "node_id": "R_123",
                "ts": "2026-05-01",
                "captured_at": "2026-05-01T12:00:00Z",
                "stargazers_count": "11",
                "subscribers_count": "2",
                "forks_count": "1",
                "open_issues_count": "4",
                "size_kb": "512",
                "created_at": "2025-01-01T00:00:00Z",
                "pushed_at": "2026-05-01T11:00:00Z",
                "updated_at": "2026-05-01T11:30:00Z",
                "language": "Python",
                "visibility": "public",
                "default_branch": "main",
                "has_pages": "False",
                "has_discussions": "True",
                "archived": "False",
                "disabled": "False",
                "source": "fixture",
                "schema_version": run.storage.SCHEMA_VERSION,
            }
        ],
    )


def _daily_row(repo: str, ts: str, views: int, visitors: int, clones: int = 0) -> dict[str, str]:
    return {
        "repo": repo,
        "ts": ts,
        "views_count": str(views),
        "views_uniques": str(visitors),
        "clones_count": str(clones),
        "clones_uniques": str(min(clones, visitors)),
        "captured_at": f"{ts}T12:00:00Z",
        "source": "fixture",
        "schema_version": run.storage.SCHEMA_VERSION,
    }


def _metric_row(
    repo: str,
    ts: str,
    stars: int,
    subscribers: int,
    forks: int,
    captured_suffix: str = "12:00:00Z",
) -> dict[str, str]:
    return {
        "repo": repo,
        "repo_id": "",
        "node_id": "",
        "ts": ts,
        "captured_at": f"{ts}T{captured_suffix}",
        "stargazers_count": str(stars),
        "subscribers_count": str(subscribers),
        "forks_count": str(forks),
        "open_issues_count": "",
        "size_kb": "",
        "created_at": "",
        "pushed_at": "",
        "updated_at": "",
        "language": "",
        "visibility": "",
        "default_branch": "",
        "has_pages": "",
        "has_discussions": "",
        "archived": "",
        "disabled": "",
        "source": "fixture",
        "schema_version": run.storage.SCHEMA_VERSION,
    }


def _copy_fixture(name: str, tmp_path: Path) -> Path:
    src = FIXTURES_DIR / name
    dst = tmp_path / name
    shutil.copytree(src, dst)
    return dst


def _response(
    status: int,
    *,
    text: str = "",
    headers: dict[str, str] | None = None,
    payload: Any | None = None,
) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.headers.update(headers or {})
    body = json.dumps(payload) if payload is not None else text
    response._content = body.encode("utf-8")
    response.url = "https://api.github.test/example"
    return response


@pytest.mark.parametrize(
    (
        "github_event_repository_private",
        "expected_repo_is_public",
        "expected_readme_dashboard",
    ),
    [
        ("false", True, "disabled"),
        ("true", False, "enabled"),
    ],
)
def test_input_normalization_from_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    github_event_repository_private: str,
    expected_repo_is_public: bool,
    expected_readme_dashboard: str,
) -> None:
    monkeypatch.setenv("REPONOMICS_MODE", "collect")
    monkeypatch.setenv("REPONOMICS_TRAFFIC_TOKEN", "ghp_traffic")
    monkeypatch.setenv("REPONOMICS_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("REPONOMICS_DASHBOARD_SECRET", OLD_KEY)
    monkeypatch.setenv("REPONOMICS_PRIVACY_MODE", "strong")
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", github_event_repository_private)
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    monkeypatch.setenv("REPONOMICS_RETENTION_DAYS", "30")
    monkeypatch.setenv("REPONOMICS_GENERATE_README", "false")
    monkeypatch.setenv("REPONOMICS_README_PATH", str(tmp_path / "README.md"))

    config = run.load_config_from_env()

    assert config.mode == "collect"
    assert config.traffic_token == "ghp_traffic"
    assert config.github_token == "ghp_test"
    assert config.data_dir == Path("data")
    assert config.dashboard_path == Path("docs/index.html")
    assert config.privacy_mode == "strong"
    assert config.repo_is_public is expected_repo_is_public
    assert config.resolved_artifact_mode == "encrypted"
    assert config.normalized_pages_dashboard == "encrypted"
    assert config.normalized_readme_dashboard == expected_readme_dashboard
    assert config.retention_days == 30
    assert config.generate_readme is False

def test_generate_readme_default_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REPONOMICS_GENERATE_README", raising=False)

    config = run.load_config_from_env()

    assert config.generate_readme is False


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
    assert f"pages-path={config.dashboard_path.parent.as_posix()}" in output


def test_generate_readme_stages_only_readme(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []
    config = _config(tmp_path, generate_readme=True)

    def fake_run(args, **kwargs):
        calls.append(list(args))
        if list(args) == ["git", "rev-parse", "--is-inside-work-tree"]:
            return subprocess.CompletedProcess(args, 0, stdout="true", stderr="")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(run.subprocess, "run", fake_run)

    run._git_commit_readme(config, "chore: test")

    assert ["git", "add", config.readme_path.as_posix()] in calls
    assert all(config.dashboard_path.as_posix() not in call for call in calls)
    assert all((config.dashboard_path.parent / "assets").as_posix() not in call for call in calls)


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


def test_invalid_mode_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPONOMICS_MODE", "setup")

    with pytest.raises(run.ActionError):
        run.load_config_from_env()


def test_legacy_privacy_mode_aliases_are_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "false")
    monkeypatch.setenv("REPONOMICS_ARTIFACT_SECURITY_MODE", "encrypted")

    config = run.load_config_from_env()

    assert config.privacy_mode == "strong"
    assert config.resolved_artifact_mode == "encrypted"


def test_public_plain_privacy_mode_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, privacy_mode="plain", repo_is_public=True)

    with pytest.raises(run.ActionError, match="plain is only supported for private repositories"):
        run.validate_config(config)


def test_secret_validation_for_encrypted_collect(tmp_path: Path) -> None:
    config = _config(tmp_path, dashboard_secret="too-short")

    with pytest.raises(run.ActionError):
        run.validate_config(config)


def test_casual_privacy_mode_allows_low_entropy_secret(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        dashboard_secret="too-short",
        privacy_mode="casual",
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


def test_incident_reset_validation_accepts_confirmed_inputs(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        mode="incident-reset",
        dashboard_next_secret=NEXT_KEY,
        incident_confirm_mode=run.INCIDENT_CONFIRM_MODE,
        incident_confirm_purge=run.INCIDENT_CONFIRM_PURGE,
        incident_confirm_irreversible=run.INCIDENT_CONFIRM_IRREVERSIBLE,
    )

    run.validate_config(config)


def test_collect_fixture_updates_artifact_without_rendering_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path)
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_collect(config, restore_artifact=False, execute_collect=False)

    assert (tmp_path / ".traffic-artifact" / "traffic-data.enc").exists()
    assert not config.readme_path.exists()
    assert not config.dashboard_path.exists()


def test_publish_fixture_renders_outputs_without_live_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish", generate_readme=True)
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    assert config.readme_path.exists()
    assert config.dashboard_path.exists()
    assert "demo/reponomics" in config.readme_path.read_text(encoding="utf-8")
    dashboard = config.dashboard_path.read_text(encoding="utf-8")
    assert "encrypted-payload" in dashboard
    assert "export-manifest" in dashboard
    assert 'id="export-button"' in dashboard
    assert 'id="export-hash-button"' in dashboard
    assert "How download verification works" in dashboard
    assert "validateEncryptedPayload" in dashboard
    assert "EXPECTED_KDF_ITERATIONS = 300000" in dashboard
    assert 'src="assets/chart.umd.min.js"' in dashboard
    assert "cdn.jsdelivr.net" not in dashboard
    assert (config.dashboard_path.parent / "assets" / "chart.umd.min.js").exists()
    assert len(list((config.dashboard_path.parent / "assets").glob("export-data-*.enc"))) == 1


def test_publish_skips_readme_when_generate_readme_is_false(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish", generate_readme=False)
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    assert not config.readme_path.exists()
    assert config.dashboard_path.exists()


def test_publish_fixture_renders_growth_metrics_in_readme_and_encrypted_dashboard_shell(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish", generate_readme=True)
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    readme = config.readme_path.read_text(encoding="utf-8")
    dashboard = config.dashboard_path.read_text(encoding="utf-8")

    assert "Growth (14d)" in readme
    assert "interest **+0 stars** / **+0 watchers** (now 11 / 2)" in readme
    assert "adoption **3 clones** / **+0 forks** (now 1)" in readme
    assert "Repository Growth" in readme
    assert "encrypted-payload" in dashboard
    assert "Reponomics Dashboard" in dashboard
    assert 'h1 class="brand">reponomics<span class="accent">.</span></h1>' in dashboard
    assert "data:font/woff2;base64," in dashboard
    assert "fonts.googleapis.com" not in dashboard
    assert 'data-window="7"' in dashboard
    assert 'data-window="14"' in dashboard
    assert 'data-window="30"' in dashboard
    assert 'data-window="90"' in dashboard
    assert 'data-window="all"' in dashboard
    assert "params.set('window', getSelectedWindow())" in dashboard
    assert "range === 'recent'" in dashboard
    assert "range === 'all'" in dashboard
    assert 'src="assets/chart.umd.min.js"' in dashboard
    assert "cdn.jsdelivr.net" not in dashboard
    assert "Attention" in dashboard
    assert "Interest" in dashboard
    assert "Adoption" in dashboard
    assert "Star Growth" in dashboard
    assert "Watcher Growth" in dashboard
    assert "Fork Growth" in dashboard
    assert '"total_subscribers":2' not in dashboard
    assert '"total_forks_delta":0' not in dashboard


def test_publish_writes_encrypted_export_asset_with_canonical_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish")
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    dashboard = config.dashboard_path.read_text(encoding="utf-8")
    export_manifest = _script_json(dashboard, "export-manifest")
    assert export_manifest["version"] == 1
    assert export_manifest["cipher"] == "AES-GCM"
    assert export_manifest["kdf"] == {
        "name": "PBKDF2",
        "hash": "SHA-256",
        "iterations": run.render_dashboard.PBKDF2_ITERATIONS,
    }
    assert re.fullmatch(r"assets/export-data-[a-f0-9]{16}\.enc", export_manifest["asset"])
    assert re.fullmatch(r"[a-f0-9]{64}", export_manifest["plaintext_sha256"])
    assert "traffic-log.csv" not in dashboard
    assert "repo-metrics.csv" not in dashboard

    asset_path = config.dashboard_path.parent / export_manifest["asset"]
    assert asset_path.exists()
    ciphertext = asset_path.read_bytes()
    assert len(ciphertext) == export_manifest["ciphertext_size"]
    assert hashlib.sha256(ciphertext).hexdigest() == export_manifest["ciphertext_sha256"]

    salt = base64.b64decode(export_manifest["salt"])
    iv = base64.b64decode(export_manifest["iv"])
    key = run.render_dashboard._derive_key(OLD_KEY, salt)
    plaintext_bundle = run.render_dashboard.AESGCM(key).decrypt(iv, ciphertext, None)
    assert hashlib.sha256(plaintext_bundle).hexdigest() == export_manifest["plaintext_sha256"]

    expected_files = [*run.storage.CSV_REGISTRY.keys(), "manifest.json"]
    with zipfile.ZipFile(io.BytesIO(plaintext_bundle), mode="r") as archive:
        assert archive.namelist() == expected_files
        for filename in expected_files:
            assert archive.read(filename) == (config.data_dir / filename).read_bytes()


def test_publish_dashboard_html_smoke_test(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish")
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    published = _parse_dashboard_html(config.dashboard_path.read_text(encoding="utf-8"))
    script_sources = [script.get("src") for script in published.scripts if script.get("src")]
    assert script_sources == ["assets/chart.umd.min.js"]
    assert all(not str(src).startswith(("http://", "https://", "//")) for src in script_sources)
    assert {"dailyChart", "weekdayChart", "stackedChart"} <= published.canvases
    assert "unlock-form" in published.forms

    standalone = _parse_dashboard_html(
        (tmp_path / "dist" / "dashboard-standalone.html").read_text(encoding="utf-8")
    )
    assert [script.get("src") for script in standalone.scripts if script.get("src")] == []
    assert {"dailyChart", "weekdayChart", "stackedChart"} <= standalone.canvases


def test_publish_encrypted_unlock_shell_affordances(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish")
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    dashboard = config.dashboard_path.read_text(encoding="utf-8")

    assert '<body class="auth-locked" data-screen-label="Unlock - Encrypted Pages">' in dashboard
    assert 'class="auth-theme-toggle theme-toggle"' in dashboard
    assert 'id="auth-theme-toggle"' in dashboard
    assert "right: calc(env(safe-area-inset-right, 0px) + 1rem);" in dashboard
    assert "document.querySelectorAll('.theme-toggle')" in dashboard

    assert 'class="auth-card-icon"' in dashboard
    assert 'class="auth-mark"' not in dashboard
    assert "max-width: 52ch;" not in dashboard

    assert '<a href="https://github.com/reponomics">Forgot your password?</a>' in dashboard
    assert (
        '<a class="brand-name" href="https://github.com/reponomics">Reponomics</a>'
        in dashboard
    )


def test_publish_encrypted_unlock_failure_throttling_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish")
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    dashboard = config.dashboard_path.read_text(encoding="utf-8")

    expected_runtime_markers = [
        "UNLOCK_ATTEMPT_STORAGE_PREFIX = 'reponomics-unlock-attempts:'",
        "UNLOCK_DELAY_STARTS_AT = 3",
        "UNLOCK_DELAY_BASE_MS = 2000",
        "UNLOCK_DELAY_MAX_MS = 30000",
        "function unlockAttemptStorageKey()",
        "function startUnlockDelay(delayMs, prefix)",
        "localStorage.setItem(unlockAttemptStorageKey(), JSON.stringify(state))",
        "localStorage.removeItem(unlockAttemptStorageKey())",
        "resetUnlockAttemptState();",
        "Too many failed attempts. Try again in ",
        "Wrong dashboard key or corrupted payload. Try again in ",
    ]
    for marker in expected_runtime_markers:
        assert marker in dashboard


def test_publish_dashboard_toolbar_controls_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish")
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    dashboard = config.dashboard_path.read_text(encoding="utf-8")
    snapshot = (FIXTURES_DIR / "dashboard_toolbar_controls.snapshot.html").read_text(
        encoding="utf-8"
    )
    assert snapshot in dashboard


def test_publish_dashboard_toolbar_layout_and_status_regression(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish")
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    dashboard = config.dashboard_path.read_text(encoding="utf-8")
    assert "font-size: clamp(2.75rem, 5.2vw, 3.2rem);" in dashboard
    assert dashboard.count(".theme-toggle .theme-label { display: none; }") == 1
    assert "@media (max-width: 1240px) {" in dashboard
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in dashboard
    assert ".hero-toolbar-controls > .export-verify-tip > summary {" in dashboard
    assert "@media (max-width: 480px) {" in dashboard
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in dashboard
    assert "grid-template-columns: repeat(3, minmax(0, max-content));" not in dashboard
    assert "grid-template-columns: repeat(2, minmax(0, max-content));" not in dashboard
    assert "const useMultiline = rawMessage.includes('\\n');" in dashboard
    assert "setExportStatus('📄 CSV export ready.\\nSHA-256: ' + plaintextSha256, 'success');" in dashboard
    assert "const shaMatch = /SHA-256:\\\\s*([0-9a-f]{16,})/i.exec(rawMessage);" not in dashboard


def test_release_notice_semver_comparison() -> None:
    compare = run.release_notice.compare_semver

    assert compare("v1.2.4", "1.2.3") == 1
    assert compare("1.2.3", "1.2.3") == 0
    assert compare("1.2.3-alpha.2", "1.2.3-alpha.10") == -1
    assert compare("1.2.3", "1.2.3-rc.1") == 1


def test_release_notice_parses_only_constrained_update_block() -> None:
    body = """
    Regular release notes with **markdown**.
    <!-- reponomics-update {"title":"Update <b>now</b>","summary":"Use v0.2.0","min_runtime_version":"0.1.0"} -->
    More arbitrary markdown that must not be rendered.
    """

    parsed = run.release_notice.parse_update_block(body)

    assert parsed == {
        "title": "Update <b>now</b>",
        "summary": "Use v0.2.0",
        "min_runtime_version": "0.1.0",
    }
    assert run.release_notice.parse_update_block("<!-- other {\"title\":\"no\"} -->") is None


def test_release_notice_validation_cli_accepts_valid_block(tmp_path: Path) -> None:
    notes = tmp_path / "release.md"
    notes.write_text(
        "\n".join([
            "# v0.2.0",
            "",
            "<!-- reponomics-update {"
            + "\"title\":\"Upgrade available\","
            + "\"summary\":\"Compatible runtime and artifact migration update.\","
            + "\"min_runtime_version\":\"0.1.0\","
            + "\"action_refs\":[\"v0.1.0\"]"
            + "} -->",
        ]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "scripts/validate_release_notice.py", str(notes)],
        check=False,
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "ok" in result.stdout


def test_release_notice_validation_cli_rejects_malformed_block(tmp_path: Path) -> None:
    notes = tmp_path / "release.md"
    notes.write_text(
        "<!-- reponomics-update {\"title\":\"Missing summary\",\"markdown\":\"**no**\"} -->",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "scripts/validate_release_notice.py", str(notes)],
        check=False,
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "summary is required" in result.stderr
    assert "unsupported reponomics-update key(s): markdown" in result.stderr


def test_release_notice_validation_reports_compatibility_errors() -> None:
    body = "\n".join([
        "<!-- reponomics-update {",
        "\"title\":\"Upgrade available\",",
        "\"summary\":\"Compatible runtime and artifact migration update.\",",
        "\"min_runtime_version\":\"0.3.0\",",
        "\"max_runtime_version\":\"0.2.0\",",
        "\"action_repository\":\"elsewhere/action\",",
        "\"action_refs\":[]",
        "} -->",
    ])

    errors = run.release_notice.validate_update_block(body)

    assert "min_runtime_version must not exceed max_runtime_version" in errors
    assert "action_repository must be reponomics/reponomics-dashboard-action when present" in errors
    assert "action_refs must be '*' or a non-empty list of action ref strings" in errors


def test_release_notice_validation_allows_absent_optional_block() -> None:
    assert run.release_notice.validate_update_block("plain release notes", require_block=False) == []
    assert run.release_notice.validate_update_block("plain release notes") == [
        "missing reponomics-update block"
    ]


def test_release_notice_selects_first_compatible_newer_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    releases = [
        {
            "tag_name": "v0.5.0",
            "draft": False,
            "prerelease": False,
            "body": (
                "<!-- reponomics-update {"
                + "\"title\":\"Future runtime only\","
                + "\"summary\":\"Not for this runtime.\","
                + "\"min_runtime_version\":\"0.5.0\""
                + "} -->"
            ),
        },
        {
            "tag_name": "v0.4.0",
            "draft": True,
            "prerelease": False,
            "body": (
                "<!-- reponomics-update {"
                + "\"title\":\"Draft\","
                + "\"summary\":\"Draft releases are ignored.\""
                + "} -->"
            ),
        },
        {
            "tag_name": "v0.3.0",
            "draft": False,
            "prerelease": False,
            "html_url": "https://malicious.example/release",
            "body": (
                "<!-- reponomics-update {"
                + "\"title\":\"Compatible <b>release</b>\","
                + "\"summary\":\"Use the minor floating tag.\","
                + "\"action_refs\":[\"v0.2\"]"
                + "} -->"
            ),
        },
    ]

    def fake_fetch_releases(_token: str):
        return releases

    monkeypatch.setattr(run.release_notice, "_fetch_releases", fake_fetch_releases)
    notice = run.release_notice.find_update_notice(
        token="",
        current_version="0.2.0",
        action_ref="v0.2",
        action_repository="reponomics/reponomics-dashboard-action",
    )

    assert notice == {
        "version": "v0.3.0",
        "title": "Compatible release",
        "summary": "Use the minor floating tag.",
        "url": "https://github.com/reponomics/reponomics-dashboard-action/releases/tag/v0.3.0",
    }


def test_release_notice_disabled_mode_does_not_call_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    called = False

    def fail_if_called(_token: str):
        nonlocal called
        called = True
        raise AssertionError("release API should not be called")

    monkeypatch.setattr(run.release_notice, "_fetch_releases", fail_if_called)
    config = _config(tmp_path, mode="publish", update_notices=False)

    run._set_update_notice_env(config)

    assert called is False
    assert "REPONOMICS_UPDATE_NOTICE_JSON" not in os.environ


def test_release_notice_api_failure_is_non_fatal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def raise_failure(_token: str):
        raise requests.RequestException("boom")

    monkeypatch.setattr(run.release_notice, "_fetch_releases", raise_failure)
    config = _config(tmp_path, mode="publish", update_notices=True)

    run._set_update_notice_env(config)

    assert "REPONOMICS_UPDATE_NOTICE_JSON" not in os.environ


def test_publish_renders_sanitized_release_notice(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_releases(_token: str):
        return [
            {
                "tag_name": "v0.2.0",
                "name": "Remote **markdown** <script>alert(1)</script>",
                "html_url": "https://github.com/reponomics/reponomics-dashboard-action/releases/tag/v0.2.0",
                "draft": False,
                "prerelease": False,
                "body": (
                    "ignored **markdown**\n"
                    + "<!-- reponomics-update {"
                    + "\"title\":\"Update <script>alert(1)</script>\","
                    + "\"summary\":\"Safe metadata only; no **markdown**\","
                    + "\"min_runtime_version\":\"0.1.0\""
                    + "} -->"
                ),
            }
        ]

    monkeypatch.setattr(run.release_notice, "_fetch_releases", fake_releases)
    config = _config(
        tmp_path,
        mode="publish",
        generate_readme=True,
        update_notices=True,
    )
    _seed_log(config.data_dir)

    run.run_publish(config, restore_artifact=False)

    readme = config.readme_path.read_text(encoding="utf-8")
    dashboard = config.dashboard_path.read_text(encoding="utf-8")
    assert "View v0.2.0" in readme
    assert "View v0.2.0" in dashboard
    assert "Safe metadata only; no markdown" in readme
    assert "ignored **markdown**" not in readme
    assert "alert(1)" not in readme
    assert "alert(1)" not in dashboard
    assert "<script>alert(1)</script>" not in readme
    assert "<script>alert(1)</script>" not in dashboard


def test_private_readme_renders_disabled_metrics_with_notice(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "README.md"
    asset_dir = tmp_path / "docs" / "assets"
    asset_dir.mkdir(parents=True)
    (asset_dir / "old.js").write_text("stale", encoding="utf-8")
    monkeypatch.setattr(run.render_private_readme, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(run.render_private_readme, "ASSET_DIR", asset_dir)
    monkeypatch.setenv("GITHUB_REPOSITORY", "demo/reponomics")
    monkeypatch.setenv("PAGES_DASHBOARD", "encrypted")
    monkeypatch.setenv("ARTIFACT_SECURITY_MODE", "encrypted")
    monkeypatch.setenv(
        "REPONOMICS_UPDATE_NOTICE_JSON",
        json.dumps({
            "version": "v0.3.0",
            "title": "Upgrade <now>",
            "summary": "No **markdown** is rendered.",
            "url": "https://github.com/reponomics/reponomics-dashboard-action/releases/tag/v0.3.0",
        }),
    )

    run.render_private_readme.render()

    readme = output_path.read_text(encoding="utf-8")
    assert not asset_dir.exists()
    assert "README analytics summary: disabled" in readme
    assert "Encrypted dashboard: `https://demo.github.io/reponomics/`" in readme
    assert "Actions data artifact: encrypted" in readme
    assert "Upgrade &lt;now&gt;" in readme
    assert "No **markdown** is rendered." in readme
    assert "View v0.3.0" in readme


def test_dashboard_placeholder_renders_disabled_pages_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "docs" / "index.html"
    monkeypatch.setattr(run.render_dashboard_placeholder, "OUTPUT_PATH", output_path)

    run.render_dashboard_placeholder.render()

    html = output_path.read_text(encoding="utf-8")
    assert "<title>GitHub Traffic Dashboard Disabled</title>" in html
    assert "Dashboard disabled" in html
    assert "No traffic metrics are published here." in html


def test_rotate_key_fixture_reencrypts_with_next_secret(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path)
    _seed_log(config.data_dir)
    run.run_collect(config, restore_artifact=False, execute_collect=False)

    encrypted_path = tmp_path / ".traffic-artifact" / "traffic-data.enc"
    config.data_dir.mkdir(exist_ok=True)
    for path in config.data_dir.iterdir():
        path.unlink()
    (config.data_dir / "traffic-data.enc").write_text(
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
    (rotated.data_dir / "traffic-data.enc").write_text(
        encrypted_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    monkeypatch.setenv("TRAFFIC_DASHBOARD_SECRET", NEXT_KEY)
    run.crypto_artifact.decrypt(
        rotated.data_dir / "traffic-data.enc",
        rotated.data_dir,
        "TRAFFIC_DASHBOARD_SECRET",
    )
    assert (rotated.data_dir / "traffic-daily.csv").exists()

    run.crypto_artifact.encrypt(rotated.data_dir, encrypted_path, "TRAFFIC_DASHBOARD_SECRET")
    for path in rotated.data_dir.iterdir():
        path.unlink()
    (rotated.data_dir / "traffic-data.enc").write_text(
        encrypted_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setenv("TRAFFIC_DASHBOARD_SECRET", OLD_KEY)
    with pytest.raises(Exception):
        run.crypto_artifact.decrypt(
            rotated.data_dir / "traffic-data.enc",
            rotated.data_dir,
            "TRAFFIC_DASHBOARD_SECRET",
        )


def test_purge_workflow_history_deletes_old_runs_and_related_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, mode="incident-reset", dashboard_next_secret=NEXT_KEY)
    monkeypatch.setenv("GITHUB_REPOSITORY", "demo/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "400")
    captured_headers: list[dict[str, str]] = []

    def fake_fetch_json(url: str, headers: dict[str, str], allow_not_found: bool = False) -> Any:
        del allow_not_found
        captured_headers.append(headers)
        if url.endswith("/actions/runs/400"):
            return {"workflow_id": 7}
        if "/actions/workflows/7/runs" in url and "page=1" in url:
            return {"workflow_runs": [{"id": 400}, {"id": 399}, {"id": 398}]}
        if "/actions/workflows/7/runs" in url and "page=2" in url:
            return {"workflow_runs": []}
        if "/actions/artifacts" in url and "page=1" in url:
            return {
                "artifacts": [
                    {"id": 11, "workflow_run": {"id": 399}},
                    {"id": 12, "workflow_run": {"id": 400}},
                    {"id": 13, "workflow_run": {"id": 999}},
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

    deleted_runs, deleted_artifacts = run._purge_workflow_history(config)

    assert deleted_runs == 2
    assert deleted_artifacts == 1
    assert set(deleted_urls) == {
        "https://api.github.com/repos/demo/repo/actions/runs/399",
        "https://api.github.com/repos/demo/repo/actions/runs/398",
        "https://api.github.com/repos/demo/repo/actions/artifacts/11",
    }
    assert captured_headers
    assert all(headers["Authorization"] == f"Bearer {config.github_token}" for headers in captured_headers)


def test_incident_reset_reencrypts_without_rendering_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path)
    _seed_log(config.data_dir)
    run.run_collect(config, restore_artifact=False, execute_collect=False)

    encrypted_path = tmp_path / ".traffic-artifact" / "traffic-data.enc"
    config.data_dir.mkdir(exist_ok=True)
    for path in config.data_dir.iterdir():
        path.unlink()
    (config.data_dir / "traffic-data.enc").write_text(
        encrypted_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    incident = _config(
        tmp_path,
        mode="incident-reset",
        dashboard_next_secret=NEXT_KEY,
        incident_confirm_mode=run.INCIDENT_CONFIRM_MODE,
        incident_confirm_purge=run.INCIDENT_CONFIRM_PURGE,
        incident_confirm_irreversible=run.INCIDENT_CONFIRM_IRREVERSIBLE,
    )
    monkeypatch.setattr(run, "_purge_workflow_history", lambda _config: (0, 0))

    run.validate_config(incident)
    run.run_incident_reset(incident, restore_artifact=False)

    assert not incident.readme_path.exists()
    assert not incident.dashboard_path.exists()

    for path in incident.data_dir.iterdir():
        path.unlink()
    (incident.data_dir / "traffic-data.enc").write_text(
        encrypted_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    monkeypatch.setenv("TRAFFIC_DASHBOARD_SECRET", NEXT_KEY)
    run.crypto_artifact.decrypt(
        incident.data_dir / "traffic-data.enc",
        incident.data_dir,
        "TRAFFIC_DASHBOARD_SECRET",
    )
    assert (incident.data_dir / "traffic-daily.csv").exists()


def test_repo_metrics_registry_creates_growth_snapshot_header(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"

    changed = run.storage.migrate_schema(data_dir.as_posix())

    assert changed is True
    header = (data_dir / "repo-metrics.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == run.storage.REPO_METRIC_FIELDS
    assert run.storage.REPO_METRIC_FIELDS == [
        "repo", "repo_id", "node_id", "ts", "captured_at",
        "stargazers_count", "subscribers_count", "forks_count",
        "open_issues_count", "size_kb", "created_at", "pushed_at",
        "updated_at", "language", "visibility", "default_branch",
        "has_pages", "has_discussions", "archived", "disabled",
        "source", "schema_version",
    ]


def test_repo_metrics_are_mapped_from_detail_without_watchers_count() -> None:
    rows = run.collect_mod.collect_repo_metrics(
        "demo/reponomics",
        {
            "id": 123,
            "node_id": "R_123",
            "stargazers_count": 42,
            "watchers_count": 999,
            "subscribers_count": 7,
            "forks_count": 3,
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
        },
        "2026-05-16T12:00:00Z",
    )

    assert rows == [
        {
            "repo": "demo/reponomics",
            "repo_id": 123,
            "node_id": "R_123",
            "ts": "2026-05-16",
            "captured_at": "2026-05-16T12:00:00Z",
            "stargazers_count": 42,
            "subscribers_count": 7,
            "forks_count": 3,
            "open_issues_count": 4,
            "size_kb": 512,
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
            "source": "repo-detail",
            "schema_version": run.storage.SCHEMA_VERSION,
        }
    ]


def test_collect_retry_after_parses_delta_and_http_date() -> None:
    future = datetime.now(timezone.utc) + timedelta(seconds=30)
    http_date = future.strftime("%a, %d %b %Y %H:%M:%S GMT")

    assert run.collect_mod._parse_retry_after_seconds("2.2") == 3
    parsed_date = run.collect_mod._parse_retry_after_seconds(http_date)
    assert parsed_date is not None
    assert 0 <= parsed_date <= 30
    assert run.collect_mod._parse_retry_after_seconds("not a date") is None


def test_collect_fetch_json_raises_secondary_limit_with_retry_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _response(
        403,
        text="You have exceeded a secondary rate limit",
        headers={"Retry-After": "7"},
    )

    def fake_get(
        url: str,
        headers: run.collect_mod.Headers,
        timeout: int,
    ) -> requests.Response:
        return response

    monkeypatch.setattr(run.collect_mod, "_perform_get", fake_get)

    with pytest.raises(run.collect_mod.SecondaryRateLimitError) as exc_info:
        run.collect_mod.fetch_json("https://api.github.test/traffic", {})

    exc = exc_info.value
    assert exc.retry_after_seconds == 7
    assert exc.retry_source == "Retry-After"
    assert exc.url == "https://api.github.test/traffic"


def test_collect_fetch_json_retries_transient_throttles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        _response(429, text="slow down"),
        _response(500, text="server error"),
        _response(200, payload={"ok": True}),
    ]
    sleeps: list[float] = []

    def fake_get(
        url: str,
        headers: run.collect_mod.Headers,
        timeout: int,
    ) -> requests.Response:
        return responses.pop(0)

    monkeypatch.setattr(run.collect_mod, "_perform_get", fake_get)
    monkeypatch.setattr(run.collect_mod.time, "sleep", sleeps.append)

    assert run.collect_mod.fetch_json("https://api.github.test/repos", {}) == {"ok": True}
    assert len(sleeps) == 2


def test_collect_fetch_json_confirms_not_found_before_skipping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def fake_get(
        url: str,
        headers: run.collect_mod.Headers,
        timeout: int,
    ) -> requests.Response:
        nonlocal attempts
        attempts += 1
        return _response(404, text="missing")

    monkeypatch.setattr(run.collect_mod, "_perform_get", fake_get)
    monkeypatch.setattr(run.collect_mod.time, "sleep", lambda _seconds: None)

    with pytest.raises(run.collect_mod.RepoUnavailableError) as exc_info:
        run.collect_mod.fetch_json(
            "https://api.github.test/repos/demo/repo/traffic/views",
            {},
            allow_not_found=True,
        )

    assert attempts == run.collect_mod.NOT_FOUND_RETRIES + 1
    assert exc_info.value.attempts == attempts


def test_resolve_repositories_applies_stable_auto_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovered: list[run.collect_mod.RepoMetadata] = [
        {
            "full_name": "demo/manual",
            "created_at": "2025-01-01T00:00:00Z",
            "permissions": {"push": True},
        },
        {
            "full_name": "demo/current",
            "created_at": "2025-02-01T00:00:00Z",
            "permissions": {"push": True},
        },
        {
            "full_name": "demo/new",
            "created_at": "2026-02-01T00:00:00Z",
            "permissions": {"push": True},
        },
        {
            "full_name": "demo/private",
            "created_at": "2025-03-01T00:00:00Z",
            "private": True,
            "permissions": {"push": True},
        },
        {
            "full_name": "demo/old-a",
            "created_at": "2025-04-01T00:00:00Z",
            "permissions": {"push": True},
        },
        {
            "full_name": "demo/old-b",
            "created_at": "2025-03-01T00:00:00Z",
            "permissions": {"push": True},
        },
        {
            "full_name": "demo/fork",
            "created_at": "2025-05-01T00:00:00Z",
            "fork": True,
            "permissions": {"push": True},
        },
    ]

    def fake_discover(_headers: run.collect_mod.Headers) -> list[run.collect_mod.RepoMetadata]:
        return discovered

    monkeypatch.setenv("GITHUB_REPOSITORY", "demo/current")
    monkeypatch.setattr(run.collect_mod, "discover_repositories", fake_discover)
    config: dict[str, Any] = {
        "include_only": [],
        "include": ["demo/manual", "demo/missing"],
        "exclude": [],
        "max_repos": 3,
        "include_others": True,
        "include_private": False,
        "include_new": False,
    }
    manifest: dict[str, Any] = {
        "selection_state": {
            "auto_seeded_at": "2026-01-01T00:00:00Z",
            "auto_cutoff_created_at": "",
        }
    }

    resolved, updated_manifest, metadata = run.collect_mod.resolve_repositories(
        {},
        config,
        manifest,
    )

    assert resolved == ["demo/manual", "demo/old-a", "demo/old-b"]
    assert sorted(metadata) == resolved
    assert updated_manifest["selection_state"] == {
        "auto_seeded_at": "2026-01-01T00:00:00Z",
        "auto_cutoff_created_at": "2025-03-01T00:00:00Z",
    }


def test_growth_analytics_totals_deltas_and_visitor_conversion() -> None:
    daily_rows = [
        _daily_row("demo/high", "2026-05-01", 40, 10, 4),
        _daily_row("demo/high", "2026-05-02", 60, 15, 6),
        _daily_row("demo/fallback", "2026-05-02", 12, 0, 1),
    ]
    metric_rows = [
        _metric_row("demo/high", "2026-05-01", 10, 2, 1),
        _metric_row("demo/high", "2026-05-02", 15, 5, 2),
        _metric_row("demo/fallback", "2026-05-01", 1, 0, 0),
        _metric_row("demo/fallback", "2026-05-02", 3, 0, 0),
    ]

    growth = run.load_data.growth_analytics(daily_rows, metric_rows, recent_days=2)

    assert growth["totals"]["total_stargazers"] == 18
    assert growth["totals"]["total_subscribers"] == 5
    assert growth["totals"]["total_forks"] == 2
    assert growth["totals"]["total_stargazers_delta"] == 7
    assert growth["totals"]["total_subscribers_delta"] == 3
    assert growth["totals"]["total_forks_delta"] == 1
    assert growth["per_repo"]["demo/high"]["conversion"]["stargazers"] == {
        "value": 0.2,
        "denominator": 25,
        "denominator_metric": "visitors",
    }
    assert growth["per_repo"]["demo/fallback"]["conversion"]["stargazers"] == {
        "value": 2 / 12,
        "denominator": 12,
        "denominator_metric": "views",
    }


def test_growth_series_uses_latest_repo_per_day_snapshot() -> None:
    metric_rows = [
        _metric_row("demo/reponomics", "2026-05-01", 10, 2, 1, "09:00:00Z"),
        _metric_row("demo/reponomics", "2026-05-01", 12, 3, 1, "18:00:00Z"),
        _metric_row("demo/reponomics", "2026-05-02", 13, 3, 2),
    ]

    series = run.load_data.repo_growth_series(metric_rows)

    assert series["demo/reponomics"]["dates"] == ["2026-05-01", "2026-05-02"]
    assert series["demo/reponomics"]["stargazers"] == [12, 13]
    assert series["demo/reponomics"]["subscribers"] == [3, 3]
    assert series["demo/reponomics"]["forks"] == [1, 2]


def test_growth_missing_history_has_zero_deltas_and_no_ratio() -> None:
    daily_rows = [_daily_row("demo/new", "2026-05-02", 4, 2)]
    metric_rows = [_metric_row("demo/new", "2026-05-02", 10, 1, 0)]

    growth = run.load_data.growth_analytics(daily_rows, metric_rows, recent_days=14)
    repo = growth["per_repo"]["demo/new"]

    assert repo["deltas"]["sample_count"] == 1
    assert repo["deltas"]["stargazers_delta"] == 0
    assert repo["deltas"]["subscribers_delta"] == 0
    assert repo["deltas"]["forks_delta"] == 0
    assert repo["conversion"]["stargazers"] == {
        "value": None,
        "denominator": 0,
        "denominator_metric": None,
    }
    assert run.load_data.actionable_insights(daily_rows, metric_rows) == []


def test_growth_deltas_ignore_migrated_blank_counter_baselines() -> None:
    daily_rows = [_daily_row("demo/reponomics", "2026-05-16", 80, 20, 4)]
    migrated = _metric_row("demo/reponomics", "2026-05-03", 43895, 0, 3751)
    migrated["subscribers_count"] = ""
    current = _metric_row("demo/reponomics", "2026-05-16", 43967, 298, 3766)

    growth = run.load_data.growth_analytics(daily_rows, [migrated, current], recent_days=14)
    repo = growth["per_repo"]["demo/reponomics"]

    assert repo["deltas"]["stars_delta"] == 72
    assert repo["deltas"]["subscribers_delta"] == 0
    assert repo["deltas"]["forks_delta"] == 15
    assert repo["deltas"]["current_subscribers"] == 298
    assert growth["totals"]["total_subscribers"] == 298
    assert growth["totals"]["total_subscribers_delta"] == 0


def test_growth_insights_select_top_defensible_candidate() -> None:
    daily_rows = []
    metric_rows = []
    for day in range(1, 5):
        ts = f"2026-05-0{day}"
        daily_rows.append(_daily_row("demo/attention", ts, 35, 12, 4))
        daily_rows.append(_daily_row("demo/tiny", ts, 1, 1, 0))
    metric_rows.extend([
        _metric_row("demo/attention", "2026-05-01", 10, 2, 1),
        _metric_row("demo/attention", "2026-05-04", 10, 2, 1),
        _metric_row("demo/tiny", "2026-05-01", 0, 0, 0),
        _metric_row("demo/tiny", "2026-05-04", 1, 0, 0),
    ])

    insights = run.load_data.actionable_insights_structured(
        daily_rows,
        metric_rows,
        limit=1,
    )

    assert len(insights) == 1
    assert insights[0]["repo"] == "demo/attention"
    assert insights[0]["subtype"] in {
        "high_attention_low_interest",
        "traffic_without_downstream_growth",
    }


def test_collect_requests_one_detail_per_selected_repo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "include_only:\n  - demo/one\n  - demo/two\nmax_repos: 2\n",
        encoding="utf-8",
    )
    config = _config(tmp_path, config_path=config_path)
    discovered = [
        {
            "full_name": "demo/one",
            "permissions": {"push": True},
            "fork": False,
            "archived": False,
            "disabled": False,
            "private": False,
            "created_at": "2025-01-01T00:00:00Z",
        },
        {
            "full_name": "demo/two",
            "permissions": {"push": True},
            "fork": False,
            "archived": False,
            "disabled": False,
            "private": False,
            "created_at": "2025-01-02T00:00:00Z",
        },
    ]
    detail_calls: list[str] = []

    def fake_fetch_json(url: str, headers, allow_not_found: bool = False):
        assert allow_not_found is False
        detail_calls.append(url)
        repo = url.removeprefix("https://api.github.com/repos/")
        return {
            "id": 100 + len(detail_calls),
            "node_id": f"R_{repo}",
            "stargazers_count": 10 + len(detail_calls),
            "watchers_count": 900 + len(detail_calls),
            "subscribers_count": 20 + len(detail_calls),
            "forks_count": 30 + len(detail_calls),
        }

    monkeypatch.setattr(run.collect_mod, "get_headers", lambda: {})
    monkeypatch.setattr(run.collect_mod, "validate_token", lambda headers: None)
    monkeypatch.setattr(run.collect_mod, "discover_repositories", lambda headers: discovered)
    monkeypatch.setattr(run.collect_mod, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(run.collect_mod, "collect_views_clones", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_referrers", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_paths", lambda *args: [])

    run.run_collect(config, restore_artifact=False, execute_collect=True)

    assert detail_calls == [
        "https://api.github.com/repos/demo/one",
        "https://api.github.com/repos/demo/two",
    ]
    with (config.data_dir / "repo-metrics.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["repo"] for row in rows] == ["demo/one", "demo/two"]
    assert [row["subscribers_count"] for row in rows] == ["21", "22"]
    assert [row["source"] for row in rows] == ["repo-detail", "repo-detail"]


def test_detail_failure_falls_back_without_losing_traffic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("include_only:\n  - demo/reponomics\n", encoding="utf-8")
    config = _config(tmp_path, config_path=config_path)
    discovered = [
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
            "stargazers_count": 15,
            "watchers_count": 999,
            "subscribers_count": 3,
            "forks_count": 2,
        }
    ]

    def raise_detail_error(repo: str, headers):
        raise requests.HTTPError("detail unavailable")

    monkeypatch.setattr(run.collect_mod, "get_headers", lambda: {})
    monkeypatch.setattr(run.collect_mod, "validate_token", lambda headers: None)
    monkeypatch.setattr(run.collect_mod, "discover_repositories", lambda headers: discovered)
    monkeypatch.setattr(run.collect_mod, "collect_repo_detail", raise_detail_error)
    monkeypatch.setattr(
        run.collect_mod,
        "collect_views_clones",
        lambda repo, headers, captured_at: [
            {
                "repo": repo,
                "ts": "2026-05-16",
                "views_count": 5,
                "views_uniques": 4,
                "clones_count": 3,
                "clones_uniques": 2,
                "captured_at": captured_at,
                "source": "api",
                "schema_version": run.storage.SCHEMA_VERSION,
            }
        ],
    )
    monkeypatch.setattr(run.collect_mod, "collect_referrers", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_paths", lambda *args: [])

    run.run_collect(config, restore_artifact=False, execute_collect=True)

    with (config.data_dir / "traffic-log.csv").open(newline="", encoding="utf-8") as handle:
        traffic_rows = list(csv.DictReader(handle))
    with (config.data_dir / "repo-metrics.csv").open(newline="", encoding="utf-8") as handle:
        metric_rows = list(csv.DictReader(handle))
    assert traffic_rows[-1]["repo"] == "demo/reponomics"
    assert traffic_rows[-1]["views_count"] == "5"
    assert metric_rows[-1]["source"] == "discovery-fallback"
    assert metric_rows[-1]["subscribers_count"] == "3"
    assert metric_rows[-1]["stargazers_count"] == "15"


def test_schema_migration_upgrades_v2_metrics_manifest_dedup_and_retention(
    tmp_path: Path,
) -> None:
    fixture = _copy_fixture("compat_v2", tmp_path)
    data_dir = fixture / "data"

    run.storage.DATA_DIR = data_dir.as_posix()
    run.merge.DATA_DIR = data_dir.as_posix()
    run.storage.migrate_schema(data_dir.as_posix())
    run.merge.dedup_all()
    run.merge.trim_all()
    manifest = run.storage.read_manifest(data_dir.as_posix())
    run.storage.write_manifest(manifest, data_dir.as_posix())

    with (data_dir / "repo-metrics.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows == [
        {
            "repo": "demo/reponomics",
            "repo_id": "",
            "node_id": "",
            "ts": "2026-05-01",
            "captured_at": "2026-05-01T12:00:00Z",
            "stargazers_count": "11",
            "subscribers_count": "2",
            "forks_count": "1",
            "open_issues_count": "",
            "size_kb": "",
            "created_at": "",
            "pushed_at": "",
            "updated_at": "",
            "language": "",
            "visibility": "",
            "default_branch": "",
            "has_pages": "",
            "has_discussions": "",
            "archived": "",
            "disabled": "",
            "source": "fixture",
            "schema_version": run.storage.SCHEMA_VERSION,
        }
    ]
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == run.storage.SCHEMA_VERSION
    assert manifest["files"] == list(run.storage.CSV_REGISTRY.keys())
    assert manifest["created_at"] == "2026-05-01T12:00:00Z"


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

    def fake_fetch_json(url: str, headers, allow_not_found: bool = False):
        assert url == "https://api.github.com/repos/demo/reponomics"
        assert allow_not_found is False
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

    run.run_collect(config, restore_artifact=False, execute_collect=True)

    assert config.config_path.read_text(encoding="utf-8") == before_config
    with (config.data_dir / "repo-metrics.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert detail_calls == ["https://api.github.com/repos/demo/reponomics"]
    assert rows[-1]["repo_id"] == "123"
    assert rows[-1]["stargazers_count"] == "15"
    assert rows[-1]["subscribers_count"] == "3"
    assert rows[-1]["forks_count"] == "2"
    assert rows[-1]["open_issues_count"] == "4"
    assert rows[-1]["size_kb"] == "512"
    assert rows[-1]["default_branch"] == "main"
    assert rows[-1]["source"] == "repo-detail"
    assert rows[-1]["schema_version"] == run.storage.SCHEMA_VERSION
    assert (tmp_path / ".traffic-artifact" / "traffic-data.enc").exists()


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
    assert config.dashboard_path.exists()
    manifest = json.loads((config.data_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == run.storage.SCHEMA_VERSION
    header = (config.data_dir / "repo-metrics.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == run.storage.REPO_METRIC_FIELDS
    readme = config.readme_path.read_text(encoding="utf-8")
    dashboard = config.dashboard_path.read_text(encoding="utf-8")
    assert "Growth (14d)" in readme
    assert "now 11 / 2" in readme
    assert "Reponomics Dashboard" in dashboard
    assert "encrypted-payload" in dashboard


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
    encrypted_path = tmp_path / ".traffic-artifact" / "traffic-data.enc"
    run.crypto_artifact.encrypt(config.data_dir, encrypted_path, "TRAFFIC_DASHBOARD_SECRET")
    for path in config.data_dir.iterdir():
        path.unlink()
    (config.data_dir / "traffic-data.enc").write_text(
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
    (rotated.data_dir / "traffic-data.enc").write_text(
        encrypted_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setenv("TRAFFIC_DASHBOARD_SECRET", NEXT_KEY)
    run.crypto_artifact.decrypt(
        rotated.data_dir / "traffic-data.enc",
        rotated.data_dir,
        "TRAFFIC_DASHBOARD_SECRET",
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
    dashboard = config.dashboard_path.read_text(encoding="utf-8")
    assert config.readme_path.exists()
    assert config.dashboard_path.exists()
    assert "Growth (14d)" not in readme
    assert "Reponomics Dashboard" in dashboard
    assert "encrypted-payload" in dashboard
