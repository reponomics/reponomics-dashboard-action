"""Generate plaintext and encrypted HTML dashboards from canonical CSV data.

Reads traffic-daily.csv, traffic-referrers.csv, and traffic-paths.csv
via the shared load_data module and produces:

- a published dashboard for docs/ hosting
- a standalone single-file dashboard with Chart.js inlined for offline use

The dashboard renderer supports two access modes:

- public: unencrypted metrics in the generated Pages index artifact
- encrypted: encrypted metrics in the generated Pages index artifact, decrypted client-side

Plaintext data mode uses the public access mode and uploads the generated HTML as
the private `html-dashboard-plaintext` workflow artifact instead of publishing it to
GitHub Pages.
"""

import base64
import gzip
import hashlib
import io
import json
import os
import shutil
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from render_dashboard_support import access as dashboard_access
from render_dashboard_support import html as dashboard_html
from render_dashboard_support import status as dashboard_status
from render_dashboard_support.html import (
    DemoUnlockMetadata,
    build_encrypted_html as _build_encrypted_html,
    build_public_html as _build_public_html,
    copy_published_dashboard_assets as _copy_published_dashboard_assets,
    write_published_json_asset as _write_published_json_asset,
)

import storage
from load_data import (
    load_daily,
    load_referrers,
    load_paths,
    load_repo_metrics,
    load_collection_status,
    load_collection_days,
    load_traffic_coverage,
    load_event_index,
    load_releases,
    load_release_assets,
    load_languages,
    load_topics,
    load_issue_pr_snapshots,
    load_issue_label_snapshots,
    load_code_frequency_weekly,
    load_contributor_activity_weekly,
    aggregate_totals,
    aggregate_by_date,
    aggregate_per_repo,
    top_referrers,
    top_paths,
    actionable_insights,
    actionable_insights_structured,
    collection_quality,
    growth_analytics,
    latest_repo_community_profiles,
    latest_repo_metadata,
    traffic_reporting_summary,
)

PAGE_INDEX_OUTPUT_PATH = "docs/index.html"
STANDALONE_OUTPUT_PATH = "dist/dashboard-standalone.html"
ACTION_ROOT = Path(__file__).resolve().parents[3]
VENDORED_CHART_JS_PATH = ACTION_ROOT / "vendor" / "chart.js" / "chart.umd.min.js"
VENDORED_INTER_FONT_PATH = (
    ACTION_ROOT / "vendor" / "inter" / "inter-latin-wght-normal.woff2"
)
VENDORED_MONO_FONT_PATH = (
    ACTION_ROOT / "vendor" / "jetbrains-mono" / "jetbrains-mono-latin-wght-normal.woff2"
)
PUBLISHED_CHART_JS_PATH = "assets/chart.umd.min.js"

ACCESS_MODE_ENV = dashboard_access.ACCESS_MODE_ENV
ACCESS_MODE_PUBLIC = dashboard_access.ACCESS_MODE_PUBLIC
ACCESS_MODE_ENCRYPTED = dashboard_access.ACCESS_MODE_ENCRYPTED
ACCESS_MODE_LEGACY_SHARED_SECRET = dashboard_access.ACCESS_MODE_LEGACY_SHARED_SECRET
_load_access_mode = dashboard_access.load_access_mode

VERSION_STATUS_ENV = dashboard_status.VERSION_STATUS_ENV
MANAGED_DOCS_LINK_ENV = dashboard_status.MANAGED_DOCS_LINK_ENV
UPDATE_DOCS_STATE_ENV = dashboard_status.UPDATE_DOCS_STATE_ENV
DOCS_ACTION_VERSION_ENV = dashboard_status.DOCS_ACTION_VERSION_ENV
DOCS_UPDATED_AT_ENV = dashboard_status.DOCS_UPDATED_AT_ENV
DOCS_STATE_LABELS = dashboard_status.DOCS_STATE_LABELS
_display_version = dashboard_status.display_version
_format_docs_timestamp = dashboard_status.format_docs_timestamp
_load_version_status = dashboard_status.load_version_status
_render_docs_status_detail = dashboard_status.render_docs_status_detail
_render_update_docs_status = dashboard_status.render_update_docs_status
_render_version_badges = dashboard_status.render_version_badges

DASHBOARD_KEY_ENV = "DASHBOARD_KEY"
LEGACY_PASSPHRASE_ENV = "DASHBOARD_PASSPHRASE"

PBKDF2_ITERATIONS = 600_000
PBKDF2_SALT_BYTES = 16
AES_GCM_IV_BYTES = 12
WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
EXPORT_ASSET_PREFIX = "export-data-"
EXPORT_ASSET_SUFFIX = ".enc"
EXPORT_MANIFEST_VERSION = 1
DASHBOARD_DATA_VERSION = 2
ENCRYPTED_DASHBOARD_DATA_VERSION = DASHBOARD_DATA_VERSION
EXPORT_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
CONTEXT_EVENT_LIMIT = 80
CONTEXT_RELEASE_LIMIT = 30
CONTEXT_WEEK_LIMIT = 26

BASE_STYLES = dashboard_html.BASE_STYLES
APP_RUNTIME_JS = dashboard_html.APP_RUNTIME_JS
SECURE_RUNTIME_JS = dashboard_html.SECURE_RUNTIME_JS

def _load_vendored_chart_js():
    """Load vendored Chart.js and escape closing script tags defensively."""
    with open(VENDORED_CHART_JS_PATH) as f:
        return f.read().replace("</script", "<\\/script")


def _publish_vendored_chart_js(output_path: str) -> str:
    """Copy vendored Chart.js beside the published dashboard."""
    asset_path = Path(output_path).parent / PUBLISHED_CHART_JS_PATH
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(VENDORED_CHART_JS_PATH, asset_path)
    return PUBLISHED_CHART_JS_PATH


def _build_repo_series(daily_rows):
    """Build per-repo daily series for drill-down and comparison modes."""
    by_repo = defaultdict(
        lambda: defaultdict(
            lambda: {
                "views": 0,
                "uniques": 0,
                "clones": 0,
                "clone_uniques": 0,
            }
        )
    )

    for row in daily_rows:
        bucket = by_repo[row["repo"]][row["ts"]]
        bucket["views"] += int(row.get("views_count", 0))
        bucket["uniques"] += int(row.get("views_uniques", 0))
        bucket["clones"] += int(row.get("clones_count", 0))
        bucket["clone_uniques"] += int(row.get("clones_uniques", 0))

    series = {}
    for repo, values_by_date in by_repo.items():
        dates = sorted(values_by_date)
        series[repo] = {
            "dates": dates,
            "views": [values_by_date[date]["views"] for date in dates],
            "uniques": [values_by_date[date]["uniques"] for date in dates],
            "clones": [values_by_date[date]["clones"] for date in dates],
            "clone_uniques": [values_by_date[date]["clone_uniques"] for date in dates],
        }
    return series


def _date_range(start: str, end: str) -> list[str]:
    if not start or not end:
        return []
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    if start_date > end_date:
        return []
    dates = []
    cursor = start_date
    while cursor <= end_date:
        dates.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return dates


def _pad_metric_series(dates, series, end_date: str):
    """Extend chart series through a reporting date with null unreported values."""
    if not dates or not end_date or end_date <= dates[-1]:
        return dates, series
    extra_dates = _date_range(_next_day(dates[-1]), end_date)
    padded_dates = [*dates, *extra_dates]
    padded_series = {}
    for key, values in series.items():
        padded_series[key] = [*values, *([None] * len(extra_dates))]
    return padded_dates, padded_series


def _next_day(ts: str) -> str:
    parsed = datetime.strptime(ts, "%Y-%m-%d").date()
    return (parsed + timedelta(days=1)).isoformat()


def _pad_repo_series(repo_series, end_date: str):
    padded = {}
    for repo, series in repo_series.items():
        dates = series.get("dates", [])
        padded_dates, padded_values = _pad_metric_series(
            dates,
            {
                "views": series.get("views", []),
                "uniques": series.get("uniques", []),
                "clones": series.get("clones", []),
                "clone_uniques": series.get("clone_uniques", []),
            },
            end_date,
        )
        padded[repo] = {"dates": padded_dates, **padded_values}
    return padded


def _build_weekday_summary(daily_rows):
    """Build average views/clones by weekday for a daily row collection."""
    daily_totals = defaultdict(lambda: {"views": 0, "clones": 0})
    weekday_totals = {
        label: {"views": 0, "clones": 0, "samples": 0} for label in WEEKDAY_LABELS
    }

    for row in daily_rows:
        bucket = daily_totals[row["ts"]]
        bucket["views"] += int(row.get("views_count", 0))
        bucket["clones"] += int(row.get("clones_count", 0))

    for ts, totals in daily_totals.items():
        weekday_label = WEEKDAY_LABELS[datetime.strptime(ts, "%Y-%m-%d").weekday()]
        bucket = weekday_totals[weekday_label]
        bucket["views"] += totals["views"]
        bucket["clones"] += totals["clones"]
        bucket["samples"] += 1

    return {
        "labels": WEEKDAY_LABELS,
        "views": [
            (
                round(
                    weekday_totals[label]["views"] / weekday_totals[label]["samples"],
                    1,
                )
                if weekday_totals[label]["samples"]
                else 0
            )
            for label in WEEKDAY_LABELS
        ],
        "clones": [
            (
                round(
                    weekday_totals[label]["clones"] / weekday_totals[label]["samples"],
                    1,
                )
                if weekday_totals[label]["samples"]
                else 0
            )
            for label in WEEKDAY_LABELS
        ],
    }


def _build_repo_weekday_summary(daily_rows):
    """Build per-repo average weekday summaries for focus/compare views."""
    rows_by_repo = defaultdict(list)
    for row in daily_rows:
        rows_by_repo[row["repo"]].append(row)
    return {repo: _build_weekday_summary(rows) for repo, rows in rows_by_repo.items()}


def _latest_snapshot_by_repo(rows):
    """Return latest snapshot rows grouped by repo for rolling snapshot families."""
    latest_by_repo = {}
    for row in rows:
        repo = row["repo"]
        captured_at = row.get("captured_at", "")
        if captured_at > latest_by_repo.get(repo, ""):
            latest_by_repo[repo] = captured_at

    grouped = defaultdict(list)
    for row in rows:
        if row.get("captured_at", "") == latest_by_repo.get(row["repo"], ""):
            grouped[row["repo"]].append(row)
    return dict(grouped)


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _latest_rows_by_repo(
    rows: list[dict[str, Any]], field: str = "captured_at"
) -> dict[str, list[dict[str, Any]]]:
    """Return rows from each repo's latest observed value for a date-like field."""
    latest_by_repo: dict[str, str] = {}
    for row in rows:
        repo = row.get("repo", "")
        value = row.get(field, "")
        if repo and value > latest_by_repo.get(repo, ""):
            latest_by_repo[repo] = value

    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        repo = row.get("repo", "")
        if repo and row.get(field, "") == latest_by_repo.get(repo, ""):
            grouped[repo].append(row)
    return dict(grouped)


def _latest_row_by_repo(
    rows: list[dict[str, Any]], field: str = "captured_at"
) -> dict[str, dict[str, Any]]:
    """Return one latest row per repo using a date-like field."""
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        repo = row.get("repo", "")
        value = row.get(field, "")
        if repo and value >= latest.get(repo, {}).get(field, ""):
            latest[repo] = row
    return latest


def _build_context_payload(
    *,
    event_rows,
    release_rows,
    release_asset_rows,
    language_rows,
    topic_rows,
    issue_rows,
    issue_label_rows,
    code_frequency_rows,
    contributor_rows,
) -> dict[str, Any]:
    """Project richer retained context rows into compact dashboard JSON."""
    return {
        "events": _context_events(event_rows),
        "releases": _context_releases(release_rows),
        "release_assets": _context_release_assets(release_asset_rows),
        "languages": _context_languages(language_rows),
        "topics": _context_topics(topic_rows),
        "issues": _context_issues(issue_rows, issue_label_rows),
        "code_frequency": _context_code_frequency(code_frequency_rows),
        "contributors": _context_contributors(contributor_rows),
    }


def _context_events(rows) -> list[dict[str, Any]]:
    normalized = [
        {
            "repo": row.get("repo", ""),
            "event_id": row.get("event_id", ""),
            "event_type": row.get("event_type", ""),
            "event_date": row.get("event_date", ""),
            "event_ts": row.get("event_ts", ""),
            "title": row.get("title", ""),
            "url": row.get("url", ""),
            "magnitude": _int_value(row.get("magnitude")),
            "classification": row.get("classification", "") or "unknown",
            "source_table": row.get("source_table", ""),
        }
        for row in rows
        if row.get("repo") and row.get("event_date")
    ]
    normalized.sort(
        key=lambda row: (
            row["event_date"],
            row.get("event_ts", ""),
            row.get("magnitude", 0),
        ),
        reverse=True,
    )
    return normalized[:CONTEXT_EVENT_LIMIT]


def _context_releases(rows) -> list[dict[str, Any]]:
    normalized = [
        {
            "repo": row.get("repo", ""),
            "release_id": row.get("release_id", ""),
            "tag_name": row.get("tag_name", ""),
            "name": row.get("name", "") or row.get("tag_name", ""),
            "published_at": row.get("published_at", "") or row.get("created_at", ""),
            "url": row.get("html_url", ""),
            "asset_count": _int_value(row.get("asset_count")),
            "asset_download_count": _int_value(row.get("asset_download_count")),
            "draft": row.get("draft", ""),
            "prerelease": row.get("prerelease", ""),
        }
        for row in rows
        if row.get("repo") and row.get("release_id")
    ]
    normalized.sort(key=lambda row: row.get("published_at", ""), reverse=True)
    return normalized[:CONTEXT_RELEASE_LIMIT]


def _context_release_assets(rows) -> list[dict[str, Any]]:
    normalized = [
        {
            "repo": row.get("repo", ""),
            "release_id": row.get("release_id", ""),
            "name": row.get("name", ""),
            "download_count": _int_value(row.get("download_count")),
            "content_type": row.get("content_type", ""),
            "size_bytes": _int_value(row.get("size_bytes")),
            "updated_at": row.get("updated_at", ""),
        }
        for row in rows
        if row.get("repo") and row.get("asset_id")
    ]
    normalized.sort(
        key=lambda row: (row.get("download_count", 0), row.get("updated_at", "")),
        reverse=True,
    )
    return normalized[:CONTEXT_RELEASE_LIMIT]


def _context_languages(rows) -> dict[str, Any]:
    latest = _latest_rows_by_repo(rows, "captured_at")
    by_repo = {}
    totals: defaultdict[str, int] = defaultdict(int)
    for repo, repo_rows in latest.items():
        sorted_rows = sorted(repo_rows, key=lambda row: _int_value(row.get("bytes")), reverse=True)
        by_repo[repo] = [
            {
                "language": row.get("language", ""),
                "bytes": _int_value(row.get("bytes")),
                "share": _float_value(row.get("share")),
            }
            for row in sorted_rows[:6]
            if row.get("language")
        ]
        for row in repo_rows:
            if row.get("language"):
                totals[row["language"]] += _int_value(row.get("bytes"))

    total_bytes = sum(totals.values())
    top = [
        {
            "language": language,
            "bytes": bytes_count,
            "share": (bytes_count / total_bytes) if total_bytes else 0,
        }
        for language, bytes_count in sorted(
            totals.items(), key=lambda item: item[1], reverse=True
        )[:8]
    ]
    return {"top": top, "by_repo": by_repo}


def _context_topics(rows) -> dict[str, Any]:
    latest = _latest_rows_by_repo(rows, "captured_at")
    by_repo = {}
    counts: defaultdict[str, int] = defaultdict(int)
    for repo, repo_rows in latest.items():
        topics = sorted({row.get("topic", "") for row in repo_rows if row.get("topic")})
        by_repo[repo] = topics[:12]
        for topic in topics:
            counts[topic] += 1
    top = [
        {"topic": topic, "repo_count": count}
        for topic, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:12]
    ]
    return {"top": top, "by_repo": by_repo}


def _context_issues(issue_rows, label_rows) -> dict[str, Any]:
    latest_issues = _latest_row_by_repo(issue_rows, "ts")
    by_repo = {}
    totals = {
        "open_issues": 0,
        "open_prs": 0,
        "stale_open_issues": 0,
        "unanswered_issues": 0,
    }
    for repo, row in latest_issues.items():
        repo_issue = {
            "open_issues": _int_value(row.get("open_issues_count")),
            "open_prs": _int_value(row.get("open_prs_count")),
            "stale_open_issues": _int_value(row.get("stale_open_issues_count")),
            "stale_open_prs": _int_value(row.get("stale_open_prs_count")),
            "unanswered_issues": _int_value(row.get("unanswered_issue_count")),
            "captured_at": row.get("captured_at", ""),
            "ts": row.get("ts", ""),
        }
        by_repo[repo] = repo_issue
        totals["open_issues"] += repo_issue["open_issues"]
        totals["open_prs"] += repo_issue["open_prs"]
        totals["stale_open_issues"] += repo_issue["stale_open_issues"]
        totals["unanswered_issues"] += repo_issue["unanswered_issues"]

    latest_labels = _latest_rows_by_repo(label_rows, "ts")
    bucket_counts: defaultdict[str, int] = defaultdict(int)
    for repo_rows in latest_labels.values():
        for row in repo_rows:
            bucket = row.get("label_bucket", "") or "other"
            bucket_counts[bucket] += _int_value(row.get("labeled_item_count"))
    label_buckets = [
        {"bucket": bucket, "count": count}
        for bucket, count in sorted(
            bucket_counts.items(), key=lambda item: (-item[1], item[0])
        )
        if count
    ][:10]
    return {"totals": totals, "by_repo": by_repo, "label_buckets": label_buckets}


def _context_code_frequency(rows) -> dict[str, Any]:
    by_week: defaultdict[str, dict[str, int]] = defaultdict(
        lambda: {"additions": 0, "deletions": 0}
    )
    for row in rows:
        week = row.get("week_start", "")
        if not week:
            continue
        by_week[week]["additions"] += _int_value(row.get("additions"))
        by_week[week]["deletions"] += _int_value(row.get("deletions"))

    weeks = [
        {
            "week_start": week,
            "additions": values["additions"],
            "deletions": values["deletions"],
            "net": values["additions"] - values["deletions"],
        }
        for week, values in sorted(by_week.items())
    ][-CONTEXT_WEEK_LIMIT:]
    return {
        "weeks": weeks,
        "totals": {
            "additions": sum(row["additions"] for row in weeks),
            "deletions": sum(row["deletions"] for row in weeks),
            "net": sum(row["net"] for row in weeks),
        },
    }


def _context_contributors(rows) -> dict[str, Any]:
    by_week: defaultdict[str, dict[str, Any]] = defaultdict(
        lambda: {"authors": set(), "commits": 0, "additions": 0, "deletions": 0}
    )
    for row in rows:
        week = row.get("week_start", "")
        if not week:
            continue
        author = row.get("author_login") or row.get("author_id") or ""
        if author:
            by_week[week]["authors"].add(author)
        by_week[week]["commits"] += _int_value(row.get("commits"))
        by_week[week]["additions"] += _int_value(row.get("additions"))
        by_week[week]["deletions"] += _int_value(row.get("deletions"))

    weeks = [
        {
            "week_start": week,
            "active_contributors": len(values["authors"]),
            "commits": values["commits"],
            "additions": values["additions"],
            "deletions": values["deletions"],
        }
        for week, values in sorted(by_week.items())
    ][-CONTEXT_WEEK_LIMIT:]
    all_authors = set()
    for values in by_week.values():
        all_authors.update(values["authors"])
    return {
        "weeks": weeks,
        "totals": {
            "active_contributors": len(all_authors),
            "commits": sum(row["commits"] for row in weeks),
        },
    }


def _build_payload(
    now,
    totals,
    dates,
    series,
    per_repo,
    referrers,
    paths,
    repo_series,
    weekday,
    repo_weekday,
    repo_referrers,
    repo_paths,
    growth,
    insights,
    insights_structured,
    data_quality,
    traffic_reporting,
    community_profiles,
    repo_metadata,
    context_payload,
):
    """Build the full JSON-safe dashboard data before summary/chunk splitting."""
    repos = []
    for row in per_repo:
        series_row = repo_series.get(row["repo"], {})
        community = community_profiles.get(row["repo"], {})
        metadata = repo_metadata.get(row["repo"], {})
        repos.append(
            {
                "name": row["repo"],
                "views": row["total_views"],
                "uniques": row["total_uniques"],
                "clones": row["total_clones"],
                "clone_uniques": row["total_clone_uniques"],
                "days": len(series_row.get("dates", [])),
                "created_at": metadata.get("created_at", ""),
                "pushed_at": metadata.get("pushed_at", ""),
                "updated_at": metadata.get("updated_at", ""),
                "community": {
                    "available": bool(community.get("available", False)),
                    "health_percentage": community.get("health_percentage"),
                    "documentation": community.get("documentation", ""),
                    "updated_at": community.get("updated_at", ""),
                    "content_reports_enabled": community.get("content_reports_enabled"),
                    "has_code_of_conduct": community.get("has_code_of_conduct"),
                    "has_contributing": community.get("has_contributing"),
                    "has_issue_template": community.get("has_issue_template"),
                    "has_pull_request_template": community.get(
                        "has_pull_request_template"
                    ),
                    "has_readme": community.get("has_readme"),
                    "has_license": community.get("has_license"),
                },
            }
        )

    return {
        "meta": {
            "recent_window_days": 14,
            "window_presets": [7, 14, 30, 90, "all"],
            "default_window": "14",
            "default_range": "recent",
            "default_min_activity": 1,
        },
        "generated_at": now,
        "totals": {
            "repo_count": len(totals["repos"]),
            "days_tracked": totals["days_tracked"],
            "total_views": totals["total_views"],
            "total_uniques": totals["total_uniques"],
            "total_clones": totals["total_clones"],
            "total_clone_uniques": totals["total_clone_uniques"],
        },
        "daily": {
            "dates": dates,
            "views": series["views"],
            "uniques": series["uniques"],
            "clones": series["clones"],
            "clone_uniques": series["clone_uniques"],
        },
        "weekday": weekday,
        "repos": repos,
        "repo_series": repo_series,
        "repo_weekday": repo_weekday,
        "referrers": referrers,
        "paths": paths,
        "repo_referrers": repo_referrers,
        "repo_paths": repo_paths,
        "growth": {
            "window_days": growth["window_days"],
            "cutoff": growth["cutoff"],
            "latest_date": growth["latest_date"],
            "totals": growth["totals"],
            "series": growth["series"],
            "per_repo": growth["per_repo"],
        },
        "insights": insights,
        "insights_v2": insights_structured,
        "data_quality": data_quality,
        "traffic_reporting": traffic_reporting,
        "context": context_payload,
    }


def _kdf_descriptor() -> dict[str, object]:
    return {
        "name": "PBKDF2",
        "hash": "SHA-256",
        "iterations": PBKDF2_ITERATIONS,
    }


def _derive_key(dashboard_key: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(dashboard_key.encode("utf-8"))


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _gzip_json(value: object) -> bytes:
    plaintext = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return gzip.compress(plaintext, compresslevel=9, mtime=0)


def _json_string(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _encrypt_bytes(plaintext: bytes, dashboard_key: str) -> tuple[bytes, bytes, bytes]:
    salt = os.urandom(PBKDF2_SALT_BYTES)
    iv = os.urandom(AES_GCM_IV_BYTES)
    key = _derive_key(dashboard_key, salt)
    ciphertext = AESGCM(key).encrypt(iv, plaintext, None)
    return salt, iv, ciphertext


def _encrypt_dashboard_blob(key: bytes, plaintext: bytes) -> str:
    iv = os.urandom(AES_GCM_IV_BYTES)
    ciphertext = AESGCM(key).encrypt(iv, plaintext, None)
    return f"{_b64url_encode(iv)}.{_b64url_encode(ciphertext)}"


DashboardData = dict[str, Any]


def _build_repo_chunk_payload(payload: DashboardData, repo_name: str) -> DashboardData:
    growth = payload.get("growth", {})
    repo_growth = {
        **growth.get("per_repo", {}).get(repo_name, {}),
        "series": growth.get("series", {}).get(repo_name, {}),
    }
    return {
        "repo": repo_name,
        "repo_series": payload.get("repo_series", {}).get(repo_name, {}),
        "repo_weekday": payload.get("repo_weekday", {}).get(repo_name, {}),
        "repo_referrers": payload.get("repo_referrers", {}).get(repo_name, []),
        "repo_paths": payload.get("repo_paths", {}).get(repo_name, []),
        "growth": {
            "per_repo": repo_growth,
        },
    }


def _split_dashboard_payload(
    payload: DashboardData,
) -> tuple[DashboardData, dict[str, DashboardData]]:
    repo_chunk_ids: dict[str, str] = {}
    chunks: dict[str, DashboardData] = {}

    for idx, repo in enumerate(payload.get("repos", []), start=1):
        repo_name = repo["name"]
        chunk_id = f"c{idx:04d}"
        repo_chunk_ids[repo_name] = chunk_id
        chunks[chunk_id] = _build_repo_chunk_payload(payload, repo_name)

    summary = {
        **{
            key_name: value
            for key_name, value in payload.items()
            if key_name
            not in {
                "repo_series",
                "repo_weekday",
                "repo_referrers",
                "repo_paths",
            }
        },
        "growth": {
            key_name: value
            for key_name, value in payload.get("growth", {}).items()
            if key_name not in {"per_repo", "series"}
        },
        "repo_chunks": repo_chunk_ids,
    }
    return summary, chunks


def _build_export_bundle(data_dir: str) -> bytes:
    files = [*storage.CSV_REGISTRY.keys(), "manifest.json"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for filename in files:
            data = (Path(data_dir) / filename).read_bytes()
            info = zipfile.ZipInfo(filename=filename, date_time=EXPORT_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return buffer.getvalue()


def _build_encrypted_export_manifest(
    output_path: str, dashboard_key: str
) -> dict[str, object]:
    plaintext_bundle = _build_export_bundle(storage.DATA_DIR)
    plaintext_sha256 = hashlib.sha256(plaintext_bundle).hexdigest()
    salt, iv, ciphertext = _encrypt_bytes(plaintext_bundle, dashboard_key)
    ciphertext_sha256 = hashlib.sha256(ciphertext).hexdigest()
    asset_name = f"{EXPORT_ASSET_PREFIX}{ciphertext_sha256[:16]}{EXPORT_ASSET_SUFFIX}"
    asset_relative_path = f"assets/{asset_name}"
    asset_path = Path(output_path).parent / asset_relative_path
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(ciphertext)
    return {
        "version": EXPORT_MANIFEST_VERSION,
        "cipher": "AES-GCM",
        "kdf": _kdf_descriptor(),
        "salt": base64.b64encode(salt).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "ciphertext_sha256": ciphertext_sha256,
        "plaintext_sha256": plaintext_sha256,
        "ciphertext_size": len(ciphertext),
        "asset": asset_relative_path,
        "filename": "reponomics-export",
    }


def _build_plaintext_dashboard_data(payload):
    """Build the v2 plaintext summary plus lazy per-repository chunk object."""
    summary, chunks = _split_dashboard_payload(payload)
    serialized_chunks = {
        chunk_id: _json_string(chunk) for chunk_id, chunk in chunks.items()
    }
    return {
        "version": DASHBOARD_DATA_VERSION,
        "encoding": "json",
        "summary": summary,
        "chunks": serialized_chunks,
        "chunk_count": len(serialized_chunks),
    }


def _build_encrypted_dashboard_data(payload, dashboard_key):
    """Build the v2 encrypted summary plus per-repository chunk object."""
    salt = os.urandom(PBKDF2_SALT_BYTES)
    key = _derive_key(dashboard_key, salt)
    summary, chunks = _split_dashboard_payload(payload)
    encrypted_chunks = {}

    for chunk_id, chunk_payload in chunks.items():
        encrypted_chunks[chunk_id] = _encrypt_dashboard_blob(
            key, _gzip_json(chunk_payload)
        )

    return {
        "version": ENCRYPTED_DASHBOARD_DATA_VERSION,
        "cipher": "AES-GCM",
        "kdf": _kdf_descriptor(),
        "salt": base64.b64encode(salt).decode("ascii"),
        "encoding": "gzip+json",
        "summary": _encrypt_dashboard_blob(key, _gzip_json(summary)),
        "chunks": encrypted_chunks,
        "chunk_count": len(encrypted_chunks),
    }


def render(*, demo_unlock: DemoUnlockMetadata | None = None):
    daily_rows = load_daily()
    referrer_rows = load_referrers()
    path_rows = load_paths()
    metric_rows = load_repo_metrics()
    status_rows = load_collection_status()
    collection_day_rows = load_collection_days()
    coverage_rows = load_traffic_coverage()
    event_rows = load_event_index()
    release_rows = load_releases()
    release_asset_rows = load_release_assets()
    language_rows = load_languages()
    topic_rows = load_topics()
    issue_rows = load_issue_pr_snapshots()
    issue_label_rows = load_issue_label_snapshots()
    code_frequency_rows = load_code_frequency_weekly()
    contributor_rows = load_contributor_activity_weekly()

    access_mode = _load_access_mode()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    totals = aggregate_totals(daily_rows)
    dates, series = aggregate_by_date(daily_rows)
    per_repo = aggregate_per_repo(daily_rows)
    ref_list = top_referrers(referrer_rows)
    path_list = top_paths(path_rows)
    repo_series = _build_repo_series(daily_rows)
    weekday = _build_weekday_summary(daily_rows)
    repo_weekday = _build_repo_weekday_summary(daily_rows)
    repo_referrers = _latest_snapshot_by_repo(referrer_rows)
    repo_paths = _latest_snapshot_by_repo(path_rows)
    growth = growth_analytics(daily_rows, metric_rows)
    community_profiles = latest_repo_community_profiles(metric_rows)
    repo_metadata = latest_repo_metadata(metric_rows)
    traffic_reporting = traffic_reporting_summary(coverage_rows, collection_day_rows)
    reporting_end_date = traffic_reporting.get("latest_collection_date", "")
    dates, series = _pad_metric_series(dates, series, reporting_end_date)
    repo_series = _pad_repo_series(repo_series, reporting_end_date)
    data_quality = collection_quality(status_rows, collection_day_rows)
    context_payload = _build_context_payload(
        event_rows=event_rows,
        release_rows=release_rows,
        release_asset_rows=release_asset_rows,
        language_rows=language_rows,
        topic_rows=topic_rows,
        issue_rows=issue_rows,
        issue_label_rows=issue_label_rows,
        code_frequency_rows=code_frequency_rows,
        contributor_rows=contributor_rows,
    )
    insights = actionable_insights(daily_rows, metric_rows, limit=3, growth=growth)
    insights_structured = actionable_insights_structured(
        daily_rows, metric_rows, limit=3, growth=growth
    )
    payload = _build_payload(
        now,
        totals,
        dates,
        series,
        per_repo,
        ref_list,
        path_list,
        repo_series,
        weekday,
        repo_weekday,
        repo_referrers,
        repo_paths,
        growth,
        insights,
        insights_structured,
        data_quality,
        traffic_reporting,
        community_profiles,
        repo_metadata,
        context_payload,
    )

    if access_mode == ACCESS_MODE_ENCRYPTED:
        dashboard_key = os.environ.get(DASHBOARD_KEY_ENV) or os.environ.get(
            LEGACY_PASSPHRASE_ENV, ""
        )
        if not dashboard_key:
            raise ValueError(
                f"{DASHBOARD_KEY_ENV} must be set when "
                + f"{ACCESS_MODE_ENV}={ACCESS_MODE_ENCRYPTED!r}."
            )
        export_manifest = _build_encrypted_export_manifest(
            PAGE_INDEX_OUTPUT_PATH, dashboard_key
        )
        encrypted_dashboard_data = _build_encrypted_dashboard_data(payload, dashboard_key)
        _copy_published_dashboard_assets(PAGE_INDEX_OUTPUT_PATH, encrypted=True)
        _write_published_json_asset(
            PAGE_INDEX_OUTPUT_PATH,
            dashboard_html.PUBLISHED_ENCRYPTED_DASHBOARD_DATA_ASSET,
            encrypted_dashboard_data,
        )
        _write_published_json_asset(
            PAGE_INDEX_OUTPUT_PATH,
            dashboard_html.PUBLISHED_EXPORT_MANIFEST_ASSET,
            export_manifest,
        )
        published_html = _build_encrypted_html(
            encrypted_dashboard_data,
            f'<script src="{_publish_vendored_chart_js(PAGE_INDEX_OUTPUT_PATH)}"></script>',
            export_manifest,
            demo_unlock=demo_unlock,
            external_assets=True,
        )
    else:
        plaintext_dashboard_data = _build_plaintext_dashboard_data(payload)
        _copy_published_dashboard_assets(PAGE_INDEX_OUTPUT_PATH, encrypted=False)
        _write_published_json_asset(
            PAGE_INDEX_OUTPUT_PATH,
            dashboard_html.PUBLISHED_DASHBOARD_DATA_ASSET,
            plaintext_dashboard_data,
        )
        published_html = _build_public_html(
            plaintext_dashboard_data,
            f'<script src="{_publish_vendored_chart_js(PAGE_INDEX_OUTPUT_PATH)}"></script>',
            external_assets=True,
        )

    os.makedirs(os.path.dirname(PAGE_INDEX_OUTPUT_PATH), exist_ok=True)
    with open(PAGE_INDEX_OUTPUT_PATH, "w") as f:
        f.write(published_html)

    standalone_chart_js = _load_vendored_chart_js()
    standalone_html = _build_public_html(
        _build_plaintext_dashboard_data(payload),
        f"<script>{standalone_chart_js}</script>",
        inline_chart_js=standalone_chart_js,
    )

    os.makedirs(os.path.dirname(STANDALONE_OUTPUT_PATH), exist_ok=True)
    with open(STANDALONE_OUTPUT_PATH, "w") as f:
        f.write(standalone_html)

    print(
        f"Dashboards written to {PAGE_INDEX_OUTPUT_PATH} and {STANDALONE_OUTPUT_PATH} "
        + f"(mode={access_mode}, {len(daily_rows)} daily rows, {len(dates)} dates, "
        + f"{len(ref_list)} referrers, {len(path_list)} paths)"
    )


if __name__ == "__main__":
    render()
