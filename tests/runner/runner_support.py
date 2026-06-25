from __future__ import annotations

import base64
import csv
import gzip
from html import unescape
from html.parser import HTMLParser
import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
import requests

from dashboard_action import run
from scripts import dashboard_scenarios


OLD_KEY = "old-dashboard-secret-" + ("x" * 40)
NEXT_KEY = "next-dashboard-secret-" + ("y" * 40)
FIXTURES_DIR = Path(__file__).parents[1] / "fixtures"
VERSION_STATUS_TEST_VERSION = "0.13.1"
VERSION_STATUS_TEST_TAG = f"v{VERSION_STATUS_TEST_VERSION}"
VERSION_STATUS_RELEASES_URL = "https://github.com/reponomics/reponomics-dashboard-action/releases"
PUBLISHED_CORE_RUNTIME_SOURCES = [
    "assets/dashboard/chart-adapter.js",
    "assets/dashboard/state.js",
    "assets/dashboard/data-provider.js",
    "assets/dashboard/theme.js",
    "assets/dashboard/format.js",
    "assets/dashboard/selection.js",
    "assets/dashboard/quality-calendar.js",
    "assets/dashboard/series.js",
    "assets/dashboard/momentum.js",
    "assets/dashboard/chart-options.js",
    "assets/dashboard/controls.js",
    "assets/dashboard/charts.js",
    "assets/dashboard/tables.js",
    "assets/dashboard/story.js",
    "assets/dashboard/controller.js",
    "assets/dashboard/app.js",
    "assets/dashboard/json-assets.js",
    "assets/dashboard/secure-core.js",
    "assets/dashboard/theme-preload.js",
    "assets/dashboard/entry-public.js",
    "assets/dashboard/entry-secure.js",
]
CONTEXTUAL_DATA_FILES = {
    "repo-commits.csv",
    "repo-commit-observations.csv",
    "repo-releases.csv",
    "repo-release-assets.csv",
    "repo-languages.csv",
    "repo-topics.csv",
    "repo-issue-pr-snapshots.csv",
    "repo-issue-label-snapshots.csv",
    "repo-code-frequency-weekly.csv",
    "repo-contributor-activity-weekly.csv",
    "collection-endpoints.csv",
    "repo-event-index.csv",
}


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


def _asset_text(index_path: Path, name: str) -> str:
    return (index_path.parent / "assets" / name).read_text(encoding="utf-8")


def _published_script_sources(*, encrypted: bool) -> list[str]:
    return [
        "assets/chart.umd.min.js",
        "assets/dashboard/theme-preload.js",
        "assets/dashboard/entry-secure.js" if encrypted else "assets/dashboard/entry-public.js",
    ]


def _published_runtime_text(index_path: Path, *, encrypted: bool) -> str:
    asset_names = [source.removeprefix("assets/") for source in PUBLISHED_CORE_RUNTIME_SOURCES]
    return "\n".join(_asset_text(index_path, name) for name in asset_names)


def _script_json(html: str, script_id: str) -> dict[str, Any]:
    match = re.search(
        rf'<script id="{re.escape(script_id)}" type="application/json">(.*?)</script>',
        html,
        flags=re.S,
    )
    if not match:
        raise AssertionError(f"missing script payload for {script_id}")
    return json.loads(match.group(1))


def _asset_json(index_path: Path, asset_name: str) -> dict[str, Any]:
    return json.loads((index_path.parent / "assets" / asset_name).read_text(encoding="utf-8"))


def _dashboard_json(
    index_path: Path,
    document: str,
    legacy_script_id: str,
    asset_name: str,
) -> dict[str, Any]:
    try:
        return _script_json(document, legacy_script_id)
    except AssertionError:
        return _asset_json(index_path, asset_name)


def _write_dashboard_json(
    index_path: Path,
    document: str,
    legacy_script_id: str,
    asset_name: str,
    value: dict[str, Any],
) -> None:
    try:
        _script_json(document, legacy_script_id)
    except AssertionError:
        (index_path.parent / "assets" / asset_name).write_text(
            json.dumps(value, separators=(",", ":")),
            encoding="utf-8",
        )
    else:
        index_path.write_text(
            _replace_script_json(document, legacy_script_id, value),
            encoding="utf-8",
        )


def _runtime_const_json(html: str, const_name: str) -> dict[str, Any]:
    match = re.search(
        rf"const {re.escape(const_name)} = (.*?);\nrenderDashboard\({re.escape(const_name)}\);",
        html,
        flags=re.S,
    )
    if not match:
        raise AssertionError(f"missing runtime const payload for {const_name}")
    return json.loads(match.group(1))


def _b64url_decode(value: str) -> bytes:
    padded = value + ("=" * ((4 - len(value) % 4) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _tamper_encrypted_token(token: str) -> str:
    iv_value, ciphertext_value = token.split(".", 1)
    ciphertext = bytearray(_b64url_decode(ciphertext_value))
    ciphertext[0] ^= 1
    return f"{iv_value}.{_b64url_encode(bytes(ciphertext))}"


def _decrypt_dashboard_blob(blob: str, key: bytes) -> dict[str, Any]:
    iv_value, ciphertext_value = blob.split(".", 1)
    plaintext = run.render_dashboard.AESGCM(key).decrypt(
        _b64url_decode(iv_value),
        _b64url_decode(ciphertext_value),
        None,
    )
    return json.loads(gzip.decompress(plaintext))


def _decrypt_encrypted_dashboard_data(
    encrypted_dashboard_data: dict[str, Any], dashboard_key: str = OLD_KEY
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    salt = base64.b64decode(encrypted_dashboard_data["salt"])
    key = run.render_dashboard._derive_key(dashboard_key, salt)
    summary = _decrypt_dashboard_blob(encrypted_dashboard_data["summary"], key)
    chunks = {
        chunk_id: _decrypt_dashboard_blob(blob, key)
        for chunk_id, blob in encrypted_dashboard_data["chunks"].items()
    }
    return summary, chunks


def _decode_plaintext_dashboard_data(
    plaintext_dashboard_data: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    chunks = {
        chunk_id: json.loads(chunk)
        for chunk_id, chunk in plaintext_dashboard_data["chunks"].items()
    }
    return plaintext_dashboard_data["summary"], chunks


def _replace_script_json(html: str, script_id: str, value: dict[str, Any]) -> str:
    replacement = json.dumps(value, separators=(",", ":"))
    pattern = rf'(<script id="{re.escape(script_id)}" type="application/json">).*?(</script>)'
    return re.sub(
        pattern, lambda match: match.group(1) + replacement + match.group(2), html, flags=re.S
    )


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
        "comparison_secret": "",
        "data_mode": "encrypted",
        "repo_is_public": False,
        "config_path": tmp_path / "config.yaml",
        "data_dir": tmp_path / "data",
        "retention_days": 90,
        "auto_doctor_every_n_days": 0,
        "artifact_run_id": "",
        "publish_pages_requested": True,
        "generate_readme": False,
        "pages_index_path": tmp_path / "docs" / "index.html",
        "readme_path": tmp_path / "README.md",
        "incident_confirm_mode": "",
        "incident_confirm_purge": "",
        "incident_confirm_next_secret": "",
        "incident_confirm_irreversible": "",
        "action_ref": "v0.1.0",
        "action_repository": "reponomics/reponomics-dashboard-action",
    }
    values.update(overrides)
    return run.RuntimeConfig(**values)


def _write_runtime_config(config_path: Path, **overrides: Any) -> None:
    values: dict[str, Any] = {
        "i_have_read_the_readme": True,
        "data_mode": "encrypted",
        "publish_pages_dashboard": True,
        "publish_readme_dashboard": False,
        "artifact_retention_days": 90,
        "use_github_app": False,
        "auto_doctor_every_n_days": 0,
    }
    values.update(overrides)

    def yaml_value(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "".join(f"{key}: {yaml_value(value)}\n" for key, value in values.items()),
        encoding="utf-8",
    )


def _stub_context_collectors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run.collect_mod, "collect_commit_history", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_release_context", lambda *args: ([], []))
    monkeypatch.setattr(run.collect_mod, "collect_languages", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_topics", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_issue_pr_snapshot", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_issue_label_snapshots", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_code_frequency_weekly", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_contributor_activity_weekly", lambda *args: [])


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


def _seed_scenario(data_dir: Path, dataset: dashboard_scenarios.ScenarioDataset) -> None:
    _write_csv(data_dir / "traffic-log.csv", run.storage.LOG_FIELDS, dataset.daily_rows)
    _write_csv(data_dir / "traffic-daily.csv", run.storage.DAILY_FIELDS, dataset.daily_rows)
    _write_csv(
        data_dir / "traffic-snapshots.csv",
        run.storage.SNAPSHOT_FIELDS,
        [],
    )
    _write_csv(
        data_dir / "traffic-referrers.csv",
        run.storage.REFERRER_FIELDS,
        dataset.referrer_rows,
    )
    _write_csv(data_dir / "traffic-paths.csv", run.storage.PATH_FIELDS, dataset.path_rows)
    _write_csv(
        data_dir / "repo-metrics.csv",
        run.storage.REPO_METRIC_FIELDS,
        dataset.metric_rows,
    )
    _write_csv(
        data_dir / "collection-status.csv",
        run.storage.COLLECTION_STATUS_FIELDS,
        dataset.status_rows,
    )
    (data_dir / "manifest.json").write_text(
        json.dumps({"schema_version": run.storage.SCHEMA_VERSION}),
        encoding="utf-8",
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


def _report_stage(report: dict[str, Any], name: str) -> dict[str, str]:
    for stage in report["stages"]:
        if stage["name"] == name:
            return stage
    raise AssertionError(f"missing doctor report stage: {name}")


def _result_stage(result: Any, name: str) -> Any:
    for stage in result.stages:
        if stage.name == name:
            return stage
    raise AssertionError(f"missing doctor result stage: {name}")


def _secret_result_stage(result: Any, label: str, name: str) -> Any:
    for secret_result in result.secret_results:
        if secret_result.label != label:
            continue
        for stage in secret_result.stages:
            if stage.name == name:
                return stage
    raise AssertionError(f"missing doctor secret stage: {label}:{name}")
