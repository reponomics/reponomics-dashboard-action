from __future__ import annotations

import json
from typing import Any

import pytest

from traffic_report_action import run


release_notice = run.release_notice


def _block(metadata: dict[str, Any]) -> str:
    return f"<!-- reponomics-update {json.dumps(metadata, separators=(',', ':'))} -->"


def _valid_metadata(**overrides: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "title": "Upgrade available",
        "summary": "Install the newer action release.",
    }
    metadata.update(overrides)
    return metadata


def test_validate_update_block_reports_missing_and_duplicate_blocks() -> None:
    assert release_notice.validate_update_block("plain release notes") == [
        "missing reponomics-update block"
    ]
    assert release_notice.validate_update_block("plain release notes", require_block=False) == []

    errors = release_notice.validate_update_block(
        "\n".join([
            _block(_valid_metadata(title="First notice")),
            "release notes between notices",
            _block(_valid_metadata(title="Second notice")),
        ])
    )

    assert errors == ["release body must contain exactly one reponomics-update block"]


def test_validate_update_block_reports_oversized_body_and_notice_json() -> None:
    assert release_notice.validate_update_block("x" * (release_notice.MAX_BODY_BYTES + 1)) == [
        f"release body exceeds {release_notice.MAX_BODY_BYTES} bytes"
    ]

    errors = release_notice.validate_update_block(
        _block(_valid_metadata(summary="x" * (release_notice.MAX_NOTICE_BYTES + 1)))
    )

    assert f"reponomics-update JSON exceeds {release_notice.MAX_NOTICE_BYTES} bytes" in errors


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        (
            _valid_metadata(min_runtime_version="1.2", max_runtime_version="2.0.0"),
            "min_runtime_version must be a semantic version string",
        ),
        (
            _valid_metadata(min_runtime_version="2.0.0", max_runtime_version="1.9.9"),
            "min_runtime_version must not exceed max_runtime_version",
        ),
        (
            _valid_metadata(action_refs=["v0.1.0", ""]),
            "action_refs entries must be non-empty strings",
        ),
    ],
)
def test_validate_update_block_reports_version_and_action_ref_edges(
    metadata: dict[str, Any],
    expected: str,
) -> None:
    assert expected in release_notice.validate_update_block(_block(metadata))


def test_find_update_notice_filters_action_refs_and_sanitizes_notice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    releases = [
        {
            "tag_name": "v0.4.0",
            "draft": False,
            "prerelease": False,
            "body": _block(
                _valid_metadata(
                    title="Wrong ref",
                    summary="This release targets another ref.",
                    action_refs=["v9"],
                )
            ),
        },
        {
            "tag_name": "v0.3.0",
            "draft": False,
            "prerelease": False,
            "html_url": "https://evil.example/not-the-release",
            "body": _block(
                _valid_metadata(
                    title="Use <b>this</b> `[release]`",
                    summary="<script>alert(1)</script>Readable **summary**",
                    action_refs=["v0.2"],
                )
            ),
        },
    ]

    monkeypatch.setattr(release_notice, "_fetch_releases", lambda _token: releases)

    assert release_notice.find_update_notice(
        token="",
        current_version="0.2.0",
        action_ref="v0.2",
        action_repository=release_notice.ACTION_REPOSITORY,
    ) == {
        "version": "v0.3.0",
        "title": "Use this release",
        "summary": "Readable summary",
        "url": "https://github.com/reponomics/reponomics-dashboard-action/releases/tag/v0.3.0",
    }


def test_find_update_notice_rejects_invalid_current_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_fetch_releases(_token: str) -> list[dict[str, Any]]:
        nonlocal called
        called = True
        return [
            {
                "tag_name": "v0.3.0",
                "draft": False,
                "prerelease": False,
                "body": _block(_valid_metadata()),
            }
        ]

    monkeypatch.setattr(release_notice, "_fetch_releases", fake_fetch_releases)

    assert (
        release_notice.find_update_notice(
            token="",
            current_version="latest",
            action_ref="main",
            action_repository=release_notice.ACTION_REPOSITORY,
        )
        is None
    )
    assert called is True


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

    monkeypatch.setattr(release_notice.requests, "get", fake_get)

    assert release_notice._fetch_releases("ghp_token") == release_payload
    assert calls[0]["url"] == release_notice.RELEASES_API_URL
    assert calls[0]["timeout"] == release_notice.REQUEST_TIMEOUT_SECONDS
    assert calls[0]["headers"]["Authorization"] == "Bearer ghp_token"
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
        assert timeout == release_notice.REQUEST_TIMEOUT_SECONDS
        return Response()

    monkeypatch.setattr(release_notice.requests, "get", fake_get)

    assert release_notice._fetch_releases("") == []
