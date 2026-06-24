"""Merge traffic log into the canonical daily reporting surface.

Reads traffic-log.csv (append-only capture log) and materializes
traffic-daily.csv (one row per repo+date, using the latest capture).

Also deduplicates all CSV files and trims them to the configured retention
window. Updates manifest.json timestamps on completion.
"""

import os
from datetime import datetime, timedelta, timezone

from storage import (
    DATA_DIR,
    RETENTION_DAYS,
    DAILY_FIELDS,
    CSV_REGISTRY,
    read_csv,
    write_csv,
    migrate_schema,
    read_manifest,
    write_manifest,
    dedup_log,
    dedup_snapshots,
    dedup_referrers,
    dedup_paths,
    dedup_repo_metrics,
    dedup_collection_status,
    dedup_collection_days,
    dedup_traffic_coverage,
    dedup_repo_commits,
    dedup_repo_releases,
    dedup_repo_release_assets,
    dedup_repo_languages,
    dedup_repo_topics,
    dedup_repo_issue_pr_snapshots,
    dedup_repo_code_frequency_weekly,
    dedup_repo_contributor_activity_weekly,
    dedup_collection_endpoints,
    dedup_repo_event_index,
)
from event_index import event_index_rows
from traffic_reporting import collection_day_rows, traffic_coverage_rows

# Map filenames to their dedup functions
_DEDUP_FNS = {
    "traffic-log.csv":       dedup_log,
    "traffic-snapshots.csv": dedup_snapshots,
    "traffic-referrers.csv": dedup_referrers,
    "traffic-paths.csv":     dedup_paths,
    "repo-metrics.csv":      dedup_repo_metrics,
    "collection-status.csv": dedup_collection_status,
    "collection-days.csv":   dedup_collection_days,
    "traffic-coverage.csv":  dedup_traffic_coverage,
    "repo-commits.csv":      dedup_repo_commits,
    "repo-releases.csv":     dedup_repo_releases,
    "repo-release-assets.csv": dedup_repo_release_assets,
    "repo-languages.csv":    dedup_repo_languages,
    "repo-topics.csv":       dedup_repo_topics,
    "repo-issue-pr-snapshots.csv": dedup_repo_issue_pr_snapshots,
    "repo-code-frequency-weekly.csv": dedup_repo_code_frequency_weekly,
    "repo-contributor-activity-weekly.csv": dedup_repo_contributor_activity_weekly,
    "collection-endpoints.csv": dedup_collection_endpoints,
    "repo-event-index.csv":  dedup_repo_event_index,
}


def ensure_registered_csvs():
    """Create any missing registered CSV files for older restored artifacts."""
    migrate_schema(DATA_DIR)


def dedup_all():
    """Remove duplicate rows from all CSV files that have dedup functions."""
    for filename, dedup_fn in _DEDUP_FNS.items():
        filepath = os.path.join(DATA_DIR, filename)
        rows = read_csv(filepath)
        if not rows:
            continue
        fieldnames = CSV_REGISTRY[filename][0]
        deduped = dedup_fn(rows)
        if len(deduped) < len(rows):
            write_csv(filepath, deduped, fieldnames)
            print(f"  Deduped {filename}: {len(rows)} -> {len(deduped)} rows")


def materialize_daily():
    """Build traffic-daily.csv from traffic-log.csv using latest capture per (repo, ts)."""
    log_path = os.path.join(DATA_DIR, "traffic-log.csv")
    daily_path = os.path.join(DATA_DIR, "traffic-daily.csv")

    rows = read_csv(log_path)
    if not rows:
        # Write an empty daily file with headers if the log is empty
        write_csv(daily_path, [], DAILY_FIELDS)
        return

    # Keep the latest captured_at for each (repo, ts) pair
    best = {}
    for row in rows:
        key = (row["repo"], row["ts"])
        existing = best.get(key)
        if existing is None or row.get("captured_at", "") >= existing.get("captured_at", ""):
            best[key] = row

    daily_rows = sorted(best.values(), key=lambda r: (r["repo"], r["ts"]))
    write_csv(daily_path, daily_rows, DAILY_FIELDS)


def materialize_reporting_coverage():
    """Build daily cadence and traffic reporting coverage surfaces."""
    daily_rows = read_csv(os.path.join(DATA_DIR, "traffic-daily.csv"))
    status_rows = read_csv(os.path.join(DATA_DIR, "collection-status.csv"))
    write_csv(
        os.path.join(DATA_DIR, "collection-days.csv"),
        collection_day_rows(status_rows),
        CSV_REGISTRY["collection-days.csv"][0],
    )
    write_csv(
        os.path.join(DATA_DIR, "traffic-coverage.csv"),
        traffic_coverage_rows(daily_rows, status_rows),
        CSV_REGISTRY["traffic-coverage.csv"][0],
    )


def materialize_event_index():
    """Build the normalized repository event spine from retained context tables."""
    commit_rows = read_csv(os.path.join(DATA_DIR, "repo-commits.csv"))
    release_rows = read_csv(os.path.join(DATA_DIR, "repo-releases.csv"))
    write_csv(
        os.path.join(DATA_DIR, "repo-event-index.csv"),
        event_index_rows(commit_rows, release_rows),
        CSV_REGISTRY["repo-event-index.csv"][0],
    )


def trim_csv_by_date(filepath, date_field, cutoff_date):
    """Remove rows older than cutoff_date based on date_field."""
    rows = read_csv(filepath)
    if not rows:
        return

    fieldnames = CSV_REGISTRY[os.path.basename(filepath)][0]
    kept = [r for r in rows if r.get(date_field, "") >= cutoff_date]

    if len(kept) < len(rows):
        write_csv(filepath, kept, fieldnames)
        print(f"  Trimmed {filepath}: {len(rows)} -> {len(kept)} rows")


def trim_all():
    """Trim all CSV files to the retention window."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")

    for filename, (_fields, date_field) in CSV_REGISTRY.items():
        trim_csv_by_date(os.path.join(DATA_DIR, filename), date_field, cutoff)


def main():
    ensure_registered_csvs()
    print("Deduplicating CSV files...")
    dedup_all()
    print("Materializing daily summary...")
    materialize_daily()
    print("Materializing reporting coverage...")
    materialize_reporting_coverage()
    print("Materializing contextual event index...")
    materialize_event_index()
    print("Trimming to retention window...")
    trim_all()

    # Update manifest timestamp
    manifest = read_manifest(DATA_DIR)
    write_manifest(manifest, DATA_DIR)

    print("Merge complete.")


if __name__ == "__main__":
    main()
