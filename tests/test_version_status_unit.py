from __future__ import annotations

from typing import Any

import pytest

from dashboard_action import run


version_status = run.version_status


def test_compare_semver_handles_prerelease_precedence() -> None:
    compare = version_status.compare_semver

    assert compare("v1.2.4", "1.2.3") == 1
    assert compare("1.2.3", "1.2.3") == 0
    assert compare("1.2.3-alpha.2", "1.2.3-alpha.10") == -1
    assert compare("1.2.3", "1.2.3-rc.1") == 1


def test_latest_stable_release_filters_drafts_prereleases_and_invalid_tags() -> None:
    releases: list[dict[str, Any]] = [
        {"tag_name": "v0.4.0", "draft": True, "prerelease": False},
        {"tag_name": "v0.5.0-rc.1", "draft": False, "prerelease": True},
        {"tag_name": "latest", "draft": False, "prerelease": False},
        {"tag_name": "v0.3.0", "draft": False, "prerelease": False},
        {"tag_name": "v0.10.0", "draft": False, "prerelease": False},
    ]

    assert version_status.latest_stable_release(releases) == {
        "tag_name": "v0.10.0",
        "name": "",
        "html_url": "",
    }


def test_build_status_payload_sanitizes_title_and_reports_available_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        version_status,
        "_fetch_releases",
        lambda: [
            {
                "tag_name": "v0.3.0",
                "name": "Reponomics **minor** <script>alert(1)</script>",
                "html_url": "https://evil.example/not-the-release",
                "draft": False,
                "prerelease": False,
                "body": "Remote release bodies are ignored **entirely**.",
            }
        ],
    )

    assert version_status.build_status_payload(
        current_version="0.2.0",
        action_ref="v0.2.0",
        action_repository=version_status.ACTION_REPOSITORY,
        check_latest=True,
    ) == {
        "current_version": "0.2.0",
        "current_url": "https://github.com/reponomics/reponomics-dashboard-action/releases/tag/v0.2.0",
        "action_ref": "v0.2.0",
        "latest_version": "v0.3.0",
        "latest_title": "Reponomics minor",
        "update_available": True,
        "url": "https://github.com/reponomics/reponomics-dashboard-action/releases/tag/v0.3.0",
    }


def test_build_status_payload_compares_latest_to_runtime_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        version_status,
        "_fetch_releases",
        lambda: [
            {
                "tag_name": "v0.13.1",
                "draft": False,
                "prerelease": False,
            }
        ],
    )

    assert version_status.build_status_payload(
        current_version="0.13.1",
        action_ref="v0.13.0",
        action_repository=version_status.ACTION_REPOSITORY,
        check_latest=True,
    ) == {
        "current_version": "0.13.1",
        "current_url": "https://github.com/reponomics/reponomics-dashboard-action/releases/tag/v0.13.1",
        "action_ref": "v0.13.0",
        "latest_version": "v0.13.1",
        "update_available": False,
        "url": "https://github.com/reponomics/reponomics-dashboard-action/releases/tag/v0.13.1",
    }


def test_build_status_payload_api_failure_keeps_local_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_failure() -> list[dict[str, Any]]:
        raise RuntimeError("boom")

    monkeypatch.setattr(version_status, "_fetch_releases", raise_failure)

    assert version_status.build_status_payload(
        current_version="0.2.0",
        action_ref="v0.2.0",
        action_repository=version_status.ACTION_REPOSITORY,
        check_latest=True,
    ) == {
        "current_version": "0.2.0",
        "current_url": "https://github.com/reponomics/reponomics-dashboard-action/releases/tag/v0.2.0",
        "action_ref": "v0.2.0",
        "update_available": False,
        "url": "https://github.com/reponomics/reponomics-dashboard-action/releases",
    }


def test_fetch_releases_sends_expected_request_and_keeps_list_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_payload = [{"tag_name": "v1.0.0"}]
    calls: list[dict[str, Any]] = []

    class Response:
        def raise_for_status(self) -> None:
            calls.append({"raised": False})

        def json(self) -> list[dict[str, str]]:
            return release_payload

    def fake_get(url: str, *, headers: dict[str, str], timeout: int) -> Response:
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        return Response()

    monkeypatch.setattr(version_status.requests, "get", fake_get)

    assert version_status._fetch_releases() == release_payload
    assert calls[0]["url"] == version_status.RELEASES_API_URL
    assert calls[0]["timeout"] == version_status.REQUEST_TIMEOUT_SECONDS
    assert "Authorization" not in calls[0]["headers"]
    assert calls[1] == {"raised": False}


def test_fetch_releases_returns_empty_list_for_non_list_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"message": "not a release list"}

    def fake_get(_url: str, *, headers: dict[str, str], timeout: int) -> Response:
        assert "Authorization" not in headers
        assert timeout == version_status.REQUEST_TIMEOUT_SECONDS
        return Response()

    monkeypatch.setattr(version_status.requests, "get", fake_get)

    assert version_status._fetch_releases() == []
