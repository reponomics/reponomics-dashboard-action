from __future__ import annotations

import base64
import hashlib
import io
import re
from pathlib import Path
import zipfile

import pytest

from dashboard_action import run
from scripts import dashboard_scenarios

from runner_support import (
    FIXTURES_DIR,
    OLD_KEY,
    _asset_text,
    _config,
    _copy_fixture,
    _csp_content,
    _dashboard_json,
    _decode_plaintext_dashboard_data,
    _decrypt_encrypted_dashboard_data,
    _parse_dashboard_html,
    _published_runtime_text,
    _published_script_sources,
    _seed_log,
    _seed_scenario,
)


def test_publish_large_corpus_writes_one_encrypted_chunk_per_repo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish", generate_readme=False)
    dataset = dashboard_scenarios.large_corpus_scenario()
    _seed_scenario(config.data_dir, dataset)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    encrypted_data = _dashboard_json(
        config.pages_index_path,
        dashboard,
        "encrypted-dashboard-data",
        "encrypted-dashboard-data.json",
    )
    summary, chunks = _decrypt_encrypted_dashboard_data(encrypted_data)

    assert summary["totals"]["repo_count"] == 200
    assert encrypted_data["chunk_count"] == 200
    assert len(encrypted_data["chunks"]) == 200
    assert len(summary["repo_chunks"]) == 200
    assert len(chunks) == 200
    assert "series" not in summary["growth"]
    assert "reponomics-scale/repo-001" not in dashboard


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
    assert config.pages_index_path.exists()


def test_publish_plaintext_private_renders_plaintext_dashboard_for_artifact_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(
        tmp_path,
        mode="publish",
        data_mode="plaintext",
        dashboard_secret="",
        generate_readme=False,
    )
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    assert config.pages_index_path.exists()
    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    assert "Reponomics Dashboard" in dashboard
    assert "encrypted-dashboard-data" not in dashboard
    assert 'name="reponomics-dashboard-data"' in dashboard
    public_entry = _asset_text(config.pages_index_path, "dashboard/entry-public.js")
    assert "createDashboardApp" in public_entry
    assert "readJsonAsset" in public_entry
    assert "dashboardPayload" not in dashboard
    assert "Dashboard disabled" not in dashboard
    assert 'src="assets/chart.umd.min.js"' in dashboard
    assert 'type="module" src="assets/dashboard/entry-public.js"' in dashboard
    assert (config.pages_index_path.parent / "assets" / "chart.umd.min.js").exists()

    plaintext_data = _dashboard_json(
        config.pages_index_path, dashboard, "plaintext-dashboard-data", "dashboard-data.json"
    )
    summary, chunks = _decode_plaintext_dashboard_data(plaintext_data)
    repo_names = [repo["name"] for repo in summary["repos"]]
    assert plaintext_data == {
        "version": run.render_dashboard.DASHBOARD_DATA_VERSION,
        "encoding": "json",
        "summary": summary,
        "chunks": plaintext_data["chunks"],
        "chunk_count": len(repo_names),
    }
    assert set(plaintext_data["chunks"]) == set(summary["repo_chunks"].values())
    assert set(chunks) == set(summary["repo_chunks"].values())
    assert "repo_series" not in summary
    assert "repo_weekday" not in summary
    assert "repo_referrers" not in summary
    assert "repo_paths" not in summary
    assert "per_repo" not in summary["growth"]
    assert "series" not in summary["growth"]

    for repo_name, chunk_id in summary["repo_chunks"].items():
        assert isinstance(plaintext_data["chunks"][chunk_id], str)
        chunk = chunks[chunk_id]
        assert chunk["repo"] == repo_name
        assert set(chunk) == {
            "repo",
            "repo_series",
            "repo_weekday",
            "repo_referrers",
            "repo_paths",
            "growth",
        }
        assert chunk["repo_series"]["dates"]
        assert "per_repo" in chunk["growth"]
        assert "series" in chunk["growth"]["per_repo"]


def test_publish_large_corpus_writes_one_plaintext_chunk_per_repo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(
        tmp_path,
        mode="publish",
        data_mode="plaintext",
        dashboard_secret="",
        generate_readme=False,
    )
    dataset = dashboard_scenarios.large_corpus_scenario()
    _seed_scenario(config.data_dir, dataset)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    plaintext_data = _dashboard_json(
        config.pages_index_path, dashboard, "plaintext-dashboard-data", "dashboard-data.json"
    )
    summary, chunks = _decode_plaintext_dashboard_data(plaintext_data)

    assert summary["totals"]["repo_count"] == 200
    assert plaintext_data["chunk_count"] == 200
    assert len(plaintext_data["chunks"]) == 200
    assert len(summary["repo_chunks"]) == 200
    assert len(chunks) == 200
    assert "series" not in summary["growth"]
    assert '"repo_series":{' not in dashboard


def test_publish_collection_quality_preview_fixture_renders_calendar_and_gap_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    fixture = _copy_fixture("collection_quality_preview", tmp_path)
    config = _config(
        tmp_path,
        mode="publish",
        data_mode="plaintext",
        dashboard_secret="",
        generate_readme=False,
        config_path=fixture / "config.yaml",
        data_dir=fixture / "data",
        pages_index_path=fixture / "docs" / "index.html",
    )

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    runtime = _published_runtime_text(config.pages_index_path, encrypted=False)
    assert 'id="calendarMonthLabel"' in dashboard
    assert "function shiftCalendarMonth(delta)" in runtime
    assert "Array.isArray(day?.repos) && day.repos.length > 0" in runtime
    payload_asset = _asset_text(config.pages_index_path, "dashboard-data.json")
    assert (
        '"message":"Collection gaps detected in the latest run: 1 skipped, 0 error(s), 1/2 repos collected."'
        in payload_asset
    )
    assert '"date":"2026-04-30","status":"gaps_detected"' in payload_asset
    assert '"date":"2026-05-14","status":"all_zero"' in payload_asset


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
    dashboard = config.pages_index_path.read_text(encoding="utf-8")

    assert "Growth (14d)" in readme
    assert "interest **+0 stars** / **+0 watchers** (now 11 / 2)" in readme
    assert "adoption **3 clones** / **+0 forks** (now 1)" in readme
    assert "Repository Growth" in readme
    assert "encrypted-dashboard-data" in dashboard
    assert "Reponomics Dashboard" in dashboard
    assert 'h1 class="brand">reponomics<span class="accent">.</span></h1>' in dashboard
    assert "data:font/woff2;base64," not in dashboard
    assert 'href="assets/font-face.css"' in dashboard
    assert (config.pages_index_path.parent / "assets" / "inter-latin-wght-normal.woff2").is_file()
    assert (
        config.pages_index_path.parent / "assets" / "jetbrains-mono-latin-wght-normal.woff2"
    ).is_file()
    assert "fonts.googleapis.com" not in dashboard
    assert 'data-window="7"' in dashboard
    assert 'data-window="14"' in dashboard
    assert 'data-window="30"' in dashboard
    assert 'data-window="90"' in dashboard
    assert 'data-window="all"' in dashboard
    assert 'src="assets/chart.umd.min.js"' in dashboard
    assert "cdn.jsdelivr.net" not in dashboard
    assert "Attention" in dashboard
    assert "Interest" in dashboard
    assert "Adoption" in dashboard
    runtime = _published_runtime_text(config.pages_index_path, encrypted=True)
    assert "Star Growth" in runtime
    assert "Watcher Growth" in runtime
    assert "Fork Growth" in runtime
    assert "params.set('window', getSelectedWindow())" in runtime
    assert "range === 'recent'" in runtime
    assert "range === 'all'" in runtime
    assert "function buildGrowthDeltaSeries(series)" in runtime
    assert "stars_delta: deltaFor('stargazers')" in runtime
    assert "SERIES_METRIC_KEYS" in runtime
    assert "function compareRepoFreshness(a, b)" in runtime
    assert "repoFreshnessTimestamp(a)" in runtime
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

    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    export_manifest = _dashboard_json(
        config.pages_index_path, dashboard, "export-manifest", "export-manifest.json"
    )
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

    asset_path = config.pages_index_path.parent / export_manifest["asset"]
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

    dashboard_html = config.pages_index_path.read_text(encoding="utf-8")
    published = _parse_dashboard_html(dashboard_html)
    csp = _csp_content(dashboard_html)
    script_sources = [script.get("src") for script in published.scripts if script.get("src")]
    assert script_sources == _published_script_sources(encrypted=True)
    assert all(not str(src).startswith(("http://", "https://", "//")) for src in script_sources)
    assert 'href="assets/font-face.css"' in dashboard_html
    assert 'href="assets/base.css"' in dashboard_html
    assert (config.pages_index_path.parent / "assets" / "inter-latin-wght-normal.woff2").is_file()
    assert (
        config.pages_index_path.parent / "assets" / "jetbrains-mono-latin-wght-normal.woff2"
    ).is_file()
    assert csp == run.render_dashboard.dashboard_html.PUBLISHED_META_CSP
    assert "default-src 'none'" in csp
    assert "script-src 'self'" in csp
    assert "script-src-attr 'none'" in csp
    assert "style-src-attr 'none'" in csp
    assert "font-src 'self'" in csp
    assert "font-src 'self' data:" not in csp
    assert "img-src 'self';" in csp
    assert "img-src 'self' data:" not in csp
    assert "connect-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "form-action 'none'" in csp
    assert "frame-ancestors" not in csp
    assert "'unsafe-inline'" not in csp
    assert "<style" not in dashboard_html
    assert "onclick=" not in dashboard_html
    assert 'style="' not in dashboard_html
    assert {"dailyChart", "weekdayChart", "stackedChart"} <= published.canvases
    assert "unlock-form" in published.forms
    assert 'id="calendarHint"' in dashboard_html
    assert 'id="calendarDayDetail"' in dashboard_html
    assert 'id="calendarGrid"' in dashboard_html
    assert 'id="calendarMonthLabel"' in dashboard_html
    runtime = _published_runtime_text(config.pages_index_path, encrypted=True)
    assert 'data-detail="' in runtime
    assert "function configureYAxis(chart, labels, datasets, stacked)" in runtime
    assert "y.max = Math.max(1, Math.ceil(max) + 1)" in runtime
    assert "function renderCollectionCalendar()" in runtime
    assert "function computeNoRunStats(days)" in runtime
    assert "function calendarStatusLabel(day)" in runtime
    assert "function trafficReportingByDate()" in runtime
    assert "function applyVisibilityThresholdToQualityDays(days)" in runtime
    assert "no workflow run" in runtime
    assert "no-run day(s)" in runtime
    assert "collection gap day(s)" in runtime
    assert "traffic lag day(s)" in runtime
    assert "GitHub traffic unreported" in runtime
    assert "function shiftCalendarMonth(delta)" in runtime

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

    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    base_css = _asset_text(config.pages_index_path, "base.css")

    assert '<body class="auth-locked" data-screen-label="Unlock - Encrypted Pages">' in dashboard
    assert 'class="auth-theme-toggle theme-toggle"' not in dashboard
    assert 'id="auth-theme-toggle"' not in dashboard
    assert "authThemeToggle" not in _asset_text(
        config.pages_index_path, "dashboard/entry-secure.js"
    )
    assert 'class="auth-data-preview" aria-hidden="true"' not in dashboard
    assert 'class="auth-data auth-data-left"' not in dashboard
    assert 'class="auth-data auth-data-right"' not in dashboard
    assert 'class="auth-data auth-data-lower"' not in dashboard
    assert "document.querySelectorAll('.theme-toggle')" in _asset_text(
        config.pages_index_path, "dashboard/theme.js"
    )

    assert 'class="auth-card auth-vault-door" id="unlock-card"' in dashboard
    assert 'class="auth-vault-wheel"' in dashboard
    assert 'class="auth-vault-hub"' in dashboard
    assert 'class="auth-card-icon"' not in dashboard
    assert 'class="auth-mark"' not in dashboard
    assert "max-width: 52ch;" not in dashboard
    assert 'class="brand-eyebrow auth-brand-line auth-brand-line-own">Your</div>' not in dashboard
    assert (
        'class="brand-eyebrow auth-brand-line auth-brand-line-dashboard">Dashboard</div>'
        in dashboard
    )
    assert "Enter your dashboard key below." not in dashboard
    assert 'class="tick tl"' not in dashboard
    assert 'class="lock-shackle"' in dashboard
    assert 'class="btn-label-default">Unlock</span>' in dashboard
    assert 'class="btn-label-success">Unlocked</span>' in dashboard

    assert "color-scheme: dark;" in base_css
    assert "width: 760px;" in base_css
    assert "max-width: none;" in base_css
    assert "min-height: 100svh;" in base_css
    assert ".auth-data-line.primary" not in base_css
    assert "@keyframes authDataFloat" not in base_css
    assert ".auth-vault-wheel" in base_css
    assert ".auth-card.is-opening .auth-vault-wheel" in base_css
    assert "animation: authDotPulse 2.4s ease-in-out infinite;" not in base_css
    assert '[data-theme="light"] .auth-button' not in base_css
    assert ".auth-button.is-unlocking .lock-shackle" in base_css
    assert ".auth-button.is-unlocked .lock-shackle" in base_css
    assert "@keyframes authRejectShudder" in base_css

    runtime = _published_runtime_text(config.pages_index_path, encrypted=True)
    assert "const UNLOCK_SUCCESS_DELAY_MS = 3400;" in runtime
    assert "const REDUCED_MOTION_UNLOCK_SUCCESS_DELAY_MS = 0;" in runtime
    assert "window.matchMedia('(prefers-reduced-motion: reduce)').matches" in runtime
    assert "const successDelayMs = unlockSuccessDelayMs();" in runtime
    assert "if (successDelayMs > 0)" in runtime
    assert "const AUTH_REVEAL_FADE_MS = 680;" in runtime
    assert "await playSuccessfulUnlock();" in runtime
    assert "authShell.classList.add('is-revealing');" in runtime
    assert "function playRejectedUnlock()" in runtime

    assert "Encrypted Pages mode for private growth analytics." not in dashboard
    assert "Client-side decryption" not in dashboard
    assert "AES-GCM" not in dashboard
    assert (
        '<a href="https://github.com/reponomics/reponomics-dashboard-demo/blob/main/docs/reponomics/security-info.md">'
        + "Problems unlocking your dashboard? Click here</a>"
        in dashboard
    )
    assert (
        '<a class="brand-name" href="https://github.com/reponomics">Reponomics</a>' not in dashboard
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

    runtime = _asset_text(config.pages_index_path, "dashboard/entry-secure.js")
    secure_core = _asset_text(config.pages_index_path, "dashboard/secure-core.js")

    expected_secure_core_markers = [
        "UNLOCK_ATTEMPT_STORAGE_PREFIX = 'reponomics-unlock-attempts:'",
        "UNLOCK_DELAY_STARTS_AT = 3",
        "UNLOCK_DELAY_BASE_MS = 2000",
        "UNLOCK_DELAY_MAX_MS = 30000",
        "function nextUnlockDelayMs(failures)",
    ]
    for marker in expected_secure_core_markers:
        assert marker in secure_core

    expected_runtime_markers = [
        "function unlockAttemptStorageKey()",
        "function startUnlockDelay(delayMs, prefix)",
        "localStorage.setItem(unlockAttemptStorageKey(), JSON.stringify(state))",
        "localStorage.removeItem(unlockAttemptStorageKey())",
        "resetUnlockAttemptState();",
        "Too many failed attempts. Try again in ",
        "Wrong dashboard key or corrupted data. Try again in ",
    ]
    for marker in expected_runtime_markers:
        assert marker in runtime


def test_publish_dashboard_toolbar_controls_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish")
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    dashboard = config.pages_index_path.read_text(encoding="utf-8")
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

    base_css = _asset_text(config.pages_index_path, "base.css")
    secure_runtime = _asset_text(config.pages_index_path, "dashboard/entry-secure.js")
    assert "font-size: clamp(2.75rem, 5.2vw, 3.2rem);" in base_css
    assert base_css.count(".theme-toggle .theme-label { display: none; }") == 1
    assert "@media (max-width: 1240px) {" in base_css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in base_css
    assert ".hero-toolbar-controls > .export-verify-tip > summary {" in base_css
    assert "@media (max-width: 480px) {" in base_css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in base_css
    assert "grid-template-columns: repeat(3, minmax(0, max-content));" not in base_css
    assert "grid-template-columns: repeat(2, minmax(0, max-content));" not in base_css
    assert "const useMultiline = rawMessage.includes('\\n');" in secure_runtime
    assert (
        "setExportStatus('📄 CSV export ready.\\nSHA-256: ' + plaintextSha256, 'success');"
        in secure_runtime
    )
    assert (
        "const shaMatch = /SHA-256:\\\\s*([0-9a-f]{16,})/i.exec(rawMessage);" not in secure_runtime
    )
