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
SCHEMA_VERSION = "4"
SCHEMA_VERSION_INT = int(SCHEMA_VERSION)
DATA_MODE = os.environ.get("DATA_MODE", "")
VALID_DATA_MODES = {"encrypted", "plaintext"}


class SchemaMigrationError(ValueError):
    """Raised when a retained artifact cannot be migrated safely."""


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

REPO_COMMIT_FIELDS = [
    "repo", "sha", "parent_sha", "committed_at", "authored_at",
    "author_name", "author_email_hash", "author_login", "committer_login",
    "message_subject", "message_body_hash", "files_changed", "additions",
    "deletions", "changed_paths_sample", "classification",
    "associated_pr_number", "source", "captured_at", "schema_version",
]

REPO_RELEASE_FIELDS = [
    "repo", "release_id", "node_id", "tag_name", "target_commitish",
    "target_sha", "name", "draft", "prerelease", "immutable", "created_at",
    "published_at", "author_login", "html_url", "asset_count",
    "asset_download_count", "body_hash", "captured_at", "schema_version",
]

REPO_RELEASE_ASSET_FIELDS = [
    "repo", "release_id", "asset_id", "name", "label", "content_type",
    "state", "size_bytes", "download_count", "created_at", "updated_at",
    "browser_download_url", "captured_at", "schema_version",
]

REPO_LANGUAGE_FIELDS = [
    "repo", "captured_at", "language", "bytes", "share", "schema_version",
]

REPO_TOPIC_FIELDS = [
    "repo", "captured_at", "topic", "schema_version",
]

REPO_ISSUE_PR_SNAPSHOT_FIELDS = [
    "repo", "ts", "captured_at", "open_issues_count", "open_prs_count",
    "closed_issues_recent", "merged_prs_recent", "stale_open_issues_count",
    "stale_open_prs_count", "unanswered_issue_count", "issue_sample_count",
    "pr_sample_count", "source", "schema_version",
]

REPO_ISSUE_LABEL_SNAPSHOT_FIELDS = [
    "repo", "ts", "captured_at", "item_type", "state", "label_name",
    "label_key", "label_bucket", "labeled_item_count", "sample_item_count",
    "sample_scope", "source", "schema_version",
]

REPO_CODE_FREQUENCY_WEEKLY_FIELDS = [
    "repo", "week_start", "additions", "deletions", "captured_at",
    "source_status", "schema_version",
]

REPO_CONTRIBUTOR_ACTIVITY_WEEKLY_FIELDS = [
    "repo", "author_id", "author_login", "week_start", "commits",
    "additions", "deletions", "captured_at", "source_status",
    "schema_version",
]

COLLECTION_ENDPOINT_FIELDS = [
    "repo", "captured_at", "endpoint_key", "credential_class", "status",
    "http_status", "rows_written", "cache_state", "rate_limit_remaining",
    "retry_after_seconds", "duration_ms", "error_type", "error_message",
    "schema_version",
]

REPO_EVENT_INDEX_FIELDS = [
    "repo", "event_id", "event_type", "event_ts", "event_date", "title",
    "url", "primary_sha", "release_id", "issue_or_pr_number", "magnitude",
    "classification", "source_table", "captured_at", "schema_version",
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
    "repo-commits.csv":      (REPO_COMMIT_FIELDS, "committed_at"),
    "repo-releases.csv":     (REPO_RELEASE_FIELDS, "created_at"),
    "repo-release-assets.csv": (
        REPO_RELEASE_ASSET_FIELDS,
        "captured_at",
    ),
    "repo-languages.csv":    (REPO_LANGUAGE_FIELDS, "captured_at"),
    "repo-topics.csv":       (REPO_TOPIC_FIELDS, "captured_at"),
    "repo-issue-pr-snapshots.csv": (
        REPO_ISSUE_PR_SNAPSHOT_FIELDS,
        "ts",
    ),
    "repo-issue-label-snapshots.csv": (
        REPO_ISSUE_LABEL_SNAPSHOT_FIELDS,
        "ts",
    ),
    "repo-code-frequency-weekly.csv": (
        REPO_CODE_FREQUENCY_WEEKLY_FIELDS,
        "week_start",
    ),
    "repo-contributor-activity-weekly.csv": (
        REPO_CONTRIBUTOR_ACTIVITY_WEEKLY_FIELDS,
        "week_start",
    ),
    "collection-endpoints.csv": (COLLECTION_ENDPOINT_FIELDS, "captured_at"),
    "repo-event-index.csv":  (REPO_EVENT_INDEX_FIELDS, "event_date"),
}

ARTIFACT_FILES = list(CSV_REGISTRY.keys()) + ["manifest.json"]

# Future compatible migrations should extend these maps instead of adding
# one-off read paths in collection or publication code.
LEGACY_FILE_RENAMES: dict[str, str] = {
    # "old-name.csv": "new-name.csv",
}

CSV_FIELD_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    # "new-name.csv": {"new_field": ("old_field",)},
}

CSV_FIELD_DEFAULTS: dict[str, dict[str, str]] = {
    # "new-name.csv": {"new_field": "safe-default"},
}

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
    """Apply compatible retained artifact migrations in-place.

    The runtime treats this function as the compatibility boundary between any
    restored packet shape and the current canonical CSV registry. Compatible
    migrations may add files, add nullable fields, rename CSV files, rename
    fields, and fill safe defaults. Destructive changes require an explicit
    transformation here and a compatibility fixture before release.
    """
    os.makedirs(data_dir, exist_ok=True)
    changed = False
    manifest_path = os.path.join(data_dir, "manifest.json")
    manifest_exists = os.path.exists(manifest_path)
    manifest = read_manifest(data_dir)
    _validate_migratable_manifest(manifest)

    for filename, (fieldnames, _date_field) in CSV_REGISTRY.items():
        if _migrate_csv_file(data_dir, filename, fieldnames):
            changed = True

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


def validate_artifact_data_mode(data_dir=DATA_DIR, expected_data_mode=""):
    """Fail if retained manifest metadata conflicts with the requested data mode."""
    expected = str(expected_data_mode or "").strip()
    if expected not in VALID_DATA_MODES:
        return
    recorded = str(read_manifest(data_dir).get("data_mode") or "").strip()
    if recorded and recorded != expected:
        raise SchemaMigrationError(
            "retained artifact data_mode "
            + f"{recorded!r} does not match this run's data-mode {expected!r}"
        )


def _validate_migratable_manifest(manifest):
    raw_version = manifest.get("schema_version")
    if raw_version in (None, ""):
        return
    try:
        version = int(str(raw_version))
    except (TypeError, ValueError) as exc:
        raise SchemaMigrationError(
            f"retained artifact manifest has invalid schema_version {raw_version!r}"
        ) from exc
    if version > SCHEMA_VERSION_INT:
        raise SchemaMigrationError(
            "retained artifact schema_version "
            + f"{version} is newer than this runtime supports ({SCHEMA_VERSION})"
        )


def _migrate_csv_file(data_dir, filename, fieldnames):
    """Rewrite a registered CSV into its current canonical shape."""
    current_path = os.path.join(data_dir, filename)
    legacy_paths = [
        os.path.join(data_dir, legacy)
        for legacy, target in LEGACY_FILE_RENAMES.items()
        if target == filename
    ]
    source_paths = [
        path
        for path in [current_path, *legacy_paths]
        if os.path.exists(path)
    ]

    if not source_paths:
        write_csv(current_path, [], fieldnames)
        return True

    original_rows = []
    existing_fields = None
    rows = []
    for path in source_paths:
        fields, source_rows = _read_csv_payload(path)
        if path == current_path:
            existing_fields = fields
            original_rows = source_rows
        rows.extend(source_rows)

    normalized = [
        {
            field: _migrated_value(filename, row, field)
            for field in fieldnames
        }
        for row in rows
    ]
    current_matches = (
        existing_fields == fieldnames
        and len(source_paths) == 1
        and source_paths[0] == current_path
        and original_rows == normalized
    )

    if not current_matches:
        write_csv(current_path, normalized, fieldnames)
        for legacy_path in legacy_paths:
            if legacy_path != current_path:
                try:
                    os.remove(legacy_path)
                except FileNotFoundError:
                    pass
        return True
    return False


def _read_csv_payload(filepath):
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        existing_fields = reader.fieldnames or []
        rows = list(reader)
    return existing_fields, rows


def _migrated_value(filename, row, field):
    """Return the value for a field during additive CSV migration."""
    if field == "schema_version":
        return SCHEMA_VERSION
    for candidate in (field, *CSV_FIELD_ALIASES.get(filename, {}).get(field, ())):
        if candidate in row:
            return row.get(candidate, "")
    if field in CSV_FIELD_DEFAULTS.get(filename, {}):
        return CSV_FIELD_DEFAULTS[filename][field]
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


def dedup_repo_commits(rows):
    """Remove duplicate default-branch commit rows.

    Key: (repo, sha).
    """
    seen = {}
    for row in rows:
        seen[(row["repo"], row["sha"])] = row
    return list(seen.values())


def dedup_repo_releases(rows):
    """Remove duplicate repository release rows.

    Key: (repo, release_id).
    """
    seen = {}
    for row in rows:
        seen[(row["repo"], row["release_id"])] = row
    return list(seen.values())


def dedup_repo_release_assets(rows):
    """Remove duplicate release asset snapshot rows.

    Key: (repo, asset_id, captured_at).
    """
    seen = {}
    for row in rows:
        seen[(row["repo"], row["asset_id"], row["captured_at"])] = row
    return list(seen.values())


def dedup_repo_languages(rows):
    """Remove duplicate repository language snapshot rows.

    Key: (repo, captured_at, language).
    """
    seen = {}
    for row in rows:
        seen[(row["repo"], row["captured_at"], row["language"])] = row
    return list(seen.values())


def dedup_repo_topics(rows):
    """Remove duplicate repository topic snapshot rows.

    Key: (repo, captured_at, topic).
    """
    seen = {}
    for row in rows:
        seen[(row["repo"], row["captured_at"], row["topic"])] = row
    return list(seen.values())


def dedup_repo_issue_pr_snapshots(rows):
    """Remove duplicate issue and pull request snapshot rows.

    Key: (repo, captured_at).
    """
    seen = {}
    for row in rows:
        seen[(row["repo"], row["captured_at"])] = row
    return list(seen.values())


def dedup_repo_issue_label_snapshots(rows):
    """Remove duplicate issue and pull request label snapshot rows.

    Key: (repo, captured_at, item_type, state, label_name).
    """
    seen = {}
    for row in rows:
        seen[
            (
                row["repo"],
                row["captured_at"],
                row["item_type"],
                row["state"],
                row["label_name"],
            )
        ] = row
    return list(seen.values())


def dedup_repo_code_frequency_weekly(rows):
    """Remove duplicate weekly code-frequency rows.

    Key: (repo, week_start).
    """
    seen = {}
    for row in rows:
        seen[(row["repo"], row["week_start"])] = row
    return list(seen.values())


def dedup_repo_contributor_activity_weekly(rows):
    """Remove duplicate weekly contributor activity rows.

    Key: (repo, author_id, week_start).
    """
    seen = {}
    for row in rows:
        seen[(row["repo"], row["author_id"], row["week_start"])] = row
    return list(seen.values())


def dedup_collection_endpoints(rows):
    """Remove duplicate endpoint telemetry rows.

    Key: (repo, captured_at, endpoint_key).
    """
    seen = {}
    for row in rows:
        seen[(row["repo"], row["captured_at"], row["endpoint_key"])] = row
    return list(seen.values())


def dedup_repo_event_index(rows):
    """Remove duplicate normalized repository event rows.

    Key: (repo, event_id).
    """
    seen = {}
    for row in rows:
        seen[(row["repo"], row["event_id"])] = row
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
    if DATA_MODE in VALID_DATA_MODES:
        manifest["data_mode"] = DATA_MODE
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
    manifest = {
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
    if DATA_MODE in VALID_DATA_MODES:
        manifest["data_mode"] = DATA_MODE
    return manifest
