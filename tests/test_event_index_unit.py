from __future__ import annotations

import csv
from pathlib import Path

from dashboard_action import run
from event_index import event_index_rows


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_event_index_rows_normalize_commit_and_release_events() -> None:
    rows = event_index_rows(
        [
            {
                "repo": "demo/app",
                "sha": "abc123",
                "committed_at": "2026-06-02T12:00:00Z",
                "message_subject": "docs: explain setup",
                "additions": "8",
                "deletions": "2",
                "classification": "docs",
                "associated_pr_number": "42",
                "captured_at": "2026-06-03T00:00:00Z",
            }
        ],
        [
            {
                "repo": "demo/app",
                "release_id": "99",
                "tag_name": "v1.2.3",
                "name": "",
                "published_at": "2026-06-01T08:00:00Z",
                "target_sha": "def456",
                "html_url": "https://github.com/demo/app/releases/tag/v1.2.3",
                "asset_count": "2",
                "asset_download_count": "35",
                "captured_at": "2026-06-03T00:00:00Z",
            }
        ],
    )

    assert [row["event_id"] for row in rows] == ["release:99", "commit:abc123"]
    assert rows[0]["event_type"] == "release"
    assert rows[0]["title"] == "v1.2.3"
    assert rows[0]["magnitude"] == 35
    assert rows[0]["classification"] == "release"
    assert rows[1]["event_type"] == "commit"
    assert rows[1]["event_date"] == "2026-06-02"
    assert rows[1]["url"] == "https://github.com/demo/app/commit/abc123"
    assert rows[1]["issue_or_pr_number"] == "42"
    assert rows[1]["magnitude"] == 10
    assert rows[1]["schema_version"] == run.storage.SCHEMA_VERSION


def test_merge_materializes_event_index_from_context_tables(
    monkeypatch, tmp_path: Path
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setattr(run.merge, "DATA_DIR", data_dir.as_posix())
    _write_csv(
        data_dir / "repo-commits.csv",
        run.storage.REPO_COMMIT_FIELDS,
        [
            {
                "repo": "demo/app",
                "sha": "abc123",
                "parent_sha": "",
                "committed_at": "2026-06-02T12:00:00Z",
                "authored_at": "2026-06-02T12:00:00Z",
                "author_name": "Alice",
                "author_email_hash": "hash",
                "author_login": "",
                "committer_login": "",
                "message_subject": "feat: add widget",
                "message_body_hash": "",
                "files_changed": "1",
                "additions": "3",
                "deletions": "1",
                "changed_paths_sample": "src/widget.py",
                "classification": "feature",
                "associated_pr_number": "",
                "source": "git-log",
                "captured_at": "2026-06-03T00:00:00Z",
                "schema_version": run.storage.SCHEMA_VERSION,
            }
        ],
    )
    _write_csv(data_dir / "repo-releases.csv", run.storage.REPO_RELEASE_FIELDS, [])

    run.merge.materialize_event_index()

    rows = _read_csv(data_dir / "repo-event-index.csv")
    assert len(rows) == 1
    assert rows[0]["event_id"] == "commit:abc123"
    assert rows[0]["event_type"] == "commit"
    assert rows[0]["event_date"] == "2026-06-02"
    assert rows[0]["classification"] == "feature"
