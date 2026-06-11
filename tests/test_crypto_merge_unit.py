from __future__ import annotations

import csv
import io
import json
import tarfile
from pathlib import Path

import pytest

from dashboard_action import run


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _tar_with_member(member_name: str, content: bytes = b"payload") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo(member_name)
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def test_crypto_decrypt_missing_artifact_is_noop(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"

    run.crypto_artifact.decrypt(tmp_path / "missing.enc", data_dir, "MISSING_SECRET")

    assert not data_dir.exists()


def test_crypto_rejects_missing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DASHBOARD_SECRET_DO_NOT_REPLACE", raising=False)

    with pytest.raises(ValueError, match="DASHBOARD_SECRET_DO_NOT_REPLACE must be set"):
        run.crypto_artifact.encrypt(
            Path("data"),
            Path(".dashboard-data-artifact") / "dashboard-data.enc",
            "DASHBOARD_SECRET_DO_NOT_REPLACE",
        )


def test_crypto_rejects_unsupported_payload_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    encrypted = tmp_path / "dashboard-data.enc"
    encrypted.write_text(json.dumps({"version": 999}), encoding="utf-8")
    monkeypatch.setenv("DASHBOARD_SECRET_DO_NOT_REPLACE", "secret-value")

    with pytest.raises(ValueError, match="Unsupported encrypted artifact version"):
        run.crypto_artifact.decrypt(encrypted, tmp_path / "data", "DASHBOARD_SECRET_DO_NOT_REPLACE")


def test_crypto_safe_extract_rejects_path_traversal(tmp_path: Path) -> None:
    archive = _tar_with_member("../escape.txt")

    with pytest.raises(ValueError, match="Refusing unsafe artifact path"):
        run.crypto_artifact._safe_extract(archive, tmp_path / "data")

    assert not (tmp_path / "escape.txt").exists()


def test_merge_materializes_latest_daily_capture(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    log_path = data_dir / "traffic-log.csv"
    daily_path = data_dir / "traffic-daily.csv"
    _write_csv(
        log_path,
        run.storage.LOG_FIELDS,
        [
            {
                "repo": "demo/repo",
                "ts": "2026-05-18",
                "views_count": "10",
                "views_uniques": "4",
                "clones_count": "1",
                "clones_uniques": "1",
                "captured_at": "2026-05-18T10:00:00Z",
                "source": "api",
                "schema_version": run.storage.SCHEMA_VERSION,
            },
            {
                "repo": "demo/repo",
                "ts": "2026-05-18",
                "views_count": "20",
                "views_uniques": "8",
                "clones_count": "2",
                "clones_uniques": "2",
                "captured_at": "2026-05-18T12:00:00Z",
                "source": "api",
                "schema_version": run.storage.SCHEMA_VERSION,
            },
            {
                "repo": "demo/other",
                "ts": "2026-05-17",
                "views_count": "5",
                "views_uniques": "3",
                "clones_count": "0",
                "clones_uniques": "0",
                "captured_at": "2026-05-17T12:00:00Z",
                "source": "api",
                "schema_version": run.storage.SCHEMA_VERSION,
            },
        ],
    )

    original_data_dir = run.merge.DATA_DIR
    try:
        run.merge.DATA_DIR = data_dir.as_posix()
        run.merge.materialize_daily()
    finally:
        run.merge.DATA_DIR = original_data_dir

    assert _read_csv(daily_path) == [
        {
            "repo": "demo/other",
            "ts": "2026-05-17",
            "views_count": "5",
            "views_uniques": "3",
            "clones_count": "0",
            "clones_uniques": "0",
            "captured_at": "2026-05-17T12:00:00Z",
            "source": "api",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
        {
            "repo": "demo/repo",
            "ts": "2026-05-18",
            "views_count": "20",
            "views_uniques": "8",
            "clones_count": "2",
            "clones_uniques": "2",
            "captured_at": "2026-05-18T12:00:00Z",
            "source": "api",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
    ]


def _status_row(repo: str, ts: str, status: str) -> dict[str, str]:
    return {
        "repo": repo,
        "ts": ts,
        "captured_at": f"{ts}T12:00:00Z",
        "run_id": "123",
        "status": status,
        "metric_source": "repo-detail",
        "traffic_days": "14",
        "referrer_rows": "0",
        "path_rows": "0",
        "error_type": "",
        "error_message": "",
        "schema_version": run.storage.SCHEMA_VERSION,
    }


def test_merge_materializes_collection_days_with_no_run_gaps(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_csv(
        data_dir / "collection-status.csv",
        run.storage.COLLECTION_STATUS_FIELDS,
        [
            _status_row("demo/app", "2026-06-09", "ok_with_data"),
            _status_row("demo/app", "2026-06-11", "ok_with_data"),
        ],
    )
    _write_csv(data_dir / "traffic-daily.csv", run.storage.DAILY_FIELDS, [])

    original_data_dir = run.merge.DATA_DIR
    try:
        run.merge.DATA_DIR = data_dir.as_posix()
        run.merge.materialize_reporting_coverage()
    finally:
        run.merge.DATA_DIR = original_data_dir

    assert _read_csv(data_dir / "collection-days.csv") == [
        {
            "ts": "2026-06-09",
            "status": "healthy",
            "latest_captured_at": "2026-06-09T12:00:00Z",
            "run_count": "1",
            "tracked_repos": "1",
            "with_data_repos": "1",
            "zero_traffic_repos": "0",
            "skipped_repos": "0",
            "error_repos": "0",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
        {
            "ts": "2026-06-10",
            "status": "no_run",
            "latest_captured_at": "",
            "run_count": "0",
            "tracked_repos": "0",
            "with_data_repos": "0",
            "zero_traffic_repos": "0",
            "skipped_repos": "0",
            "error_repos": "0",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
        {
            "ts": "2026-06-11",
            "status": "healthy",
            "latest_captured_at": "2026-06-11T12:00:00Z",
            "run_count": "1",
            "tracked_repos": "1",
            "with_data_repos": "1",
            "zero_traffic_repos": "0",
            "skipped_repos": "0",
            "error_repos": "0",
            "schema_version": run.storage.SCHEMA_VERSION,
        },
    ]


def test_merge_materializes_upstream_lag_and_backfill_coverage(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    daily_rows = [
        {
            "repo": "demo/app",
            "ts": "2026-06-08",
            "views_count": "4",
            "views_uniques": "2",
            "clones_count": "1",
            "clones_uniques": "1",
            "captured_at": "2026-06-11T12:00:00Z",
            "source": "api",
            "schema_version": run.storage.SCHEMA_VERSION,
        }
    ]
    _write_csv(data_dir / "traffic-daily.csv", run.storage.DAILY_FIELDS, daily_rows)
    _write_csv(
        data_dir / "collection-status.csv",
        run.storage.COLLECTION_STATUS_FIELDS,
        [_status_row("demo/app", "2026-06-11", "ok_with_data")],
    )

    original_data_dir = run.merge.DATA_DIR
    try:
        run.merge.DATA_DIR = data_dir.as_posix()
        run.merge.materialize_reporting_coverage()
        first_states = {
            (row["repo"], row["ts"]): row["coverage_state"]
            for row in _read_csv(data_dir / "traffic-coverage.csv")
        }
        _write_csv(
            data_dir / "traffic-daily.csv",
            run.storage.DAILY_FIELDS,
            [
                *daily_rows,
                {
                    **daily_rows[0],
                    "ts": "2026-06-09",
                    "views_count": "7",
                    "captured_at": "2026-06-12T12:00:00Z",
                },
            ],
        )
        run.merge.materialize_reporting_coverage()
    finally:
        run.merge.DATA_DIR = original_data_dir

    assert first_states == {
        ("demo/app", "2026-06-08"): "reported",
        ("demo/app", "2026-06-09"): "not_reported_by_api",
        ("demo/app", "2026-06-10"): "not_reported_by_api",
        ("demo/app", "2026-06-11"): "not_reported_by_api",
    }
    second_states = {
        (row["repo"], row["ts"]): row["coverage_state"]
        for row in _read_csv(data_dir / "traffic-coverage.csv")
    }
    assert second_states[("demo/app", "2026-06-09")] == "reported"
    assert second_states[("demo/app", "2026-06-10")] == "not_reported_by_api"
    assert second_states[("demo/app", "2026-06-11")] == "not_reported_by_api"


def test_merge_materializes_skipped_and_failed_traffic_coverage(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_csv(data_dir / "traffic-daily.csv", run.storage.DAILY_FIELDS, [])
    _write_csv(
        data_dir / "collection-status.csv",
        run.storage.COLLECTION_STATUS_FIELDS,
        [
            _status_row("demo/skipped", "2026-06-11", "skipped_unavailable"),
            _status_row("demo/error", "2026-06-11", "error"),
        ],
    )

    original_data_dir = run.merge.DATA_DIR
    try:
        run.merge.DATA_DIR = data_dir.as_posix()
        run.merge.materialize_reporting_coverage()
    finally:
        run.merge.DATA_DIR = original_data_dir

    assert {
        (row["repo"], row["ts"]): row["coverage_state"]
        for row in _read_csv(data_dir / "traffic-coverage.csv")
    } == {
        ("demo/error", "2026-06-11"): "collection_failed",
        ("demo/skipped", "2026-06-11"): "repo_skipped",
    }


def test_merge_trim_csv_by_date_keeps_rows_on_or_after_cutoff(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    log_path = data_dir / "traffic-log.csv"
    _write_csv(
        log_path,
        run.storage.LOG_FIELDS,
        [
            {
                "repo": "demo/old",
                "ts": "2026-05-01",
                "views_count": "1",
                "views_uniques": "1",
                "clones_count": "0",
                "clones_uniques": "0",
                "captured_at": "2026-05-01T00:00:00Z",
                "source": "api",
                "schema_version": run.storage.SCHEMA_VERSION,
            },
            {
                "repo": "demo/new",
                "ts": "2026-05-10",
                "views_count": "2",
                "views_uniques": "2",
                "clones_count": "0",
                "clones_uniques": "0",
                "captured_at": "2026-05-10T00:00:00Z",
                "source": "api",
                "schema_version": run.storage.SCHEMA_VERSION,
            },
        ],
    )

    run.merge.trim_csv_by_date(log_path.as_posix(), "ts", "2026-05-10")

    rows = _read_csv(log_path)
    assert [row["repo"] for row in rows] == ["demo/new"]
