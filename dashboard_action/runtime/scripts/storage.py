"""Shared CSV schemas, I/O helpers, and manifest lifecycle management.

This module is the single source of truth for the canonical artifact payload
structure. All scripts that read or write CSV data files or manifest.json
should use these helpers.
"""

import csv
import json
import os
from datetime import datetime, timezone

DATA_DIR = "data"
SCHEMA_VERSION = "3"


def _int_env(name, default):
    """Read an integer env var with a safe default."""
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


RETENTION_DAYS = _int_env("RETENTION_DAYS", 90)

# ---------------------------------------------------------------------------
# Canonical CSV schemas — column order matters for deterministic output
# ---------------------------------------------------------------------------

LOG_FIELDS = [
    "repo", "ts", "views_count", "views_uniques",
    "clones_count", "clones_uniques", "captured_at", "source",
    "schema_version",
]

DAILY_FIELDS = [
    "repo", "ts", "views_count", "views_uniques",
    "clones_count", "clones_uniques", "captured_at", "source",
    "schema_version",
]

SNAPSHOT_FIELDS = [
    "repo", "ts", "captured_at", "views_count", "views_uniques",
    "clones_count", "clones_uniques", "schema_version",
]

REFERRER_FIELDS = [
    "repo", "captured_at", "referrer", "count", "uniques",
    "schema_version",
]

PATH_FIELDS = [
    "repo", "captured_at", "path", "title", "count", "uniques",
    "schema_version",
]

REPO_METRIC_FIELDS = [
    "repo", "repo_id", "node_id", "ts", "captured_at",
    "stargazers_count", "subscribers_count", "forks_count",
    "open_issues_count", "size_kb", "created_at", "pushed_at",
    "updated_at", "language", "visibility", "default_branch",
    "has_pages", "has_discussions", "archived", "disabled",
    "community_health_percentage", "community_documentation",
    "community_updated_at", "community_content_reports_enabled",
    "community_has_code_of_conduct", "community_has_contributing",
    "community_has_issue_template", "community_has_pull_request_template",
    "community_has_readme", "community_has_license",
    "source", "schema_version",
]

COLLECTION_STATUS_FIELDS = [
    "repo", "ts", "captured_at", "run_id", "status",
    "metric_source", "traffic_days", "referrer_rows", "path_rows",
    "error_type", "error_message", "schema_version",
]

COLLECTION_DAY_FIELDS = [
    "ts", "status", "latest_captured_at", "run_count",
    "tracked_repos", "with_data_repos", "zero_traffic_repos",
    "skipped_repos", "error_repos", "schema_version",
]

TRAFFIC_COVERAGE_FIELDS = [
    "repo", "ts", "coverage_state", "reported_at", "latest_collection_ts",
    "latest_captured_at", "reason", "schema_version",
]

# Map filename -> (field list, date field used for retention trim)
CSV_REGISTRY = {
    "traffic-log.csv":       (LOG_FIELDS,      "ts"),
    "traffic-daily.csv":     (DAILY_FIELDS,     "ts"),
    "traffic-snapshots.csv": (SNAPSHOT_FIELDS,  "ts"),
    "traffic-referrers.csv": (REFERRER_FIELDS,  "captured_at"),
    "traffic-paths.csv":     (PATH_FIELDS,      "captured_at"),
    "repo-metrics.csv":      (REPO_METRIC_FIELDS, "ts"),
    "collection-status.csv": (COLLECTION_STATUS_FIELDS, "ts"),
    "collection-days.csv":   (COLLECTION_DAY_FIELDS, "ts"),
    "traffic-coverage.csv":  (TRAFFIC_COVERAGE_FIELDS, "ts"),
}

ARTIFACT_FILES = list(CSV_REGISTRY.keys()) + ["manifest.json"]

# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------


def read_csv(filepath):
    """Read a CSV file and return a list of dicts. Returns [] if missing."""
    if not os.path.exists(filepath):
        return []
    with open(filepath, newline="") as f:
        return list(csv.DictReader(f))


def write_csv(filepath, rows, fieldnames):
    """Write rows to a CSV file with a header line."""
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def append_csv(filepath, rows, fieldnames):
    """Append rows to an existing CSV file (no header)."""
    if not rows:
        return
    with open(filepath, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        for row in rows:
            writer.writerow(row)


def ensure_csv(filepath, fieldnames):
    """Create a CSV file with only a header row if it does not exist."""
    if not os.path.exists(filepath):
        write_csv(filepath, [], fieldnames)


def migrate_schema(data_dir=DATA_DIR):
    """Apply compatible artifact schema migrations in-place.

    Migrations are intentionally additive. Existing retained rows keep their
    historical values, newly introduced columns are blank unless a safe default
    is known, and manifest metadata is refreshed to the runtime schema.
    """
    os.makedirs(data_dir, exist_ok=True)
    changed = False

    for filename, (fieldnames, _date_field) in CSV_REGISTRY.items():
        filepath = os.path.join(data_dir, filename)
        if not os.path.exists(filepath):
            write_csv(filepath, [], fieldnames)
            changed = True
            continue
        if _migrate_csv_header(filepath, fieldnames):
            changed = True

    manifest_path = os.path.join(data_dir, "manifest.json")
    manifest_exists = os.path.exists(manifest_path)
    manifest = read_manifest(data_dir)
    if not manifest_exists and not manifest.get("created_at"):
        manifest["created_at"] = _now_iso()
        changed = True
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("files") != list(CSV_REGISTRY.keys())
        or manifest.get("retention_days") != RETENTION_DAYS
    ):
        changed = True

    if changed:
        write_manifest(manifest, data_dir)
    return changed


def _migrate_csv_header(filepath, fieldnames):
    """Rewrite a registered CSV when its header differs from the canonical one."""
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        existing_fields = reader.fieldnames or []
        rows = list(reader)

    if existing_fields == fieldnames:
        return False

    normalized = []
    for row in rows:
        normalized.append({
            field: _migrated_value(row, field)
            for field in fieldnames
        })
    write_csv(filepath, normalized, fieldnames)
    return True


def _migrated_value(row, field):
    """Return the value for a field during additive CSV migration."""
    if field == "schema_version":
        return SCHEMA_VERSION
    return row.get(field, "")


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------


def dedup_log(rows):
    """Remove exact duplicate rows from the traffic log.

    Two rows are duplicates if they share the same (repo, ts, captured_at).
    When duplicates exist the last occurrence wins (preserving append order).
    """
    seen = {}
    for row in rows:
        key = (row["repo"], row["ts"], row["captured_at"])
        seen[key] = row
    return list(seen.values())


def dedup_snapshots(rows):
    """Remove exact duplicate snapshot rows.

    Key: (repo, ts, captured_at).
    """
    seen = {}
    for row in rows:
        key = (row["repo"], row["ts"], row["captured_at"])
        seen[key] = row
    return list(seen.values())


def dedup_referrers(rows):
    """Remove exact duplicate referrer rows.

    Key: (repo, captured_at, referrer).
    """
    seen = {}
    for row in rows:
        key = (row["repo"], row["captured_at"], row["referrer"])
        seen[key] = row
    return list(seen.values())


def dedup_paths(rows):
    """Remove exact duplicate path rows.

    Key: (repo, captured_at, path).
    """
    seen = {}
    for row in rows:
        key = (row["repo"], row["captured_at"], row["path"])
        seen[key] = row
    return list(seen.values())


def dedup_repo_metrics(rows):
    """Remove duplicate repository metric snapshots.

    Key: (repo, captured_at).
    """
    seen = {}
    for row in rows:
        key = (row["repo"], row["captured_at"])
        seen[key] = row
    return list(seen.values())


def dedup_collection_status(rows):
    """Remove duplicate per-run collection-status rows.

    Key: (repo, captured_at, status).
    """
    seen = {}
    for row in rows:
        key = (row["repo"], row["captured_at"], row.get("status", ""))
        seen[key] = row
    return list(seen.values())


def dedup_collection_days(rows):
    """Remove duplicate collection-day summaries.

    Key: ts.
    """
    seen = {}
    for row in rows:
        seen[row["ts"]] = row
    return list(seen.values())


def dedup_traffic_coverage(rows):
    """Remove duplicate traffic coverage rows.

    Key: (repo, ts).
    """
    seen = {}
    for row in rows:
        seen[(row["repo"], row["ts"])] = row
    return list(seen.values())


# ---------------------------------------------------------------------------
# Manifest lifecycle
# ---------------------------------------------------------------------------


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_manifest(data_dir=DATA_DIR):
    """Read manifest.json; return a dict (empty-ish default if missing)."""
    path = os.path.join(data_dir, "manifest.json")
    if not os.path.exists(path):
        return _default_manifest()
    with open(path) as f:
        return json.load(f)


def write_manifest(manifest, data_dir=DATA_DIR):
    """Write manifest.json with updated last_updated timestamp."""
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["files"] = list(CSV_REGISTRY.keys())
    manifest["retention_days"] = RETENTION_DAYS
    manifest["last_updated"] = _now_iso()
    path = os.path.join(data_dir, "manifest.json")
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")


def create_manifest(data_dir=DATA_DIR):
    """Create a fresh manifest.json with created_at set to now."""
    manifest = _default_manifest()
    now = _now_iso()
    manifest["created_at"] = now
    manifest["last_updated"] = now
    path = os.path.join(data_dir, "manifest.json")
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    return manifest


def _default_manifest():
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": "",
        "last_updated": "",
        "retention_days": RETENTION_DAYS,
        "files": list(CSV_REGISTRY.keys()),
        "selection_state": {
            "auto_seeded_at": "",
            "auto_cutoff_created_at": "",
        },
    }
