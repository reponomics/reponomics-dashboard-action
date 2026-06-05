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
    row_identities: dict[str, set[str]] = {}
    row_dates: dict[str, dict[str, str]] = {}

    for filename, (_fields, date_field) in storage.CSV_REGISTRY.items():
        path = root / filename
        rows = _read_rows(path)
        dates = sorted(row.get(date_field, "") for row in rows if row.get(date_field, ""))
        identity_dates = {
            _row_identity(filename, row): row.get(date_field, "")
            for row in rows
        }
        files[filename] = FileSummary(
            sha256=_sha256(path),
            rows=len(rows),
            date_min=dates[0] if dates else "",
            date_max=dates[-1] if dates else "",
        )
        row_identities[filename] = set(identity_dates)
        row_dates[filename] = identity_dates

    manifest = storage.read_manifest(root.as_posix())
    return PayloadSnapshot(
        manifest_digest=_sha256(root / "manifest.json"),
        payload_digest=_hash_json({filename: summary.sha256 for filename, summary in files.items()}),
        semantic_root_digest=_hash_json({filename: sorted(identities) for filename, identities in row_identities.items()}),
        files=files,
        row_identities=row_identities,
        row_dates=row_dates,
        lineage=dict(manifest.get("lineage") or {}),
    )


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
            "lineage_schema_version": str(parent.lineage.get("lineage_schema_version") or ""),
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
    return (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime("%Y-%m-%d")


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
        raise LineageError(f"Restored dashboard-data lineage {label} does not match the current payload.")


def _row_identity(filename: str, row: dict[str, str]) -> str:
    fields = ROW_IDENTITY_FIELDS[filename]
    return _hash_json([row.get(field, "") for field in fields])


def _retained_parent_row_count(parent: PayloadSnapshot, cutoff: str) -> int:
    count = 0
    for filename in storage.CSV_REGISTRY:
        count += sum(
            1
            for identity in parent.row_identities[filename]
            if _is_retained(parent.row_dates[filename].get(identity, ""), cutoff)
        )
    return count


def _verify_parent_rows_preserved(parent: PayloadSnapshot, child: PayloadSnapshot, cutoff: str) -> None:
    missing: list[tuple[str, str]] = []
    for filename in storage.CSV_REGISTRY:
        for identity in sorted(parent.row_identities[filename]):
            if not _is_retained(parent.row_dates[filename].get(identity, ""), cutoff):
                continue
            if identity not in child.row_identities[filename]:
                missing.append((filename, identity))

    if not missing:
        return

    examples = ", ".join(f"{filename}:{identity[:12]}" for filename, identity in missing[:5])
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


def _json_file_summaries(files: dict[str, FileSummary]) -> dict[str, dict[str, str | int]]:
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
