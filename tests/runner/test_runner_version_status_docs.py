from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import requests

from dashboard_action import run

from runner_support import (
    VERSION_STATUS_RELEASES_URL,
    VERSION_STATUS_TEST_TAG,
    VERSION_STATUS_TEST_VERSION,
    _config,
    _seed_log,
    _version_status_release_url,
    _version_status_tag,
)


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
    assert f'>your version</span><span class="badge-value">{current_tag}</span>' in dashboard
    assert '>latest version</span><span class="badge-value">v0.2.0</span>' in dashboard
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
    current_value = (
        f'>your version</span><span class="badge-value">{VERSION_STATUS_TEST_TAG}</span>'
    )
    latest_value = f'>latest version</span><span class="badge-value">{latest_display}</span>'

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


def test_publish_footer_docs_link_uses_existing_local_managed_docs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    managed_docs_dir = tmp_path / "docs" / "reponomics"
    managed_docs_dir.mkdir(parents=True)
    (managed_docs_dir / "README.md").write_text("local docs\n", encoding="utf-8")
    config = _config(tmp_path, mode="publish", generate_readme=True)
    _seed_log(config.data_dir)

    run.run_publish(config, restore_artifact=False)

    readme = config.readme_path.read_text(encoding="utf-8")
    assert (tmp_path / "docs" / "reponomics" / "README.md").is_file()
    assert not (tmp_path / "docs" / "README.md").exists()
    assert "[Setup & Docs](docs/reponomics/README.md)" in readme
    assert "[Setup & Docs](docs/README.md)" not in readme


def test_publish_surfaces_blocked_managed_docs_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run, "VERSION", VERSION_STATUS_TEST_VERSION)
    monkeypatch.setenv("REPONOMICS_UPDATE_DOCS_STATE", "manifest_inconsistent")
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
    assert (
        f"[![Your version: {VERSION_STATUS_TEST_TAG}](docs/assets/action-version-current.svg)]"
        in readme
    )
    assert "[![Latest version: unknown](docs/assets/action-version-latest.svg)]" in readme
    assert '>latest version</span><span class="badge-value">unknown</span>' in dashboard
    assert "View latest updates" in readme
    assert "View latest updates" in dashboard
    assert "Check latest release" not in readme
    assert "Check latest release" not in dashboard
