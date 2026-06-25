from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import requests

from dashboard_action import run

from runner_support import _response


def test_repo_metrics_registry_creates_growth_snapshot_header(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"

    changed = run.storage.migrate_schema(data_dir.as_posix())

    assert changed is True
    header = (data_dir / "repo-metrics.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == run.storage.REPO_METRIC_FIELDS
    assert run.storage.REPO_METRIC_FIELDS == [
        "repo",
        "repo_id",
        "node_id",
        "ts",
        "captured_at",
        "stargazers_count",
        "subscribers_count",
        "forks_count",
        "open_issues_count",
        "size_kb",
        "created_at",
        "pushed_at",
        "updated_at",
        "language",
        "visibility",
        "default_branch",
        "has_pages",
        "has_discussions",
        "archived",
        "disabled",
        "community_health_percentage",
        "community_documentation",
        "community_updated_at",
        "community_content_reports_enabled",
        "community_has_code_of_conduct",
        "community_has_contributing",
        "community_has_issue_template",
        "community_has_pull_request_template",
        "community_has_readme",
        "community_has_license",
        "source",
        "schema_version",
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
    manifest: dict[str, Any] = {
        "selection_state": {"auto_seeded_at": "", "auto_cutoff_created_at": ""}
    }

    resolved, _updated_manifest, metadata = run.collect_mod.resolve_repositories(
        {}, config, manifest
    )

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
