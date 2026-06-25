from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from dashboard_action import run

from runner_support import (
    CONTEXTUAL_DATA_FILES,
    _config,
    _copy_fixture,
    _write_csv,
)


def test_schema_migration_upgrades_v2_metrics_manifest_dedup_and_retention(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _copy_fixture("compat_v2", tmp_path)
    data_dir = fixture / "data"

    monkeypatch.setattr(run.storage, "DATA_DIR", data_dir.as_posix())
    monkeypatch.setattr(run.merge, "DATA_DIR", data_dir.as_posix())
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


def test_schema_migration_creates_contextual_data_headers(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "3",
                "files": ["repo-metrics.csv"],
                "created_at": "2026-05-01T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    assert run.storage.migrate_schema(data_dir.as_posix()) is True

    for filename in sorted(CONTEXTUAL_DATA_FILES):
        path = data_dir / filename
        assert path.exists(), filename
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            assert next(reader) == run.storage.CSV_REGISTRY[filename][0]
            assert list(reader) == []

    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == run.storage.SCHEMA_VERSION
    assert set(CONTEXTUAL_DATA_FILES).issubset(manifest["files"])


def test_contextual_data_dedup_helpers_preserve_latest_identity_rows() -> None:
    assert run.storage.dedup_repo_commits(
        [
            {"repo": "demo/app", "sha": "abc", "message_subject": "old"},
            {"repo": "demo/app", "sha": "abc", "message_subject": "new"},
        ]
    ) == [{"repo": "demo/app", "sha": "abc", "message_subject": "new"}]
    assert run.storage.dedup_repo_commit_observations(
        [
            {
                "repo": "demo/app",
                "captured_at": "2026-06-01T00:00:00Z",
                "default_branch": "main",
                "sha": "abc",
                "position_from_head": "1",
            },
            {
                "repo": "demo/app",
                "captured_at": "2026-06-01T00:00:00Z",
                "default_branch": "main",
                "sha": "abc",
                "position_from_head": "0",
            },
        ]
    ) == [
        {
            "repo": "demo/app",
            "captured_at": "2026-06-01T00:00:00Z",
            "default_branch": "main",
            "sha": "abc",
            "position_from_head": "0",
        }
    ]
    assert run.storage.dedup_repo_release_assets(
        [
            {
                "repo": "demo/app",
                "asset_id": "10",
                "captured_at": "2026-06-01T00:00:00Z",
                "download_count": "1",
            },
            {
                "repo": "demo/app",
                "asset_id": "10",
                "captured_at": "2026-06-01T00:00:00Z",
                "download_count": "2",
            },
            {
                "repo": "demo/app",
                "asset_id": "10",
                "captured_at": "2026-06-02T00:00:00Z",
                "download_count": "3",
            },
        ]
    ) == [
        {
            "repo": "demo/app",
            "asset_id": "10",
            "captured_at": "2026-06-01T00:00:00Z",
            "download_count": "2",
        },
        {
            "repo": "demo/app",
            "asset_id": "10",
            "captured_at": "2026-06-02T00:00:00Z",
            "download_count": "3",
        },
    ]
    assert run.storage.dedup_repo_event_index(
        [
            {"repo": "demo/app", "event_id": "commit:abc", "title": "old"},
            {"repo": "demo/app", "event_id": "commit:abc", "title": "new"},
        ]
    ) == [{"repo": "demo/app", "event_id": "commit:abc", "title": "new"}]


def test_release_retention_keeps_recent_drafts_without_published_at(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setattr(run.bootstrap, "DATA_DIR", data_dir.as_posix())
    run.bootstrap.bootstrap()
    recent_created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_csv(
        data_dir / "repo-releases.csv",
        run.storage.REPO_RELEASE_FIELDS,
        [
            {
                "repo": "demo/reponomics",
                "release_id": "99",
                "node_id": "R_99",
                "tag_name": "v1.2.3-draft",
                "target_commitish": "main",
                "target_sha": "",
                "name": "v1.2.3 draft",
                "draft": "True",
                "prerelease": "False",
                "immutable": "",
                "created_at": recent_created_at,
                "published_at": "",
                "author_login": "maintainer",
                "html_url": "https://github.com/demo/reponomics/releases/tag/v1.2.3-draft",
                "asset_count": "0",
                "asset_download_count": "0",
                "body_hash": "",
                "captured_at": recent_created_at,
                "schema_version": run.storage.SCHEMA_VERSION,
            }
        ],
    )

    monkeypatch.setattr(run.merge, "DATA_DIR", data_dir.as_posix())
    run.merge.trim_all()

    with (data_dir / "repo-releases.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["release_id"] == "99"
    assert rows[0]["published_at"] == ""


def test_merge_trim_all_does_not_delete_retained_csv_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setattr(run.bootstrap, "DATA_DIR", data_dir.as_posix())
    run.bootstrap.bootstrap()
    old_committed_at = "2020-01-01T00:00:00Z"
    _write_csv(
        data_dir / "repo-commits.csv",
        run.storage.REPO_COMMIT_FIELDS,
        [
            {
                "repo": "demo/reponomics",
                "sha": "abc123",
                "parent_sha": "",
                "committed_at": old_committed_at,
                "authored_at": old_committed_at,
                "author_name": "Maintainer",
                "author_email_hash": "",
                "author_login": "maintainer",
                "committer_login": "maintainer",
                "message_subject": "Initial observed commit",
                "message_body_hash": "",
                "files_changed": "",
                "additions": "",
                "deletions": "",
                "changed_paths_sample": "",
                "classification": "unknown",
                "associated_pr_number": "",
                "source": "github-commits-api",
                "captured_at": old_committed_at,
                "schema_version": run.storage.SCHEMA_VERSION,
            }
        ],
    )

    monkeypatch.setattr(run.merge, "DATA_DIR", data_dir.as_posix())
    run.merge.trim_all()

    with (data_dir / "repo-commits.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["sha"] == "abc123"


def test_schema_migration_handles_file_field_renames_and_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    _write_csv(
        data_dir / "legacy-growth.csv",
        ["repo", "day", "stars", "schema_version"],
        [
            {
                "repo": "demo/reponomics",
                "day": "2026-05-01",
                "stars": "11",
                "schema_version": "1",
            }
        ],
    )
    (data_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "files": ["legacy-growth.csv"],
                "created_at": "2026-05-01T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        run.storage,
        "CSV_REGISTRY",
        {
            "repo-growth.csv": (
                ["repo", "ts", "stargazers_count", "source", "schema_version"],
                "ts",
            )
        },
    )
    monkeypatch.setattr(
        run.storage,
        "LEGACY_FILE_RENAMES",
        {"legacy-growth.csv": "repo-growth.csv"},
    )
    monkeypatch.setattr(
        run.storage,
        "CSV_FIELD_ALIASES",
        {
            "repo-growth.csv": {
                "ts": ("day",),
                "stargazers_count": ("stars",),
            }
        },
    )
    monkeypatch.setattr(
        run.storage,
        "CSV_FIELD_DEFAULTS",
        {"repo-growth.csv": {"source": "migration-default"}},
    )

    assert run.storage.migrate_schema(data_dir.as_posix()) is True

    with (data_dir / "repo-growth.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {
            "repo": "demo/reponomics",
            "ts": "2026-05-01",
            "stargazers_count": "11",
            "source": "migration-default",
            "schema_version": run.storage.SCHEMA_VERSION,
        }
    ]
    assert run.storage.dedup_repo_issue_label_snapshots(
        [
            {
                "repo": "demo/app",
                "captured_at": "2026-06-01T00:00:00Z",
                "item_type": "issue",
                "state": "open",
                "label_name": "bug",
                "labeled_item_count": "1",
            },
            {
                "repo": "demo/app",
                "captured_at": "2026-06-01T00:00:00Z",
                "item_type": "issue",
                "state": "open",
                "label_name": "bug",
                "labeled_item_count": "2",
                "source": "new",
            },
        ]
    ) == [
        {
            "repo": "demo/app",
            "captured_at": "2026-06-01T00:00:00Z",
            "item_type": "issue",
            "state": "open",
            "label_name": "bug",
            "labeled_item_count": "2",
            "source": "new",
        }
    ]
    assert not (data_dir / "legacy-growth.csv").exists()
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == run.storage.SCHEMA_VERSION
    assert manifest["files"] == ["repo-growth.csv"]


def test_prepare_data_schema_rejects_future_retained_schema(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "manifest.json").write_text(
        json.dumps({"schema_version": int(run.storage.SCHEMA_VERSION) + 1}),
        encoding="utf-8",
    )
    config = _config(tmp_path, data_dir=data_dir)

    with pytest.raises(run.ActionError, match="newer than this runtime supports"):
        run._prepare_data_schema(config)


def test_prepare_data_schema_rejects_retained_data_mode_mismatch(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "manifest.json").write_text(
        json.dumps({"schema_version": run.storage.SCHEMA_VERSION, "data_mode": "encrypted"}),
        encoding="utf-8",
    )
    config = _config(tmp_path, data_dir=data_dir, data_mode="plaintext", dashboard_secret="")

    with pytest.raises(run.ActionError, match="data_mode 'encrypted'"):
        run._prepare_data_schema(config)
