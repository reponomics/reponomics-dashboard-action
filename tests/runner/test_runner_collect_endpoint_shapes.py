from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

import pytest

from dashboard_action import run
from collect_modules.context_endpoints import RepositoryStatisticsStatus


def test_collect_views_clones_joins_views_and_clone_only_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = {
        "views": {"views": [{"timestamp": "2026-05-15T00:00:00Z", "count": 10, "uniques": 4}]},
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


def test_collect_release_context_shapes_release_and_asset_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fetch_json(url: str, _headers: run.collect_mod.Headers) -> Any:
        assert url == "https://api.github.com/repos/demo/reponomics/releases?per_page=100"
        return [
            {
                "id": 99,
                "node_id": "R_99",
                "tag_name": "v1.2.3",
                "target_commitish": "main",
                "name": "v1.2.3",
                "draft": False,
                "prerelease": False,
                "immutable": True,
                "created_at": "2026-06-01T08:00:00Z",
                "published_at": "2026-06-01T09:00:00Z",
                "author": {"login": "maintainer"},
                "html_url": "https://github.com/demo/reponomics/releases/tag/v1.2.3",
                "body": "Release notes",
                "assets": [
                    {
                        "id": 10,
                        "name": "tool.tar.gz",
                        "label": "tool",
                        "content_type": "application/gzip",
                        "state": "uploaded",
                        "size": 2048,
                        "download_count": 7,
                        "created_at": "2026-06-01T08:30:00Z",
                        "updated_at": "2026-06-01T08:45:00Z",
                        "browser_download_url": "https://example.test/tool.tar.gz",
                    }
                ],
            }
        ]

    monkeypatch.setattr(run.collect_mod, "fetch_json", fake_fetch_json)

    release_rows, asset_rows = run.collect_mod.collect_release_context(
        "demo/reponomics",
        {},
        "2026-06-02T00:00:00Z",
    )

    assert release_rows == [
        {
            "repo": "demo/reponomics",
            "release_id": 99,
            "node_id": "R_99",
            "tag_name": "v1.2.3",
            "target_commitish": "main",
            "target_sha": "",
            "name": "v1.2.3",
            "draft": False,
            "prerelease": False,
            "immutable": True,
            "created_at": "2026-06-01T08:00:00Z",
            "published_at": "2026-06-01T09:00:00Z",
            "author_login": "maintainer",
            "html_url": "https://github.com/demo/reponomics/releases/tag/v1.2.3",
            "asset_count": 1,
            "asset_download_count": 7,
            "body_hash": hashlib.sha256(b"Release notes").hexdigest(),
            "captured_at": "2026-06-02T00:00:00Z",
            "schema_version": run.storage.SCHEMA_VERSION,
        }
    ]
    assert asset_rows == [
        {
            "repo": "demo/reponomics",
            "release_id": 99,
            "asset_id": 10,
            "name": "tool.tar.gz",
            "label": "tool",
            "content_type": "application/gzip",
            "state": "uploaded",
            "size_bytes": 2048,
            "download_count": 7,
            "created_at": "2026-06-01T08:30:00Z",
            "updated_at": "2026-06-01T08:45:00Z",
            "browser_download_url": "https://example.test/tool.tar.gz",
            "captured_at": "2026-06-02T00:00:00Z",
            "schema_version": run.storage.SCHEMA_VERSION,
        }
    ]


def test_collect_commit_history_shapes_api_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch_json(url: str, _headers: run.collect_mod.Headers) -> Any:
        assert url == "https://api.github.com/repos/demo/reponomics/commits?per_page=100&sha=main"
        return [
            {
                "sha": "def456",
                "parents": [{"sha": "abc123"}],
                "author": {"login": "dev"},
                "committer": {"login": "maintainer"},
                "commit": {
                    "message": "Fix parser edge case (#12)\n\nBody text",
                    "author": {
                        "name": "Dev Example",
                        "email": "DEV@example.com",
                        "date": "2026-06-02T08:00:00Z",
                    },
                    "committer": {"date": "2026-06-02T09:00:00Z"},
                },
            },
            {
                "sha": "abc123",
                "parents": [],
                "author": {"login": "dev"},
                "committer": {"login": "dev"},
                "commit": {
                    "message": "Add parser",
                    "author": {
                        "name": "Dev Example",
                        "email": "dev@example.com",
                        "date": "2026-06-01T08:00:00Z",
                    },
                    "committer": {"date": "2026-06-01T09:00:00Z"},
                },
            },
        ]

    monkeypatch.setattr(run.collect_mod, "fetch_json", fake_fetch_json)

    rows = run.collect_mod.collect_commit_history(
        "demo/reponomics",
        {},
        "2026-06-03T00:00:00Z",
        default_branch="main",
    )

    assert rows == [
        {
            "repo": "demo/reponomics",
            "sha": "abc123",
            "parent_sha": "",
            "committed_at": "2026-06-01T09:00:00Z",
            "authored_at": "2026-06-01T08:00:00Z",
            "author_name": "Dev Example",
            "author_email_hash": hashlib.sha256(b"dev@example.com").hexdigest(),
            "author_login": "dev",
            "committer_login": "dev",
            "message_subject": "Add parser",
            "message_body_hash": "",
            "files_changed": "",
            "additions": "",
            "deletions": "",
            "changed_paths_sample": "",
            "classification": "feature",
            "associated_pr_number": "",
            "source": "github-commits-api",
            "captured_at": "2026-06-03T00:00:00Z",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
        {
            "repo": "demo/reponomics",
            "sha": "def456",
            "parent_sha": "abc123",
            "committed_at": "2026-06-02T09:00:00Z",
            "authored_at": "2026-06-02T08:00:00Z",
            "author_name": "Dev Example",
            "author_email_hash": hashlib.sha256(b"dev@example.com").hexdigest(),
            "author_login": "dev",
            "committer_login": "maintainer",
            "message_subject": "Fix parser edge case (#12)",
            "message_body_hash": hashlib.sha256(b"Body text").hexdigest(),
            "files_changed": "",
            "additions": "",
            "deletions": "",
            "changed_paths_sample": "",
            "classification": "fix",
            "associated_pr_number": "12",
            "source": "github-commits-api",
            "captured_at": "2026-06-03T00:00:00Z",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
    ]


def test_collect_commit_history_classifies_conventional_api_subjects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fetch_json(url: str, _headers: run.collect_mod.Headers) -> Any:
        assert url == "https://api.github.com/repos/demo/reponomics/commits?per_page=100"
        return [
            {"sha": "test123", "commit": {"message": "test(parser): cover edge case"}},
            {"sha": "ci123", "commit": {"message": "ci: pin workflow action"}},
            {"sha": "docs123", "commit": {"message": "docs(readme): clarify setup"}},
        ]

    monkeypatch.setattr(run.collect_mod, "fetch_json", fake_fetch_json)

    rows = run.collect_mod.collect_commit_history(
        "demo/reponomics",
        {},
        "2026-06-03T00:00:00Z",
    )

    assert {row["message_subject"]: row["classification"] for row in rows} == {
        "docs(readme): clarify setup": "docs",
        "ci: pin workflow action": "ci",
        "test(parser): cover edge case": "tests",
    }


def test_collect_context_shapes_languages_topics_and_issue_pr_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fetch_json(url: str, _headers: run.collect_mod.Headers) -> Any:
        if url.endswith("/languages"):
            return {"Python": 75, "Shell": 25}
        if url.endswith("/topics?per_page=100"):
            return {"names": ["analytics", "dashboard"]}
        if url.endswith("/issues?state=open&per_page=100"):
            return [
                {
                    "number": 1,
                    "title": "bug",
                    "labels": [
                        {"name": "bug", "color": "d73a4a"},
                        {"name": "enhancement", "color": "a2eeef"},
                    ],
                },
                {
                    "number": 2,
                    "pull_request": {},
                    "labels": [{"name": "dependencies", "color": "0366d6"}],
                },
            ]
        if url.endswith("/pulls?state=open&per_page=100"):
            return [{"number": 2}, {"number": 3}]
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(run.collect_mod, "fetch_json", fake_fetch_json)

    assert run.collect_mod.collect_languages(
        "demo/reponomics",
        {},
        "2026-06-02T00:00:00Z",
    ) == [
        {
            "repo": "demo/reponomics",
            "captured_at": "2026-06-02T00:00:00Z",
            "language": "Python",
            "bytes": 75,
            "share": "0.750000",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
        {
            "repo": "demo/reponomics",
            "captured_at": "2026-06-02T00:00:00Z",
            "language": "Shell",
            "bytes": 25,
            "share": "0.250000",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
    ]
    assert run.collect_mod.collect_topics(
        "demo/reponomics",
        {},
        "2026-06-02T00:00:00Z",
    ) == [
        {
            "repo": "demo/reponomics",
            "captured_at": "2026-06-02T00:00:00Z",
            "topic": "analytics",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
        {
            "repo": "demo/reponomics",
            "captured_at": "2026-06-02T00:00:00Z",
            "topic": "dashboard",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
    ]
    assert run.collect_mod.collect_issue_pr_snapshot(
        "demo/reponomics",
        {},
        "2026-06-02T00:00:00Z",
    ) == [
        {
            "repo": "demo/reponomics",
            "ts": "2026-06-02",
            "captured_at": "2026-06-02T00:00:00Z",
            "open_issues_count": 1,
            "open_prs_count": 2,
            "closed_issues_recent": "",
            "merged_prs_recent": "",
            "stale_open_issues_count": "",
            "stale_open_prs_count": "",
            "unanswered_issue_count": "",
            "issue_sample_count": 2,
            "pr_sample_count": 2,
            "source": "api-sample",
            "schema_version": run.storage.SCHEMA_VERSION,
        }
    ]
    assert run.collect_mod.collect_issue_label_snapshots(
        "demo/reponomics",
        {},
        "2026-06-02T00:00:00Z",
    ) == [
        {
            "repo": "demo/reponomics",
            "ts": "2026-06-02",
            "captured_at": "2026-06-02T00:00:00Z",
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
        },
        {
            "repo": "demo/reponomics",
            "ts": "2026-06-02",
            "captured_at": "2026-06-02T00:00:00Z",
            "item_type": "issue",
            "state": "open",
            "label_name": "enhancement",
            "label_key": "enhancement",
            "label_bucket": "enhancement",
            "labeled_item_count": 1,
            "sample_item_count": 1,
            "sample_scope": "issues-api-open-first-page",
            "source": "api-sample",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
        {
            "repo": "demo/reponomics",
            "ts": "2026-06-02",
            "captured_at": "2026-06-02T00:00:00Z",
            "item_type": "pr",
            "state": "open",
            "label_name": "dependencies",
            "label_key": "dependencies",
            "label_bucket": "",
            "labeled_item_count": 1,
            "sample_item_count": 1,
            "sample_scope": "issues-api-open-first-page",
            "source": "api-sample",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
    ]


def test_collect_statistics_shapes_weekly_graph_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    week_epoch = int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp())

    def fake_fetch_json_with_status(
        url: str,
        _headers: run.collect_mod.Headers,
        *,
        accepted_statuses: set[int] | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        assert accepted_statuses
        if url.endswith("/stats/code_frequency"):
            return (
                200,
                [
                    [week_epoch, 10, -4],
                    ["not-a-week"],
                    [week_epoch + 604800, 0, 0],
                ],
                {},
            )
        if url.endswith("/stats/contributors"):
            return (
                200,
                [
                    {
                        "author": {"id": 1, "login": "dev"},
                        "weeks": [
                            {"w": week_epoch, "a": 10, "d": 4, "c": 2},
                            {"w": week_epoch + 604800, "a": 0, "d": 0, "c": 0},
                        ],
                    }
                ],
                {},
            )
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(run.collect_mod, "fetch_json_with_status", fake_fetch_json_with_status)

    assert run.collect_mod.collect_code_frequency_weekly(
        "demo/reponomics",
        {},
        "2026-06-03T00:00:00Z",
    ) == [
        {
            "repo": "demo/reponomics",
            "week_start": "2026-06-01",
            "additions": 10,
            "deletions": 4,
            "captured_at": "2026-06-03T00:00:00Z",
            "source_status": "api",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
        {
            "repo": "demo/reponomics",
            "week_start": "2026-06-08",
            "additions": 0,
            "deletions": 0,
            "captured_at": "2026-06-03T00:00:00Z",
            "source_status": "api",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
    ]
    assert run.collect_mod.collect_contributor_activity_weekly(
        "demo/reponomics",
        {},
        "2026-06-03T00:00:00Z",
    ) == [
        {
            "repo": "demo/reponomics",
            "author_id": 1,
            "author_login": "dev",
            "week_start": "2026-06-01",
            "commits": 2,
            "additions": 10,
            "deletions": 4,
            "captured_at": "2026-06-03T00:00:00Z",
            "source_status": "api",
            "schema_version": run.storage.SCHEMA_VERSION,
        }
    ]


def test_collect_statistics_reports_pending_github_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fetch_json_with_status(
        url: str,
        _headers: run.collect_mod.Headers,
        *,
        accepted_statuses: set[int] | None = None,
    ) -> tuple[int, None, dict[str, str]]:
        assert url == "https://api.github.com/repos/demo/reponomics/stats/code_frequency"
        assert accepted_statuses == {202, 204, 422}
        return 202, None, {}

    monkeypatch.setattr(run.collect_mod, "fetch_json_with_status", fake_fetch_json_with_status)

    with pytest.raises(RepositoryStatisticsStatus) as exc_info:
        run.collect_mod.collect_code_frequency_weekly(
            "demo/reponomics",
            {},
            "2026-06-03T00:00:00Z",
        )

    assert exc_info.value.status == "pending"
    assert exc_info.value.http_status == 202
    assert exc_info.value.cache_state == "pending"
