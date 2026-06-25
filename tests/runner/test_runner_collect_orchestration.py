from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from dashboard_action import run
from collect_modules.context_endpoints import RepositoryStatisticsStatus

from runner_support import (
    _config,
    _response,
    _stub_context_collectors,
)


def test_collect_appends_context_rows_for_selected_repo(
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
            "permissions": {"push": True},
            "fork": False,
            "archived": False,
            "disabled": False,
            "private": False,
            "created_at": "2025-01-01T00:00:00Z",
        }
    ]

    def collect_release_context(repo: str, headers, captured_at: str):
        return (
            [
                {
                    "repo": repo,
                    "release_id": 99,
                    "tag_name": "v1.2.3",
                    "target_commitish": "main",
                    "name": "v1.2.3",
                    "created_at": "2026-06-01T08:00:00Z",
                    "published_at": "2026-06-01T09:00:00Z",
                    "html_url": "https://github.com/demo/reponomics/releases/tag/v1.2.3",
                    "asset_count": 1,
                    "asset_download_count": 7,
                    "captured_at": captured_at,
                    "schema_version": run.storage.SCHEMA_VERSION,
                }
            ],
            [
                {
                    "repo": repo,
                    "release_id": 99,
                    "asset_id": 10,
                    "name": "tool.tar.gz",
                    "download_count": 7,
                    "captured_at": captured_at,
                    "schema_version": run.storage.SCHEMA_VERSION,
                }
            ],
        )

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
            "default_branch": "main",
        },
    )
    monkeypatch.setattr(run.collect_mod, "collect_repo_community_profile", lambda *args: {})
    monkeypatch.setattr(run.collect_mod, "collect_views_clones", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_referrers", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_paths", lambda *args: [])
    monkeypatch.setattr(
        run.collect_mod,
        "collect_commit_history",
        lambda repo, headers, captured_at, default_branch: [
            {
                "repo": repo,
                "sha": "abc123",
                "committed_at": "2026-05-31T09:00:00Z",
                "message_subject": f"Add analytics on {default_branch}",
                "classification": "feature",
                "captured_at": captured_at,
                "schema_version": run.storage.SCHEMA_VERSION,
            }
        ],
    )
    monkeypatch.setattr(run.collect_mod, "collect_release_context", collect_release_context)
    monkeypatch.setattr(
        run.collect_mod,
        "collect_languages",
        lambda repo, headers, captured_at: [
            {
                "repo": repo,
                "captured_at": captured_at,
                "language": "Python",
                "bytes": 75,
                "share": "0.750000",
                "schema_version": run.storage.SCHEMA_VERSION,
            }
        ],
    )
    monkeypatch.setattr(
        run.collect_mod,
        "collect_topics",
        lambda repo, headers, captured_at: [
            {
                "repo": repo,
                "captured_at": captured_at,
                "topic": "analytics",
                "schema_version": run.storage.SCHEMA_VERSION,
            }
        ],
    )
    monkeypatch.setattr(
        run.collect_mod,
        "collect_issue_pr_snapshot",
        lambda repo, headers, captured_at: [
            {
                "repo": repo,
                "ts": captured_at[:10],
                "captured_at": captured_at,
                "open_issues_count": 1,
                "open_prs_count": 2,
                "issue_sample_count": 1,
                "pr_sample_count": 2,
                "source": "api-sample",
                "schema_version": run.storage.SCHEMA_VERSION,
            }
        ],
    )
    monkeypatch.setattr(
        run.collect_mod,
        "collect_issue_label_snapshots",
        lambda repo, headers, captured_at: [
            {
                "repo": repo,
                "ts": captured_at[:10],
                "captured_at": captured_at,
                "item_type": "issue",
                "state": "open",
                "label_name": "bug",
                "label_key": "bug",
                "label_bucket": "bug",
                "labeled_item_count": 1,
                "sample_item_count": 1,
                "sample_scope": "issues-api-open-first-page",
                "source": "api-sample",
                "schema_version": run.storage.SCHEMA_VERSION,
            }
        ],
    )
    monkeypatch.setattr(
        run.collect_mod,
        "collect_code_frequency_weekly",
        lambda repo, headers, captured_at: [
            {
                "repo": repo,
                "week_start": "2026-06-01",
                "additions": 10,
                "deletions": 4,
                "captured_at": captured_at,
                "source_status": "api",
                "schema_version": run.storage.SCHEMA_VERSION,
            }
        ],
    )
    monkeypatch.setattr(
        run.collect_mod,
        "collect_contributor_activity_weekly",
        lambda repo, headers, captured_at: [
            {
                "repo": repo,
                "author_id": 1,
                "author_login": "dev",
                "week_start": "2026-06-01",
                "commits": 2,
                "additions": 10,
                "deletions": 4,
                "captured_at": captured_at,
                "source_status": "api",
                "schema_version": run.storage.SCHEMA_VERSION,
            }
        ],
    )

    run.run_collect(config, restore_artifact=False, execute_collect=True)

    def rows(filename: str) -> list[dict[str, str]]:
        with (config.data_dir / filename).open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    assert rows("repo-commits.csv")[-1]["message_subject"] == "Add analytics on main"
    assert rows("repo-commit-observations.csv")[-1]["branch_head_sha"] == "abc123"
    assert rows("repo-releases.csv")[-1]["tag_name"] == "v1.2.3"
    assert rows("repo-release-assets.csv")[-1]["name"] == "tool.tar.gz"
    assert rows("repo-languages.csv")[-1]["language"] == "Python"
    assert rows("repo-topics.csv")[-1]["topic"] == "analytics"
    assert rows("repo-issue-pr-snapshots.csv")[-1]["open_prs_count"] == "2"
    assert rows("repo-issue-label-snapshots.csv")[-1]["label_name"] == "bug"
    assert rows("repo-code-frequency-weekly.csv")[-1]["additions"] == "10"
    assert rows("repo-contributor-activity-weekly.csv")[-1]["author_login"] == "dev"
    endpoint_rows = rows("collection-endpoints.csv")
    endpoint_statuses = {row["endpoint_key"]: row["status"] for row in endpoint_rows}
    assert endpoint_statuses == {
        "commits": "ok",
        "releases": "ok",
        "languages": "ok",
        "topics": "ok",
        "issue-pr-snapshot": "ok",
        "issue-labels": "ok",
        "code-frequency": "ok",
        "contributor-activity": "ok",
    }
    assert endpoint_rows[-2]["cache_state"] == "ready"
    assert endpoint_rows[-1]["cache_state"] == "ready"
    event_rows = rows("repo-event-index.csv")
    event_ids = {row["event_id"] for row in event_rows}
    assert {"commit:abc123", "release:99"}.issubset(event_ids)


def test_collect_context_failure_records_warning_without_failing_collection(
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

    def raise_topics_error(repo: str, headers, captured_at: str):
        raise requests.HTTPError("topics unavailable")

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
    monkeypatch.setattr(run.collect_mod, "collect_views_clones", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_referrers", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_paths", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_commit_history", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_release_context", lambda *args: ([], []))
    monkeypatch.setattr(run.collect_mod, "collect_languages", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_topics", raise_topics_error)
    monkeypatch.setattr(run.collect_mod, "collect_issue_pr_snapshot", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_issue_label_snapshots", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_code_frequency_weekly", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_contributor_activity_weekly", lambda *args: [])

    run.run_collect(config, restore_artifact=False, execute_collect=True)

    with (config.data_dir / "collection-status.csv").open(newline="", encoding="utf-8") as handle:
        status_rows = list(csv.DictReader(handle))
    with (config.data_dir / "collection-endpoints.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        endpoint_rows = list(csv.DictReader(handle))
    summary = summary_path.read_text(encoding="utf-8")
    assert status_rows[-1]["status"] == "ok_zero_data"
    topic_endpoint = next(row for row in endpoint_rows if row["endpoint_key"] == "topics")
    assert topic_endpoint["status"] == "error"
    assert topic_endpoint["error_type"] == "HTTPError"
    assert "topics unavailable" in topic_endpoint["error_message"]
    assert "Repository Context Warnings" in summary
    assert "topics unavailable" in summary


def test_collect_records_pending_statistics_endpoint_without_warning(
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

    def raise_pending(repo: str, headers, captured_at: str):
        raise RepositoryStatisticsStatus(
            endpoint_key="code-frequency",
            http_status=202,
            status="pending",
            cache_state="pending",
            message=f"{repo}: GitHub statistics for code-frequency are still being computed.",
        )

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
    monkeypatch.setattr(run.collect_mod, "collect_views_clones", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_referrers", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_paths", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_commit_history", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_release_context", lambda *args: ([], []))
    monkeypatch.setattr(run.collect_mod, "collect_languages", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_topics", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_issue_pr_snapshot", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_issue_label_snapshots", lambda *args: [])
    monkeypatch.setattr(run.collect_mod, "collect_code_frequency_weekly", raise_pending)
    monkeypatch.setattr(run.collect_mod, "collect_contributor_activity_weekly", lambda *args: [])

    run.run_collect(config, restore_artifact=False, execute_collect=True)

    with (config.data_dir / "collection-status.csv").open(newline="", encoding="utf-8") as handle:
        status_rows = list(csv.DictReader(handle))
    with (config.data_dir / "collection-endpoints.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        endpoint_rows = list(csv.DictReader(handle))
    summary = summary_path.read_text(encoding="utf-8")
    code_frequency = next(row for row in endpoint_rows if row["endpoint_key"] == "code-frequency")
    assert status_rows[-1]["status"] == "ok_zero_data"
    assert code_frequency["status"] == "pending"
    assert code_frequency["http_status"] == "202"
    assert code_frequency["cache_state"] == "pending"
    assert code_frequency["rows_written"] == "0"
    assert "Repository Context Warnings" not in summary


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
    _stub_context_collectors(monkeypatch)

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
    _stub_context_collectors(monkeypatch)

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
    _stub_context_collectors(monkeypatch)

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
