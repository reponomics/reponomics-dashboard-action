from __future__ import annotations

import base64
import csv
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
import zipfile

import pytest
import requests

from dashboard_action import run


OLD_KEY = "old-dashboard-secret-" + ("x" * 40)
NEXT_KEY = "next-dashboard-secret-" + ("y" * 40)
FIXTURES_DIR = Path(__file__).parent / "fixtures"
VERSION_STATUS_TEST_VERSION = "0.13.1"
VERSION_STATUS_TEST_TAG = f"v{VERSION_STATUS_TEST_VERSION}"
VERSION_STATUS_RELEASES_URL = "https://github.com/reponomics/reponomics-dashboard-action/releases"


def _version_status_tag(version: str) -> str:
    return version if version.startswith("v") else f"v{version}"


def _version_status_release_url(tag: str) -> str:
    return f"{VERSION_STATUS_RELEASES_URL}/tag/{tag}"


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


def _csp_content(document: str) -> str:
    match = re.search(
        r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">',
        document,
    )
    if not match:
        raise AssertionError("missing Content-Security-Policy meta tag")
    return unescape(match.group(1))


def _config(tmp_path: Path, **overrides) -> run.RuntimeConfig:
    values: dict[str, Any] = {
        "mode": "collect",
        "collection_token": "ghp_collection",
        "use_github_app": False,
        "github_token": "ghp_test",
        "dashboard_secret": OLD_KEY,
        "dashboard_next_secret": "",
        "privacy_mode": "strong",
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
        "action_ref": "v0.1.0",
        "action_repository": "reponomics/reponomics-dashboard-action",
    }
    values.update(overrides)
    return run.RuntimeConfig(**values)


@pytest.fixture(autouse=True)
def _stub_version_status_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run.version_status, "_fetch_releases", lambda: [])


@pytest.fixture(autouse=True)
def _reset_collect_runtime_state() -> Generator[None, None, None]:
    run.collect_mod._reset_runtime_state()
    yield
    run.collect_mod._reset_runtime_state()


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
                "community_health_percentage": "71",
                "community_documentation": "https://github.com/demo/reponomics",
                "community_updated_at": "2026-05-01T11:30:00Z",
                "community_content_reports_enabled": "True",
                "community_has_code_of_conduct": "True",
                "community_has_contributing": "True",
                "community_has_issue_template": "False",
                "community_has_pull_request_template": "False",
                "community_has_readme": "True",
                "community_has_license": "True",
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
        "community_health_percentage": "",
        "community_documentation": "",
        "community_updated_at": "",
        "community_content_reports_enabled": "",
        "community_has_code_of_conduct": "",
        "community_has_contributing": "",
        "community_has_issue_template": "",
        "community_has_pull_request_template": "",
        "community_has_readme": "",
        "community_has_license": "",
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
    monkeypatch.setenv("REPONOMICS_PRIVACY_MODE", "strong")
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", github_event_repository_private)
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(tmp_path / "config.yaml"))
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
    assert config.privacy_mode == "strong"
    assert config.repo_is_public is expected_repo_is_public
    assert config.resolved_artifact_mode == "encrypted"
    assert config.publish_pages is True
    assert config.retention_days == 30
    assert config.generate_readme is False
    assert config.allow_docs_sync is True


def test_allow_docs_sync_uses_config_when_input_is_unset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("allow_docs_sync: false\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("REPONOMICS_ALLOW_DOCS_SYNC", raising=False)

    config = run.load_config_from_env()

    assert config.allow_docs_sync is False


def test_allow_docs_sync_input_overrides_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("allow_docs_sync: false\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("REPONOMICS_ALLOW_DOCS_SYNC", "true")

    config = run.load_config_from_env()

    assert config.allow_docs_sync is True


def test_allow_docs_sync_rejects_non_boolean_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text('allow_docs_sync: "false"\n', encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("REPONOMICS_ALLOW_DOCS_SYNC", raising=False)

    with pytest.raises(run.ActionError, match="allow_docs_sync"):
        run.load_config_from_env()


def test_use_github_app_input_normalization_from_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("REPONOMICS_MODE", "collect")
    monkeypatch.setenv("REPONOMICS_COLLECTION_TOKEN", "ghs_installation_token")
    monkeypatch.setenv("REPONOMICS_USE_GITHUB_APP", "true")
    monkeypatch.setenv("REPONOMICS_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("REPONOMICS_DASHBOARD_SECRET", OLD_KEY)
    monkeypatch.setenv("REPONOMICS_PRIVACY_MODE", "strong")
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    monkeypatch.setenv("REPONOMICS_RETENTION_DAYS", "30")
    monkeypatch.setenv("REPONOMICS_GENERATE_README", "false")
    monkeypatch.setenv("REPONOMICS_README_PATH", str(tmp_path / "README.md"))

    config = run.load_config_from_env()

    assert config.use_github_app is True


@pytest.mark.parametrize(
    (
        "privacy_mode",
        "publish_pages_requested",
        "expected_artifact_mode",
        "expected_publish_pages",
    ),
    [
        ("strong", True, "encrypted", True),
        ("strong", False, "encrypted", False),
        ("casual", True, "encrypted", True),
        ("casual", False, "encrypted", False),
        ("plain", True, "plain", False),
        ("plain", False, "plain", False),
    ],
)
def test_publish_pages_values_follow_privacy_mode(
    tmp_path: Path,
    privacy_mode: str,
    publish_pages_requested: bool,
    expected_artifact_mode: str,
    expected_publish_pages: bool,
) -> None:
    config = _config(
        tmp_path,
        privacy_mode=privacy_mode,
        publish_pages_requested=publish_pages_requested,
        dashboard_secret="" if privacy_mode == "plain" else OLD_KEY,
    )

    assert config.resolved_artifact_mode == expected_artifact_mode
    assert config.publish_pages is expected_publish_pages


def test_publish_pages_input_normalization_from_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("REPONOMICS_MODE", "publish")
    monkeypatch.setenv("REPONOMICS_COLLECTION_TOKEN", "ghp_collection")
    monkeypatch.setenv("REPONOMICS_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("REPONOMICS_DASHBOARD_SECRET", OLD_KEY)
    monkeypatch.setenv("REPONOMICS_PRIVACY_MODE", "strong")
    monkeypatch.setenv("REPONOMICS_PUBLISH_PAGES", "false")
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "true")
    monkeypatch.setenv("REPONOMICS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    monkeypatch.setenv("REPONOMICS_RETENTION_DAYS", "30")
    monkeypatch.setenv("REPONOMICS_GENERATE_README", "false")
    monkeypatch.setenv("REPONOMICS_README_PATH", str(tmp_path / "README.md"))

    config = run.load_config_from_env()

    assert config.publish_pages_requested is False
    assert config.publish_pages is False


def test_generate_readme_default_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_EVENT_REPOSITORY_PRIVATE", "false")
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
    assert "publish-pages=true" in output
    assert f"pages-path={config.pages_index_path.parent.as_posix()}" in output
    assert "docs-sync-reason=" not in output
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


def test_docs_sync_mode_writes_outputs_and_commits_managed_namespace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []
    output_path = tmp_path / "github-output.txt"
    summary_path = tmp_path / "summary.md"
    config = _config(tmp_path, mode="docs-sync")

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

    run.run_docs_sync(config)

    output = output_path.read_text(encoding="utf-8")
    summary = summary_path.read_text(encoding="utf-8")
    assert (tmp_path / "docs" / "reponomics" / "README.md").is_file()
    assert (tmp_path / "docs" / "reponomics" / ".manifest.json").is_file()
    assert "docs-sync-state=written" in output
    assert f"docs-action-version={run.VERSION}" in output
    assert "docs-updated-at=" in output
    assert "Managed Reponomics docs" in summary
    assert ["git", "add", "--", "docs/reponomics"] in calls
    assert any(command[:3] == ["git", "commit", "-m"] and command[-2:] == ["--", "docs/reponomics"] for command in calls)
    assert ["git", "push"] in calls


def test_docs_sync_mode_reports_permission_missing_for_push_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "github-output.txt"
    config = _config(tmp_path, mode="docs-sync")

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

    run.run_docs_sync(config)

    output = output_path.read_text(encoding="utf-8")
    assert "docs-sync-state=permission_missing" in output
    assert "docs-sync-reason=" not in output
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


def test_collect_requires_github_token_before_upload(tmp_path: Path) -> None:
    config = _config(tmp_path, github_token="")

    with pytest.raises(run.ActionError, match="github-token"):
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

    assert (tmp_path / ".dashboard-data-artifact" / "dashboard-data.enc").exists()
    manifest = run.storage.read_manifest(config.data_dir.as_posix())
    lineage_payload = manifest["lineage"]
    assert lineage_payload["artifact_kind"] == "dashboard-data"
    assert lineage_payload["operation"] == "collect"
    assert lineage_payload["payload_digest"]
    assert lineage_payload["semantic_root_digest"]
    assert lineage_payload["verification"]["type"] == "retained-row-superset"
    assert not config.readme_path.exists()
    assert not config.pages_index_path.exists()


def test_lineage_rejects_child_missing_retained_parent_row(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path)
    _seed_log(config.data_dir)
    run._patch_runtime_paths(config)
    run._prepare_data_schema(config)
    parent = run.lineage.snapshot_payload(config.data_dir)

    _write_csv(config.data_dir / "traffic-log.csv", run.storage.LOG_FIELDS, [])

    with pytest.raises(run.lineage.LineageError, match="does not preserve retained parent rows"):
        run.lineage.write_verified_lineage(
            config.data_dir,
            parent=parent,
            retention_days=config.retention_days,
            action_version=run.VERSION,
            operation="collect",
        )


def test_lineage_rejects_restored_payload_digest_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path)
    _seed_log(config.data_dir)
    run._patch_runtime_paths(config)
    run._prepare_data_schema(config)
    parent = run.lineage.snapshot_payload(config.data_dir)
    run.lineage.write_verified_lineage(
        config.data_dir,
        parent=parent,
        retention_days=config.retention_days,
        action_version=run.VERSION,
        operation="collect",
    )

    rows = run.storage.read_csv((config.data_dir / "traffic-log.csv").as_posix())
    rows[0]["views_count"] = "99"
    run.storage.write_csv((config.data_dir / "traffic-log.csv").as_posix(), rows, run.storage.LOG_FIELDS)
    tampered = run.lineage.snapshot_payload(config.data_dir)

    with pytest.raises(run.lineage.LineageError, match="file digest does not match"):
        run.lineage.validate_snapshot_lineage(tampered)


def test_lineage_accepts_recorded_parent_before_additive_registry_migration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path)
    _seed_log(config.data_dir)
    run._patch_runtime_paths(config)
    run._prepare_data_schema(config)
    parent = run.lineage.snapshot_payload(config.data_dir)
    run.lineage.write_verified_lineage(
        config.data_dir,
        parent=parent,
        retention_days=config.retention_days,
        action_version=run.VERSION,
        operation="collect",
    )

    original_registry = run.storage.CSV_REGISTRY
    monkeypatch.setattr(
        run.storage,
        "CSV_REGISTRY",
        {
            **original_registry,
            "future-compatible.csv": (["repo", "ts", "schema_version"], "ts"),
        },
    )
    restored = run.lineage.snapshot_payload(config.data_dir)

    run.lineage.validate_snapshot_lineage(restored)


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
    assert config.pages_index_path.exists()
    readme = config.readme_path.read_text(encoding="utf-8")
    assert "demo/reponomics" in readme
    assert "Latest data capture: 2026-05-01 12:00 UTC" in readme
    assert "Last updated:" not in readme
    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    assert "encrypted-payload" in dashboard
    assert "export-manifest" in dashboard
    assert 'id="export-button"' in dashboard
    assert 'id="export-hash-button"' in dashboard
    assert "How download verification works" in dashboard
    assert "validateEncryptedPayload" in dashboard
    assert "EXPECTED_KDF_ITERATIONS = 600000" in dashboard
    assert 'src="assets/chart.umd.min.js"' in dashboard
    assert "cdn.jsdelivr.net" not in dashboard
    assert (config.pages_index_path.parent / "assets" / "chart.umd.min.js").exists()
    assert len(list((config.pages_index_path.parent / "assets").glob("export-data-*.enc"))) == 1


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


def test_publish_plain_private_renders_plain_dashboard_for_artifact_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(
        tmp_path,
        mode="publish",
        privacy_mode="plain",
        dashboard_secret="",
        generate_readme=False,
    )
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    assert config.pages_index_path.exists()
    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    assert "Reponomics Dashboard" in dashboard
    assert "encrypted-payload" not in dashboard
    assert "Dashboard disabled" not in dashboard
    assert 'src="assets/chart.umd.min.js"' in dashboard
    assert (config.pages_index_path.parent / "assets" / "chart.umd.min.js").exists()


def test_publish_collection_quality_preview_fixture_renders_calendar_and_gap_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    fixture = _copy_fixture("collection_quality_preview", tmp_path)
    config = _config(
        tmp_path,
        mode="publish",
        privacy_mode="plain",
        dashboard_secret="",
        generate_readme=False,
        config_path=fixture / "config.yaml",
        data_dir=fixture / "data",
        pages_index_path=fixture / "docs" / "index.html",
    )

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    assert 'id="calendarMonthLabel"' in dashboard
    assert "function shiftCalendarMonth(delta)" in dashboard
    assert '"message":"Collection gaps detected in the latest run: 1 skipped, 0 error(s), 1/2 repos collected."' in dashboard
    assert '"date":"2026-04-30","status":"gaps_detected"' in dashboard
    assert '"date":"2026-05-14","status":"all_zero"' in dashboard


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

    dashboard = config.pages_index_path.read_text(encoding="utf-8")
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
    assert script_sources == ["assets/chart.umd.min.js"]
    assert all(not str(src).startswith(("http://", "https://", "//")) for src in script_sources)
    assert "default-src 'self'" in csp
    assert "script-src 'self' 'sha256-" in csp
    assert "style-src 'self' 'sha256-" in csp
    assert "connect-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "'unsafe-inline'" not in csp
    assert "onclick=" not in dashboard_html
    assert 'style="' not in dashboard_html
    assert {"dailyChart", "weekdayChart", "stackedChart"} <= published.canvases
    assert "unlock-form" in published.forms
    assert 'id="calendarHint"' in dashboard_html
    assert 'id="calendarDayDetail"' in dashboard_html
    assert 'id="calendarGrid"' in dashboard_html
    assert 'id="calendarMonthLabel"' in dashboard_html
    assert 'data-detail="' in dashboard_html
    assert "function renderCollectionCalendar()" in dashboard_html
    assert "function computeNoRunStats(days)" in dashboard_html
    assert "function calendarStatusLabel(day)" in dashboard_html
    assert "function applyVisibilityThresholdToQualityDays(days)" in dashboard_html
    assert "status: no-run" in dashboard_html
    assert "no-run day(s)" in dashboard_html
    assert "function shiftCalendarMonth(delta)" in dashboard_html

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

    dashboard = config.pages_index_path.read_text(encoding="utf-8")

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

    dashboard = config.pages_index_path.read_text(encoding="utf-8")
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


def test_version_status_semver_comparison() -> None:
    compare = run.version_status.compare_semver

    assert compare("v1.2.4", "1.2.3") == 1
    assert compare("1.2.3", "1.2.3") == 0
    assert compare("1.2.3-alpha.2", "1.2.3-alpha.10") == -1
    assert compare("1.2.3", "1.2.3-rc.1") == 1


def test_version_status_selects_latest_stable_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    releases = [
        {
            "tag_name": "v0.5.0",
            "draft": False,
            "prerelease": True,
        },
        {
            "tag_name": "v0.4.0",
            "draft": True,
            "prerelease": False,
        },
        {
            "tag_name": "v0.3.0",
            "draft": False,
            "prerelease": False,
            "html_url": "https://malicious.example/release",
            "name": "Compatible <b>release</b>",
        },
    ]

    def fake_fetch_releases():
        return releases

    monkeypatch.setattr(run.version_status, "_fetch_releases", fake_fetch_releases)
    status = run.version_status.build_status_payload(
        current_version="0.2.0",
        action_ref="v0.2.0",
        action_repository="reponomics/reponomics-dashboard-action",
        check_latest=True,
    )

    assert status == {
        "current_version": "0.2.0",
        "current_url": "https://github.com/reponomics/reponomics-dashboard-action/releases/tag/v0.2.0",
        "action_ref": "v0.2.0",
        "latest_version": "v0.3.0",
        "latest_title": "Compatible release",
        "update_available": True,
        "url": "https://github.com/reponomics/reponomics-dashboard-action/releases/tag/v0.3.0",
    }


def test_version_status_api_failure_is_non_fatal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def raise_failure():
        raise requests.RequestException("boom")

    monkeypatch.setattr(run.version_status, "_fetch_releases", raise_failure)
    config = _config(tmp_path, mode="publish")

    run._set_version_status_env(config)

    status = json.loads(os.environ["REPONOMICS_VERSION_STATUS_JSON"])
    current_tag = _version_status_tag(run.VERSION)
    assert status == {
        "current_version": run.VERSION,
        "current_url": _version_status_release_url(current_tag),
        "action_ref": "v0.1.0",
        "update_available": False,
        "url": VERSION_STATUS_RELEASES_URL,
    }


def test_publish_renders_sanitized_version_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    current_version = "0.1.0"
    current_tag = _version_status_tag(current_version)
    monkeypatch.setattr(run, "VERSION", current_version)

    def fake_releases():
        return [
            {
                "tag_name": "v0.2.0",
                "name": "Remote **markdown** <script>alert(1)</script>",
                "html_url": "https://github.com/reponomics/reponomics-dashboard-action/releases/tag/v0.2.0",
                "draft": False,
                "prerelease": False,
                "body": "ignored **markdown** and never rendered",
            }
        ]

    monkeypatch.setattr(run.version_status, "_fetch_releases", fake_releases)
    config = _config(
        tmp_path,
        mode="publish",
        generate_readme=True,
    )
    _seed_log(config.data_dir)

    run.run_publish(config, restore_artifact=False)

    readme = config.readme_path.read_text(encoding="utf-8")
    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    assert f"[![Your version: {current_tag}](docs/assets/action-version-current.svg)]" in readme
    assert "[![Latest version: v0.2.0](docs/assets/action-version-latest.svg)]" in readme
    assert (tmp_path / "docs" / "assets" / "action-version-current.svg").is_file()
    assert (tmp_path / "docs" / "assets" / "action-version-latest.svg").is_file()
    assert 'class="action-version-badge current"' in dashboard
    assert 'class="action-version-badge latest different"' in dashboard
    assert f">your version</span><span class=\"badge-value\">{current_tag}</span>" in dashboard
    assert ">latest version</span><span class=\"badge-value\">v0.2.0</span>" in dashboard
    assert "View latest updates" in readme
    assert "View latest updates" in dashboard
    assert "v0.2.0" in readme
    assert "Remote markdown" not in readme
    assert "Remote markdown" not in dashboard
    assert "ignored **markdown**" not in readme
    assert "alert(1)" not in readme
    assert "alert(1)" not in dashboard
    assert "<script>alert(1)</script>" not in readme
    assert "<script>alert(1)</script>" not in dashboard


@pytest.mark.parametrize(
    ("latest_tag", "latest_display", "latest_url", "latest_class", "latest_color"),
    [
        (
            VERSION_STATUS_TEST_TAG,
            VERSION_STATUS_TEST_TAG,
            _version_status_release_url(VERSION_STATUS_TEST_TAG),
            'class="action-version-badge latest"',
            "#1a7f37",
        ),
        (
            "v0.14.0",
            "v0.14.0",
            _version_status_release_url("v0.14.0"),
            'class="action-version-badge latest different"',
            "#0969da",
        ),
        (
            "",
            "unknown",
            VERSION_STATUS_RELEASES_URL,
            'class="action-version-badge latest unknown"',
            "#6e7781",
        ),
    ],
)
def test_publish_renders_expected_version_status_states(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    latest_tag: str,
    latest_display: str,
    latest_url: str,
    latest_class: str,
    latest_color: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run, "VERSION", VERSION_STATUS_TEST_VERSION)

    if latest_tag:
        monkeypatch.setattr(
            run.version_status,
            "_fetch_releases",
            lambda: [
                {
                    "tag_name": latest_tag,
                    "html_url": latest_url,
                    "draft": False,
                    "prerelease": False,
                }
            ],
        )
    else:
        def raise_failure():
            raise requests.RequestException("boom")

        monkeypatch.setattr(run.version_status, "_fetch_releases", raise_failure)

    config = _config(tmp_path, mode="publish", generate_readme=True)
    _seed_log(config.data_dir)

    run.run_publish(config, restore_artifact=False)

    current_url = _version_status_release_url(VERSION_STATUS_TEST_TAG)
    readme = config.readme_path.read_text(encoding="utf-8")
    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    current_svg = (tmp_path / "docs" / "assets" / "action-version-current.svg").read_text(
        encoding="utf-8",
    )
    latest_svg = (tmp_path / "docs" / "assets" / "action-version-latest.svg").read_text(
        encoding="utf-8",
    )

    current_badge = (
        f"[![Your version: {VERSION_STATUS_TEST_TAG}]"
        + f"(docs/assets/action-version-current.svg)]({current_url})"
    )
    latest_badge = (
        f"[![Latest version: {latest_display}]"
        + f"(docs/assets/action-version-latest.svg)]({latest_url})"
    )
    current_value = f">your version</span><span class=\"badge-value\">{VERSION_STATUS_TEST_TAG}</span>"
    latest_value = f">latest version</span><span class=\"badge-value\">{latest_display}</span>"

    assert current_badge in readme
    assert latest_badge in readme
    assert f"[View latest updates]({latest_url})" in readme
    assert 'class="action-version-badge current"' in dashboard
    assert latest_class in dashboard
    assert f'href="{latest_url}"' in dashboard
    assert current_value in dashboard
    assert latest_value in dashboard
    assert "#1a7f37" in current_svg
    assert latest_color in latest_svg


def test_publish_links_version_status_to_local_managed_docs_when_present(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run, "VERSION", VERSION_STATUS_TEST_VERSION)
    monkeypatch.setattr(
        run.version_status,
        "_fetch_releases",
        lambda: [
            {
                "tag_name": "v0.14.0",
                "html_url": _version_status_release_url("v0.14.0"),
                "draft": False,
                "prerelease": False,
            }
        ],
    )
    managed_docs_dir = tmp_path / "docs" / "reponomics"
    managed_docs_dir.mkdir(parents=True)
    (managed_docs_dir / "README.md").write_text("local docs\n", encoding="utf-8")
    config = _config(tmp_path, mode="publish", generate_readme=True)
    _seed_log(config.data_dir)

    run.run_publish(config, restore_artifact=False)

    readme = config.readme_path.read_text(encoding="utf-8")
    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    assert "[View latest updates](docs/reponomics/README.md)" in readme
    assert 'class="action-version-link" href="reponomics/README.md"' in dashboard


def test_publish_surfaces_blocked_managed_docs_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run, "VERSION", VERSION_STATUS_TEST_VERSION)
    monkeypatch.setenv("REPONOMICS_DOCS_SYNC_STATE", "manifest_inconsistent")
    managed_docs_dir = tmp_path / "docs" / "reponomics"
    managed_docs_dir.mkdir(parents=True)
    (managed_docs_dir / "README.md").write_text("local docs\n", encoding="utf-8")
    config = _config(tmp_path, mode="publish", generate_readme=True)
    _seed_log(config.data_dir)

    run.run_publish(config, restore_artifact=False)

    readme = config.readme_path.read_text(encoding="utf-8")
    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    assert "**Local docs:** needs manual review." in readme
    assert "Local docs:" in dashboard
    assert "needs manual review" in dashboard


def test_publish_surfaces_stale_local_managed_docs_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run, "VERSION", VERSION_STATUS_TEST_VERSION)
    managed_docs_dir = tmp_path / "docs" / "reponomics"
    managed_docs_dir.mkdir(parents=True)
    (managed_docs_dir / "README.md").write_text("local docs\n", encoding="utf-8")
    (managed_docs_dir / ".manifest.json").write_text(
        json.dumps(
            {
                "schema_version": run.managed_docs.MANIFEST_SCHEMA_VERSION,
                "managed_namespace": "docs/reponomics",
                "action_repository": "reponomics/reponomics-dashboard-action",
                "action_version": "0.12.0",
                "updated_at": "2026-05-29T12:00:00Z",
                "files": {},
            }
        ),
        encoding="utf-8",
    )
    config = _config(tmp_path, mode="publish", generate_readme=True)
    _seed_log(config.data_dir)

    run.run_publish(config, restore_artifact=False)

    readme = config.readme_path.read_text(encoding="utf-8")
    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    assert "**Local docs:** version is out of sync with this repository's action version." in readme
    assert "Docs version: v0.12.0." in readme
    assert f"Action version: v{VERSION_STATUS_TEST_VERSION}." in readme
    assert "Last docs update: 2026-05-29 12:00 UTC." in readme
    assert "Local docs:" in dashboard
    assert "version is out of sync with this repository&#x27;s action version" in dashboard
    assert "Docs version: v0.12.0." in dashboard
    assert f"Action version: v{VERSION_STATUS_TEST_VERSION}." in dashboard
    assert "Last docs update: 2026-05-29 12:00 UTC." in dashboard


def test_publish_renders_version_status_fallback_when_latest_unknown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run, "VERSION", VERSION_STATUS_TEST_VERSION)

    def raise_failure():
        raise requests.RequestException("boom")

    monkeypatch.setattr(run.version_status, "_fetch_releases", raise_failure)
    config = _config(
        tmp_path,
        mode="publish",
        generate_readme=True,
    )
    _seed_log(config.data_dir)

    run.run_publish(config, restore_artifact=False)

    readme = config.readme_path.read_text(encoding="utf-8")
    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    assert f"[![Your version: {VERSION_STATUS_TEST_TAG}](docs/assets/action-version-current.svg)]" in readme
    assert "[![Latest version: unknown](docs/assets/action-version-latest.svg)]" in readme
    assert ">latest version</span><span class=\"badge-value\">unknown</span>" in dashboard
    assert "View latest updates" in readme
    assert "View latest updates" in dashboard
    assert "Check latest release" not in readme
    assert "Check latest release" not in dashboard


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
    assert all(headers["Authorization"] == f"Bearer {config.github_token}" for headers in captured_headers)


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
        "community_health_percentage", "community_documentation",
        "community_updated_at", "community_content_reports_enabled",
        "community_has_code_of_conduct", "community_has_contributing",
        "community_has_issue_template", "community_has_pull_request_template",
        "community_has_readme", "community_has_license",
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
        {
            "health_percentage": 85,
            "documentation": "https://docs.example.com/reponomics",
            "updated_at": "2026-05-16T12:00:00Z",
            "content_reports_enabled": True,
            "files": {
                "code_of_conduct": {"html_url": "https://example.com/coc"},
                "contributing": {"html_url": "https://example.com/contrib"},
                "issue_template": None,
                "pull_request_template": {"html_url": "https://example.com/pr"},
                "readme": {"html_url": "https://example.com/readme"},
                "license": {"html_url": "https://example.com/license"},
            },
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
            "community_health_percentage": 85,
            "community_documentation": "https://docs.example.com/reponomics",
            "community_updated_at": "2026-05-16T12:00:00Z",
            "community_content_reports_enabled": True,
            "community_has_code_of_conduct": True,
            "community_has_contributing": True,
            "community_has_issue_template": False,
            "community_has_pull_request_template": True,
            "community_has_readme": True,
            "community_has_license": True,
            "source": "repo-detail",
            "schema_version": run.storage.SCHEMA_VERSION,
        }
    ]


def test_collect_retry_after_parses_delta_and_http_date() -> None:
    future = datetime.now(timezone.utc) + timedelta(seconds=30)
    http_date = future.strftime("%a, %d %b %Y %H:%M:%S GMT")

    assert run.collect_mod._parse_retry_after_seconds(None) is None
    assert run.collect_mod._parse_retry_after_seconds("2.2") == 3
    parsed_date = run.collect_mod._parse_retry_after_seconds(http_date)
    assert parsed_date is not None
    assert 0 <= parsed_date <= 35
    assert run.collect_mod._parse_retry_after_seconds("not a date") is None


def test_collect_status_row_truncates_multiline_error_messages() -> None:
    row = run.collect_mod._collection_status_row(
        repo="demo/reponomics",
        captured_at="2026-05-16T12:00:00Z",
        run_id="123",
        status="error",
        metric_source="repo-detail",
        traffic_days=0,
        referrer_rows=0,
        path_rows=0,
        error_type="RuntimeError",
        error_message=("line one\n" + ("x" * 260)),
    )

    assert row["ts"] == "2026-05-16"
    assert "\n" not in row["error_message"]
    assert row["error_message"].endswith("...")
    assert len(row["error_message"]) == 243


def test_collect_step_summary_includes_collection_warnings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "summary.md"
    response = _response(403, text="secondary")
    secondary = run.collect_mod.SecondaryRateLimitError(
        "https://api.github.test/traffic",
        response,
        7,
        datetime(2026, 5, 16, 12, 7, tzinfo=timezone.utc),
        "Retry-After",
    )
    status_rows = [
        {"status": "ok_with_data"},
        {"status": "ok_zero_data"},
        {"status": "skipped_unavailable"},
    ]

    run.collect_mod._reset_runtime_state()
    run.collect_mod._record_network_warning(
        "https://api.github.test/repos",
        2,
        requests.Timeout("slow"),
    )
    run.collect_mod._REPO_DETAIL_WARNINGS.append("detail fallback used")
    run.collect_mod._REPO_COMMUNITY_WARNINGS.append("community profile skipped")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", summary_path.as_posix())

    run.collect_mod._write_step_summary(
        "failed",
        errors=["demo/error"],
        secondary_limit=secondary,
        skipped_repos=["demo/missing"],
        status_rows=status_rows,
    )

    summary = summary_path.read_text(encoding="utf-8")
    assert "- Repositories with errors: demo/error" in summary
    assert "- Repositories skipped as unavailable: demo/missing" in summary
    assert "- Repositories collected with data: 1" in summary
    assert "- Retry after: `7` second(s)" in summary
    assert "Network Warnings" in summary
    assert "detail fallback used" in summary
    assert "community profile skipped" in summary


def test_collect_pacing_waits_after_completed_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []

    run.collect_mod._LAST_REQUEST_COMPLETED_AT = 100.0
    monkeypatch.setattr(run.collect_mod.random, "uniform", lambda _low, _high: 0.75)
    monkeypatch.setattr(run.collect_mod.time, "monotonic", lambda: 100.2)
    monkeypatch.setattr(run.collect_mod.time, "sleep", sleeps.append)

    run.collect_mod._pace_request()

    assert sleeps == [pytest.approx(0.55)]


def test_collect_perform_get_marks_request_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _response(200, payload={"ok": True})

    def fake_get(
        url: str,
        *,
        headers: run.collect_mod.Headers,
        timeout: int,
    ) -> requests.Response:
        assert url == "https://api.github.test/repos"
        assert headers == {"Authorization": "Bearer test"}
        assert timeout == 15
        return response

    monkeypatch.setattr(run.collect_mod, "_pace_request", lambda: None)
    monkeypatch.setattr(run.collect_mod.requests, "get", fake_get)
    monkeypatch.setattr(run.collect_mod.time, "monotonic", lambda: 123.4)

    assert (
        run.collect_mod._perform_get(
            "https://api.github.test/repos",
            {"Authorization": "Bearer test"},
            15,
        )
        is response
    )
    assert run.collect_mod._LAST_REQUEST_COMPLETED_AT == 123.4


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


def test_collect_fetch_json_raises_after_network_retries(
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
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(run.collect_mod, "_perform_get", fake_get)
    monkeypatch.setattr(run.collect_mod.time, "sleep", lambda _seconds: None)

    with pytest.raises(requests.ConnectionError):
        run.collect_mod.fetch_json("https://api.github.test/repos", {})

    assert attempts == run.collect_mod.MAX_RETRIES


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


def test_collect_fetch_json_raises_plain_not_found_without_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        run.collect_mod,
        "_perform_get",
        lambda url, headers, timeout: _response(404, text="missing"),
    )

    with pytest.raises(requests.HTTPError):
        run.collect_mod.fetch_json("https://api.github.test/repos/demo/missing", {})

    assert "returned 404" in capsys.readouterr().out


def test_collect_fetch_json_raises_after_retryable_server_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        run.collect_mod,
        "_perform_get",
        lambda url, headers, timeout: _response(500, text="server error"),
    )
    monkeypatch.setattr(run.collect_mod.time, "sleep", lambda _seconds: None)

    with pytest.raises(requests.HTTPError) as exc_info:
        run.collect_mod.fetch_json("https://api.github.test/repos", {})

    assert "500 Server Error" in str(exc_info.value)


def test_discover_repositories_uses_installation_listing_for_github_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls: list[str] = []

    def fake_fetch_json(url: str, _headers: run.collect_mod.Headers) -> Any:
        urls.append(url)
        if "page=1" in url:
            return {
                "total_count": 1,
                "repositories": [
                    {
                        "full_name": "demo/repo",
                        "permissions": {"pull": True},
                    }
                ],
            }
        return {"total_count": 1, "repositories": []}

    monkeypatch.setattr(run.collect_mod, "fetch_json", fake_fetch_json)
    monkeypatch.setenv("REPONOMICS_USE_GITHUB_APP", "true")

    discovered = run.collect_mod.discover_repositories({})

    assert discovered == [{"full_name": "demo/repo", "permissions": {"pull": True}}]
    assert urls[0].startswith("https://api.github.com/installation/repositories?")
    assert "per_page=100" in urls[0]
    assert "page=1" in urls[0]


def test_discover_repositories_paginates_user_repository_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls: list[str] = []
    first_page = [
        {"full_name": f"demo/repo-{index}", "permissions": {"push": True}}
        for index in range(run.collect_mod.REPO_DISCOVERY_PAGE_SIZE)
    ]
    second_page = [{"full_name": "demo/final", "permissions": {"push": True}}]

    def fake_fetch_json(url: str, _headers: run.collect_mod.Headers) -> Any:
        urls.append(url)
        return first_page if "&page=1" in url else second_page

    monkeypatch.delenv("REPONOMICS_USE_GITHUB_APP", raising=False)
    monkeypatch.setattr(run.collect_mod, "fetch_json", fake_fetch_json)

    discovered = run.collect_mod.discover_repositories({})

    assert len(discovered) == run.collect_mod.REPO_DISCOVERY_PAGE_SIZE + 1
    assert "affiliation=owner,collaborator,organization_member" in urls[0]
    assert "page=2" in urls[1]


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"total_count": 1, "items": []},
    ],
)
def test_discover_repositories_rejects_malformed_app_responses(
    monkeypatch: pytest.MonkeyPatch,
    payload: Any,
) -> None:
    monkeypatch.setenv("REPONOMICS_USE_GITHUB_APP", "true")
    monkeypatch.setattr(run.collect_mod, "fetch_json", lambda _url, _headers: payload)

    with pytest.raises(requests.HTTPError):
        run.collect_mod.discover_repositories({})


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
    assert sorted(metadata) == sorted(resolved)
    assert updated_manifest["selection_state"] == {
        "auto_seeded_at": "2026-01-01T00:00:00Z",
        "auto_cutoff_created_at": "2025-03-01T00:00:00Z",
    }


def test_resolve_repositories_accepts_pull_only_permissions_for_github_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovered: list[run.collect_mod.RepoMetadata] = [
        {
            "full_name": "demo/read-only",
            "permissions": {"pull": True, "push": False, "admin": False},
            "created_at": "2025-01-01T00:00:00Z",
        }
    ]

    monkeypatch.setenv("REPONOMICS_USE_GITHUB_APP", "true")
    monkeypatch.setattr(run.collect_mod, "discover_repositories", lambda _headers: discovered)
    config: dict[str, Any] = {
        "include_only": [],
        "include": [],
        "exclude": [],
        "max_repos": 5,
        "include_others": True,
        "include_private": True,
        "include_new": True,
    }
    manifest: dict[str, Any] = {"selection_state": {"auto_seeded_at": "", "auto_cutoff_created_at": ""}}

    resolved, _updated_manifest, metadata = run.collect_mod.resolve_repositories({}, config, manifest)

    assert resolved == ["demo/read-only"]
    assert sorted(metadata) == ["demo/read-only"]


def test_resolve_repositories_include_only_warns_and_exits_when_empty(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    discovered = [
        {
            "full_name": "demo/fork",
            "permissions": {"push": True},
            "fork": True,
        }
    ]
    config: dict[str, Any] = {
        "include_only": ["demo/fork", "demo/missing"],
        "include": [],
        "exclude": [],
        "max_repos": 5,
        "include_others": False,
        "include_private": True,
        "include_new": True,
    }

    monkeypatch.setattr(run.collect_mod, "discover_repositories", lambda _headers: discovered)

    with pytest.raises(SystemExit):
        run.collect_mod.resolve_repositories({}, config, {})

    output = capsys.readouterr().out
    assert "include_only repos were not eligible" in output
    assert "no eligible repositories remain in 'include_only'" in output


def test_resolve_repositories_clears_auto_cutoff_when_auto_fill_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovered = [
        {
            "full_name": "demo/manual",
            "permissions": {"admin": True},
            "created_at": "2025-01-01T00:00:00Z",
        }
    ]
    config: dict[str, Any] = {
        "include_only": [],
        "include": ["demo/manual", "demo/manual"],
        "exclude": [],
        "max_repos": 5,
        "include_others": False,
        "include_private": True,
        "include_new": True,
    }
    manifest: dict[str, Any] = {
        "selection_state": {
            "auto_seeded_at": "2026-01-01T00:00:00Z",
            "auto_cutoff_created_at": "2025-01-01T00:00:00Z",
        }
    }

    monkeypatch.setattr(run.collect_mod, "discover_repositories", lambda _headers: discovered)

    resolved, updated_manifest, metadata = run.collect_mod.resolve_repositories(
        {},
        config,
        manifest,
    )

    assert resolved == ["demo/manual"]
    assert sorted(metadata) == ["demo/manual"]
    assert updated_manifest["selection_state"]["auto_cutoff_created_at"] == ""


def test_resolve_repositories_exits_when_no_repos_are_eligible(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config: dict[str, Any] = {
        "include_only": [],
        "include": [],
        "exclude": [],
        "max_repos": 5,
        "include_others": False,
        "include_private": True,
        "include_new": True,
    }

    monkeypatch.setattr(run.collect_mod, "discover_repositories", lambda _headers: [])

    with pytest.raises(SystemExit):
        run.collect_mod.resolve_repositories({}, config, {})

    assert "no eligible repositories found" in capsys.readouterr().out


def test_collect_views_clones_joins_views_and_clone_only_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = {
        "views": {
            "views": [
                {"timestamp": "2026-05-15T00:00:00Z", "count": 10, "uniques": 4}
            ]
        },
        "clones": {
            "clones": [
                {"timestamp": "2026-05-15T00:00:00Z", "count": 3, "uniques": 2},
                {"timestamp": "2026-05-16T00:00:00Z", "count": 7, "uniques": 5},
            ]
        },
    }

    def fake_fetch_json(
        url: str,
        _headers: run.collect_mod.Headers,
        allow_not_found: bool = False,
    ) -> Any:
        assert allow_not_found is True
        return payloads["clones" if url.endswith("/clones") else "views"]

    monkeypatch.setattr(run.collect_mod, "fetch_json", fake_fetch_json)

    rows = run.collect_mod.collect_views_clones(
        "demo/reponomics",
        {},
        "2026-05-16T12:00:00Z",
    )

    assert rows == [
        {
            "repo": "demo/reponomics",
            "ts": "2026-05-15",
            "views_count": 10,
            "views_uniques": 4,
            "clones_count": 3,
            "clones_uniques": 2,
            "captured_at": "2026-05-16T12:00:00Z",
            "source": "api",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
        {
            "repo": "demo/reponomics",
            "ts": "2026-05-16",
            "views_count": 0,
            "views_uniques": 0,
            "clones_count": 7,
            "clones_uniques": 5,
            "captured_at": "2026-05-16T12:00:00Z",
            "source": "api",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
    ]


def test_collect_referrers_and_paths_shape_endpoint_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fetch_json(
        url: str,
        _headers: run.collect_mod.Headers,
        allow_not_found: bool = False,
    ) -> Any:
        assert allow_not_found is True
        if url.endswith("/referrers"):
            return [{"referrer": "github.com", "count": 5, "uniques": 3}]
        return [{"path": "/demo/reponomics", "title": "Overview", "count": 8, "uniques": 4}]

    monkeypatch.setattr(run.collect_mod, "fetch_json", fake_fetch_json)

    assert run.collect_mod.collect_referrers(
        "demo/reponomics",
        {},
        "2026-05-16T12:00:00Z",
    ) == [
        {
            "repo": "demo/reponomics",
            "captured_at": "2026-05-16T12:00:00Z",
            "referrer": "github.com",
            "count": 5,
            "uniques": 3,
            "schema_version": run.storage.SCHEMA_VERSION,
        }
    ]
    assert run.collect_mod.collect_paths(
        "demo/reponomics",
        {},
        "2026-05-16T12:00:00Z",
    ) == [
        {
            "repo": "demo/reponomics",
            "captured_at": "2026-05-16T12:00:00Z",
            "path": "/demo/reponomics",
            "title": "Overview",
            "count": 8,
            "uniques": 4,
            "schema_version": run.storage.SCHEMA_VERSION,
        }
    ]


def test_collect_repo_detail_and_community_profile_reject_non_object_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run.collect_mod, "fetch_json", lambda _url, _headers: [])

    with pytest.raises(requests.HTTPError, match="repository detail response"):
        run.collect_mod.collect_repo_detail("demo/reponomics", {})
    with pytest.raises(requests.HTTPError, match="community profile response"):
        run.collect_mod.collect_repo_community_profile("demo/reponomics", {})


def test_collect_repo_metrics_normalizes_invalid_community_profile() -> None:
    rows = run.collect_mod.collect_repo_metrics(
        "demo/reponomics",
        {"stargazers_count": 1, "subscribers_count": 2, "forks_count": 3},
        {"health_percentage": "unknown", "files": []},
        "2026-05-16T12:00:00Z",
    )

    assert rows[0]["community_health_percentage"] == ""
    assert rows[0]["community_has_code_of_conduct"] == ""
    assert rows[0]["stargazers_count"] == 1


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
    community_calls: list[str] = []

    def fake_fetch_json(url: str, headers, allow_not_found: bool = False):
        assert allow_not_found is False
        if url.endswith("/community/profile"):
            community_calls.append(url)
            return {
                "health_percentage": 71,
                "documentation": "https://github.com/docs",
                "updated_at": "2026-05-16T10:00:00Z",
                "files": {
                    "code_of_conduct": None,
                    "contributing": {"html_url": "https://example.com/contributing"},
                    "issue_template": None,
                    "pull_request_template": None,
                    "readme": {"html_url": "https://example.com/readme"},
                    "license": {"html_url": "https://example.com/license"},
                },
            }
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
    assert community_calls == [
        "https://api.github.com/repos/demo/one/community/profile",
        "https://api.github.com/repos/demo/two/community/profile",
    ]
    with (config.data_dir / "repo-metrics.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    with (config.data_dir / "collection-status.csv").open(newline="", encoding="utf-8") as handle:
        status_rows = list(csv.DictReader(handle))
    assert [row["repo"] for row in rows] == ["demo/one", "demo/two"]
    assert [row["subscribers_count"] for row in rows] == ["21", "22"]
    assert [row["source"] for row in rows] == ["repo-detail", "repo-detail"]
    assert [row["repo"] for row in status_rows] == ["demo/one", "demo/two"]
    assert [row["status"] for row in status_rows] == ["ok_zero_data", "ok_zero_data"]


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
    monkeypatch.setattr(run.collect_mod, "collect_repo_community_profile", lambda repo, headers: {})
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
    with (config.data_dir / "collection-status.csv").open(newline="", encoding="utf-8") as handle:
        status_rows = list(csv.DictReader(handle))
    assert traffic_rows[-1]["repo"] == "demo/reponomics"
    assert traffic_rows[-1]["views_count"] == "5"
    assert metric_rows[-1]["source"] == "discovery-fallback"
    assert metric_rows[-1]["subscribers_count"] == "3"
    assert metric_rows[-1]["stargazers_count"] == "15"
    assert status_rows[-1]["status"] == "ok_with_data"
    assert status_rows[-1]["metric_source"] == "discovery-fallback"


def test_community_profile_failure_records_warning_without_losing_metrics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("include_only:\n  - demo/reponomics\n", encoding="utf-8")
    summary_path = tmp_path / "summary.md"
    config = _config(tmp_path, config_path=config_path)
    discovered = [
        {
            "full_name": "demo/reponomics",
            "permissions": {"push": True},
            "fork": False,
            "archived": False,
            "disabled": False,
            "private": False,
            "created_at": "2025-01-01T00:00:00Z",
        }
    ]

    def raise_community_error(repo: str, headers):
        raise requests.HTTPError("community unavailable")

    monkeypatch.setenv("GITHUB_STEP_SUMMARY", summary_path.as_posix())
    monkeypatch.setattr(run.collect_mod, "get_headers", lambda: {})
    monkeypatch.setattr(run.collect_mod, "validate_token", lambda headers: None)
    monkeypatch.setattr(run.collect_mod, "discover_repositories", lambda headers: discovered)
    monkeypatch.setattr(
        run.collect_mod,
        "collect_repo_detail",
        lambda repo, headers: {
            "id": 123,
            "node_id": "R_123",
            "stargazers_count": 15,
            "subscribers_count": 3,
            "forks_count": 2,
        },
    )
    monkeypatch.setattr(
        run.collect_mod,
        "collect_repo_community_profile",
        raise_community_error,
    )
    monkeypatch.setattr(run.collect_mod, "collect_views_clones", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_referrers", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_paths", lambda *args: [])

    run.run_collect(config, restore_artifact=False, execute_collect=True)

    with (config.data_dir / "repo-metrics.csv").open(newline="", encoding="utf-8") as handle:
        metric_rows = list(csv.DictReader(handle))
    summary = summary_path.read_text(encoding="utf-8")
    assert metric_rows[-1]["source"] == "repo-detail"
    assert metric_rows[-1]["community_health_percentage"] == ""
    assert "Community Profile Warnings" in summary
    assert "community unavailable" in summary


def test_collect_records_skipped_unavailable_repo_status(
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

    unavailable = run.collect_mod.RepoUnavailableError(
        "https://api.github.com/repos/demo/reponomics/traffic/views",
        _response(404, text="Not Found"),
        attempts=3,
    )

    monkeypatch.setattr(run.collect_mod, "get_headers", lambda: {})
    monkeypatch.setattr(run.collect_mod, "validate_token", lambda headers: None)
    monkeypatch.setattr(run.collect_mod, "discover_repositories", lambda headers: discovered)
    monkeypatch.setattr(run.collect_mod, "collect_repo_detail", lambda repo, headers: discovered[0])
    monkeypatch.setattr(run.collect_mod, "collect_repo_community_profile", lambda repo, headers: {})

    def raise_unavailable(repo: str, headers, captured_at: str):
        raise unavailable

    monkeypatch.setattr(run.collect_mod, "collect_views_clones", raise_unavailable)

    run.run_collect(config, restore_artifact=False, execute_collect=True)

    with (config.data_dir / "traffic-log.csv").open(newline="", encoding="utf-8") as handle:
        traffic_rows = list(csv.DictReader(handle))
    with (config.data_dir / "collection-status.csv").open(newline="", encoding="utf-8") as handle:
        status_rows = list(csv.DictReader(handle))

    assert traffic_rows == []
    assert len(status_rows) == 1
    assert status_rows[0]["repo"] == "demo/reponomics"
    assert status_rows[0]["status"] == "skipped_unavailable"


def test_collect_secondary_rate_limit_aborts_with_status_and_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("include_only:\n  - demo/reponomics\n", encoding="utf-8")
    summary_path = tmp_path / "summary.md"
    config = _config(tmp_path, config_path=config_path)
    discovered = [
        {
            "full_name": "demo/reponomics",
            "permissions": {"push": True},
            "fork": False,
            "archived": False,
            "disabled": False,
            "private": False,
            "created_at": "2025-01-01T00:00:00Z",
        }
    ]
    secondary = run.collect_mod.SecondaryRateLimitError(
        "https://api.github.test/detail",
        _response(403, text="secondary"),
        60,
        datetime(2026, 5, 16, 13, 0, tzinfo=timezone.utc),
        "default-minimum",
    )

    def raise_secondary(repo: str, headers):
        raise secondary

    monkeypatch.setenv("GITHUB_STEP_SUMMARY", summary_path.as_posix())
    monkeypatch.setattr(run.collect_mod, "get_headers", lambda: {})
    monkeypatch.setattr(run.collect_mod, "validate_token", lambda headers: None)
    monkeypatch.setattr(run.collect_mod, "discover_repositories", lambda headers: discovered)
    monkeypatch.setattr(run.collect_mod, "collect_repo_detail", raise_secondary)

    with pytest.raises(SystemExit):
        run.run_collect(config, restore_artifact=False, execute_collect=True)

    with (config.data_dir / "collection-status.csv").open(newline="", encoding="utf-8") as handle:
        status_rows = list(csv.DictReader(handle))
    summary = summary_path.read_text(encoding="utf-8")
    assert status_rows[-1]["status"] == "error_secondary_rate_limit"
    assert status_rows[-1]["error_type"] == "SecondaryRateLimitError"
    assert "Secondary Rate Limit" in summary
    assert "default-minimum" in summary


@pytest.mark.parametrize(
    ("exc", "expected_type"),
    [
        (requests.HTTPError("traffic failed"), "HTTPError"),
        (requests.ConnectionError("network failed"), "ConnectionError"),
    ],
)
def test_collect_records_generic_collection_errors_and_exits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    exc: requests.RequestException,
    expected_type: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("include_only:\n  - demo/reponomics\n", encoding="utf-8")
    summary_path = tmp_path / "summary.md"
    config = _config(tmp_path, config_path=config_path)
    discovered = [
        {
            "full_name": "demo/reponomics",
            "permissions": {"push": True},
            "fork": False,
            "archived": False,
            "disabled": False,
            "private": False,
            "created_at": "2025-01-01T00:00:00Z",
        }
    ]

    def raise_collection_error(repo: str, headers, captured_at: str):
        raise exc

    monkeypatch.setenv("GITHUB_STEP_SUMMARY", summary_path.as_posix())
    monkeypatch.setattr(run.collect_mod, "get_headers", lambda: {})
    monkeypatch.setattr(run.collect_mod, "validate_token", lambda headers: None)
    monkeypatch.setattr(run.collect_mod, "discover_repositories", lambda headers: discovered)
    monkeypatch.setattr(
        run.collect_mod,
        "collect_repo_detail",
        lambda repo, headers: {
            "id": 123,
            "node_id": "R_123",
            "stargazers_count": 15,
            "subscribers_count": 3,
            "forks_count": 2,
        },
    )
    monkeypatch.setattr(run.collect_mod, "collect_repo_community_profile", lambda *args: {})
    monkeypatch.setattr(run.collect_mod, "collect_views_clones", raise_collection_error)

    with pytest.raises(SystemExit):
        run.run_collect(config, restore_artifact=False, execute_collect=True)

    with (config.data_dir / "collection-status.csv").open(newline="", encoding="utf-8") as handle:
        status_rows = list(csv.DictReader(handle))
    summary = summary_path.read_text(encoding="utf-8")
    assert status_rows[-1]["status"] == "error"
    assert status_rows[-1]["error_type"] == expected_type
    assert "- Outcome: **failed**" in summary
    assert "- Repositories with errors: demo/reponomics" in summary


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
            "community_health_percentage": "",
            "community_documentation": "",
            "community_updated_at": "",
            "community_content_reports_enabled": "",
            "community_has_code_of_conduct": "",
            "community_has_contributing": "",
            "community_has_issue_template": "",
            "community_has_pull_request_template": "",
            "community_has_readme": "",
            "community_has_license": "",
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
    assert "encrypted-payload" in dashboard
