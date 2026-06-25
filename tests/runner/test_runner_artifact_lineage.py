from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dashboard_action import run

from runner_support import (
    _config,
    _seed_log,
    _write_csv,
)


def test_collect_fixture_updates_artifact_without_rendering_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path)
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_collect(config, restore_artifact=False, execute_collect=False)

    assert (tmp_path / ".dashboard-data-artifact" / "dashboard-data.enc").exists()
    manifest = run.storage.read_manifest(config.data_dir.as_posix())
    lineage_payload = manifest["lineage"]
    assert lineage_payload["artifact_kind"] == "dashboard-data"
    assert lineage_payload["operation"] == "collect"
    assert lineage_payload["payload_digest"]
    assert lineage_payload["semantic_root_digest"]
    assert lineage_payload["verification"]["type"] == "retained-row-superset"
    assert not config.readme_path.exists()
    assert not config.pages_index_path.exists()


def test_lineage_rejects_child_missing_retained_parent_row(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path)
    _seed_log(config.data_dir)
    run._patch_runtime_paths(config)
    run._prepare_data_schema(config)
    parent = run.lineage.snapshot_payload(config.data_dir)

    _write_csv(config.data_dir / "traffic-log.csv", run.storage.LOG_FIELDS, [])

    with pytest.raises(run.lineage.LineageError, match="does not preserve retained parent rows"):
        run.lineage.write_verified_lineage(
            config.data_dir,
            parent=parent,
            retention_days=config.retention_days,
            action_version=run.VERSION,
            operation="collect",
        )


def test_lineage_rejects_restored_payload_digest_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path)
    _seed_log(config.data_dir)
    run._patch_runtime_paths(config)
    run._prepare_data_schema(config)
    parent = run.lineage.snapshot_payload(config.data_dir)
    run.lineage.write_verified_lineage(
        config.data_dir,
        parent=parent,
        retention_days=config.retention_days,
        action_version=run.VERSION,
        operation="collect",
    )

    rows = run.storage.read_csv((config.data_dir / "traffic-log.csv").as_posix())
    rows[0]["views_count"] = "99"
    run.storage.write_csv(
        (config.data_dir / "traffic-log.csv").as_posix(), rows, run.storage.LOG_FIELDS
    )
    tampered = run.lineage.snapshot_payload(config.data_dir)

    with pytest.raises(run.lineage.LineageError, match="file digest does not match"):
        run.lineage.validate_snapshot_lineage(tampered)


def test_lineage_accepts_recorded_parent_before_additive_registry_migration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path)
    _seed_log(config.data_dir)
    run._patch_runtime_paths(config)
    run._prepare_data_schema(config)
    parent = run.lineage.snapshot_payload(config.data_dir)
    run.lineage.write_verified_lineage(
        config.data_dir,
        parent=parent,
        retention_days=config.retention_days,
        action_version=run.VERSION,
        operation="collect",
    )

    original_registry = run.storage.CSV_REGISTRY
    monkeypatch.setattr(
        run.storage,
        "CSV_REGISTRY",
        {
            **original_registry,
            "future-compatible.csv": (["repo", "ts", "schema_version"], "ts"),
        },
    )
    restored = run.lineage.snapshot_payload(config.data_dir)

    run.lineage.validate_snapshot_lineage(restored)


def test_lineage_validates_recorded_legacy_file_before_rename(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    legacy_path = data_dir / "legacy-growth.csv"
    _write_csv(
        legacy_path,
        ["repo", "day", "stars", "schema_version"],
        [
            {
                "repo": "demo/reponomics",
                "day": "2099-05-01",
                "stars": "11",
                "schema_version": "1",
            }
        ],
    )
    legacy_digest = hashlib.sha256(legacy_path.read_bytes()).hexdigest()
    (data_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "lineage": {
                    "artifact_kind": "dashboard-data",
                    "files": {
                        "legacy-growth.csv": {
                            "sha256": legacy_digest,
                            "rows": 1,
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        run.storage,
        "CSV_REGISTRY",
        {"repo-growth.csv": (["repo", "ts", "stars", "schema_version"], "ts")},
    )
    monkeypatch.setattr(
        run.storage,
        "LEGACY_FILE_RENAMES",
        {"legacy-growth.csv": "repo-growth.csv"},
    )
    monkeypatch.setattr(
        run.storage,
        "CSV_FIELD_ALIASES",
        {"repo-growth.csv": {"ts": ("day",)}},
    )
    monkeypatch.setattr(
        run.lineage,
        "ROW_IDENTITY_FIELDS",
        {"repo-growth.csv": ("repo", "ts")},
    )

    restored = run.lineage.snapshot_payload(data_dir)

    assert restored.files["legacy-growth.csv"].sha256 == legacy_digest
    run.lineage.validate_snapshot_lineage(restored)


def test_lineage_enforces_row_preservation_across_legacy_file_rename(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setattr(
        run.storage,
        "CSV_REGISTRY",
        {"repo-growth.csv": (["repo", "ts", "stars", "schema_version"], "ts")},
    )
    monkeypatch.setattr(
        run.storage,
        "LEGACY_FILE_RENAMES",
        {"legacy-growth.csv": "repo-growth.csv"},
    )
    monkeypatch.setattr(
        run.storage,
        "CSV_FIELD_ALIASES",
        {"repo-growth.csv": {"ts": ("day",)}},
    )
    monkeypatch.setattr(
        run.lineage,
        "ROW_IDENTITY_FIELDS",
        {"repo-growth.csv": ("repo", "ts")},
    )
    _write_csv(
        data_dir / "legacy-growth.csv",
        ["repo", "day", "stars", "schema_version"],
        [
            {
                "repo": "demo/reponomics",
                "day": "2099-05-01",
                "stars": "11",
                "schema_version": "1",
            }
        ],
    )
    (data_dir / "manifest.json").write_text(
        json.dumps({"schema_version": "1"}),
        encoding="utf-8",
    )
    parent = run.lineage.snapshot_payload(data_dir)

    (data_dir / "legacy-growth.csv").unlink()
    _write_csv(
        data_dir / "repo-growth.csv",
        ["repo", "ts", "stars", "schema_version"],
        [
            {
                "repo": "demo/reponomics",
                "ts": "2099-05-02",
                "stars": "11",
                "schema_version": run.storage.SCHEMA_VERSION,
            }
        ],
    )

    with pytest.raises(run.lineage.LineageError, match="does not preserve retained parent rows"):
        run.lineage.write_verified_lineage(
            data_dir,
            parent=parent,
            retention_days=90,
            action_version=run.VERSION,
            operation="test-migration",
        )
