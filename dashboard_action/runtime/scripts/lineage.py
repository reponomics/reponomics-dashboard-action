"""Lineage metadata and preservation checks for dashboard-data artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import storage

LINEAGE_SCHEMA_VERSION = "1"
ARTIFACT_KIND = "dashboard-data"

ROW_IDENTITY_FIELDS = {
    "traffic-log.csv": ("repo", "ts", "captured_at"),
    "traffic-daily.csv": ("repo", "ts"),
    "traffic-snapshots.csv": ("repo", "ts", "captured_at"),
    "traffic-referrers.csv": ("repo", "captured_at", "referrer"),
    "traffic-paths.csv": ("repo", "captured_at", "path"),
    "repo-metrics.csv": ("repo", "captured_at"),
    "collection-status.csv": ("repo", "captured_at", "status"),
    "collection-days.csv": ("ts",),
    "traffic-coverage.csv": ("repo", "ts"),
    "repo-commits.csv": ("repo", "sha"),
    "repo-releases.csv": ("repo", "release_id"),
    "repo-release-assets.csv": ("repo", "asset_id", "captured_at"),
    "repo-languages.csv": ("repo", "captured_at", "language"),
    "repo-topics.csv": ("repo", "captured_at", "topic"),
    "repo-issue-pr-snapshots.csv": ("repo", "captured_at"),
    "repo-issue-label-snapshots.csv": (
        "repo",
        "captured_at",
        "item_type",
        "state",
        "label_name",
    ),
    "repo-code-frequency-weekly.csv": ("repo", "week_start"),
    "repo-contributor-activity-weekly.csv": ("repo", "author_id", "week_start"),
    "collection-endpoints.csv": ("repo", "captured_at", "endpoint_key"),
    "repo-event-index.csv": ("repo", "event_id"),
}


class LineageError(ValueError):
    """Raised when a child artifact would not preserve retained parent rows."""


@dataclass(frozen=True)
class FileSummary:
    sha256: str
    rows: int
    date_min: str
    date_max: str


@dataclass(frozen=True)
class PayloadSnapshot:
    manifest_digest: str
    payload_digest: str
    semantic_root_digest: str
    files: dict[str, FileSummary]
    row_identities: dict[str, set[str]]
    row_dates: dict[str, dict[str, str]]
    lineage: dict[str, Any]


def snapshot_payload(data_dir: str | Path) -> PayloadSnapshot:
    root = Path(data_dir)
    files: dict[str, FileSummary] = {}
    row_identities: dict[str, set[str]] = {
        filename: set() for filename in storage.CSV_REGISTRY
    }
    row_dates: dict[str, dict[str, str]] = {
        filename: {} for filename in storage.CSV_REGISTRY
    }
    manifest = storage.read_manifest(root.as_posix())

    for filename in _snapshot_filenames(root, manifest):
        identity_filename = _identity_filename(filename)
        date_field = storage.CSV_REGISTRY.get(identity_filename, ((), ""))[1]
        path = root / filename
        rows = _read_rows(path)
        dates = sorted(
            _row_value(identity_filename, row, date_field)
            for row in rows
            if date_field and _row_value(identity_filename, row, date_field)
        )
        files[filename] = FileSummary(
            sha256=_sha256(path),
            rows=len(rows),
            date_min=dates[0] if dates else "",
            date_max=dates[-1] if dates else "",
        )
        identity_dates = _identity_dates(identity_filename, rows, date_field)
        if identity_dates and identity_filename in storage.CSV_REGISTRY:
            row_identities[identity_filename].update(identity_dates)
            row_dates[identity_filename].update(identity_dates)

    return PayloadSnapshot(
        manifest_digest=_sha256(root / "manifest.json"),
        payload_digest=_hash_json(
            {filename: summary.sha256 for filename, summary in files.items()}
        ),
        semantic_root_digest=_hash_json(
            {
                filename: sorted(identities)
                for filename, identities in row_identities.items()
            }
        ),
        files=files,
        row_identities=row_identities,
        row_dates=row_dates,
        lineage=dict(manifest.get("lineage") or {}),
    )


def _snapshot_filenames(root: Path, manifest: dict[str, Any]) -> list[str]:
    filenames = list(storage.CSV_REGISTRY.keys())
    recorded_files = (manifest.get("lineage") or {}).get("files")
    if isinstance(recorded_files, dict):
        filenames.extend(
            filename
            for filename in recorded_files
            if isinstance(filename, str)
        )
    filenames.extend(
        legacy_filename
        for legacy_filename in storage.LEGACY_FILE_RENAMES
        if (root / legacy_filename).is_file()
    )
    return list(dict.fromkeys(filenames))


def _identity_filename(filename: str) -> str:
    return storage.LEGACY_FILE_RENAMES.get(filename, filename)


def _identity_dates(
    filename: str,
    rows: list[dict[str, str]],
    date_field: str,
) -> dict[str, str]:
    if filename not in ROW_IDENTITY_FIELDS:
        return {}
    return {_row_identity(filename, row): _row_value(filename, row, date_field) for row in rows}


def write_verified_lineage(
    data_dir: str | Path,
    *,
    parent: PayloadSnapshot,
    retention_days: int,
    action_version: str,
    operation: str,
) -> PayloadSnapshot:
    root = Path(data_dir)
    cutoff = retention_cutoff(retention_days)
    child = snapshot_payload(root)
    _verify_parent_rows_preserved(parent, child, cutoff)

    manifest = storage.read_manifest(root.as_posix())
    manifest["lineage"] = {
        "lineage_schema_version": LINEAGE_SCHEMA_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "operation": operation,
        "action_version": action_version,
        "created_at": _now_iso(),
        "retention_days": retention_days,
        "retention_cutoff": cutoff,
        "payload_digest": child.payload_digest,
        "semantic_root_digest": child.semantic_root_digest,
        "files": _json_file_summaries(child.files),
        "parent": {
            "manifest_digest": parent.manifest_digest,
            "payload_digest": parent.payload_digest,
            "semantic_root_digest": parent.semantic_root_digest,
            "lineage_schema_version": str(
                parent.lineage.get("lineage_schema_version") or ""
            ),
        },
        "verification": {
            "type": "retained-row-superset",
            "retained_parent_rows": _retained_parent_row_count(parent, cutoff),
        },
    }
    storage.write_manifest(manifest, root.as_posix())
    return snapshot_payload(root)


def validate_snapshot_lineage(snapshot: PayloadSnapshot) -> None:
    if not snapshot.lineage:
        return

    expected_kind = str(snapshot.lineage.get("artifact_kind") or "")
    if expected_kind and expected_kind != ARTIFACT_KIND:
        raise LineageError(f"Unexpected lineage artifact kind {expected_kind!r}.")

    recorded_files = snapshot.lineage.get("files")
    if isinstance(recorded_files, dict):
        _validate_recorded_file_digests(snapshot, recorded_files)
        return

    _validate_digest(
        label="payload_digest",
        expected=str(snapshot.lineage.get("payload_digest") or ""),
        actual=snapshot.payload_digest,
    )
    _validate_digest(
        label="semantic_root_digest",
        expected=str(snapshot.lineage.get("semantic_root_digest") or ""),
        actual=snapshot.semantic_root_digest,
    )


def retention_cutoff(retention_days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime(
        "%Y-%m-%d"
    )


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_json(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_digest(*, label: str, expected: str, actual: str) -> None:
    if expected and expected != actual:
        raise LineageError(
            f"Restored dashboard-data lineage {label} does not match the current payload."
        )


def _validate_recorded_file_digests(
    snapshot: PayloadSnapshot, recorded_files: dict[str, Any]
) -> None:
    for filename, raw_summary in recorded_files.items():
        if not isinstance(filename, str) or not isinstance(raw_summary, dict):
            continue
        expected = str(raw_summary.get("sha256") or "")
        actual = snapshot.files.get(filename, FileSummary("", 0, "", "")).sha256
        if expected and expected != actual:
            raise LineageError(
                "Restored dashboard-data lineage file digest does not match the current payload "
                + f"for {filename}."
            )


def _row_identity(filename: str, row: dict[str, str]) -> str:
    fields = ROW_IDENTITY_FIELDS[filename]
    values = []
    for field in fields:
        value = _row_value(filename, row, field)
        if field and not _row_field_present(filename, row, field):
            raise LineageError(
                "Retained row identity field "
                + f"{field!r} is missing for {filename}; add a migration alias "
                + "or an explicit row-identity transform."
            )
        values.append(value)
    return _hash_json(values)


def _row_value(filename: str, row: dict[str, str], field: str) -> str:
    if not field:
        return ""
    for candidate in (field, *storage.CSV_FIELD_ALIASES.get(filename, {}).get(field, ())):
        if candidate in row:
            return row.get(candidate, "")
    return ""


def _row_field_present(filename: str, row: dict[str, str], field: str) -> bool:
    if not field:
        return True
    return any(
        candidate in row
        for candidate in (field, *storage.CSV_FIELD_ALIASES.get(filename, {}).get(field, ()))
    )


def _retained_parent_row_count(parent: PayloadSnapshot, cutoff: str) -> int:
    count = 0
    for filename in storage.CSV_REGISTRY:
        count += sum(
            1
            for identity in parent.row_identities[filename]
            if _is_retained(parent.row_dates[filename].get(identity, ""), cutoff)
        )
    return count


def _verify_parent_rows_preserved(
    parent: PayloadSnapshot, child: PayloadSnapshot, cutoff: str
) -> None:
    missing: list[tuple[str, str]] = []
    for filename in storage.CSV_REGISTRY:
        for identity in sorted(parent.row_identities[filename]):
            if not _is_retained(parent.row_dates[filename].get(identity, ""), cutoff):
                continue
            if identity not in child.row_identities[filename]:
                missing.append((filename, identity))

    if not missing:
        return

    examples = ", ".join(
        f"{filename}:{identity[:12]}" for filename, identity in missing[:5]
    )
    raise LineageError(
        "Child dashboard-data payload does not preserve retained parent rows: "
        + f"{len(missing)} missing row identities"
        + (f" ({examples})" if examples else "")
        + "."
    )


def _is_retained(value: str, cutoff: str) -> bool:
    if not value:
        return True
    return value[:10] >= cutoff


def _json_file_summaries(
    files: dict[str, FileSummary],
) -> dict[str, dict[str, str | int]]:
    return {
        filename: {
            "sha256": summary.sha256,
            "rows": summary.rows,
            "date_min": summary.date_min,
            "date_max": summary.date_max,
        }
        for filename, summary in files.items()
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
