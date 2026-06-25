"""Collection status rows and GitHub Actions step-summary rendering."""

from __future__ import annotations

import os
from typing import Any

from storage import COLLECTION_STATUS_FIELDS, DATA_DIR, SCHEMA_VERSION, append_csv

from collect_modules.types import NetworkWarning


def collection_status_row(
    *,
    repo: str,
    captured_at: str,
    run_id: str,
    status: str,
    metric_source: str,
    traffic_days: int,
    referrer_rows: int,
    path_rows: int,
    error_type: str = "",
    error_message: str = "",
) -> dict[str, Any]:
    """Build a normalized collection-status.csv row."""
    message = error_message.replace("\n", " ").strip()
    if len(message) > 240:
        message = message[:240] + "..."
    return {
        "repo": repo,
        "ts": captured_at[:10],
        "captured_at": captured_at,
        "run_id": run_id,
        "status": status,
        "metric_source": metric_source,
        "traffic_days": traffic_days,
        "referrer_rows": referrer_rows,
        "path_rows": path_rows,
        "error_type": error_type,
        "error_message": message,
        "schema_version": SCHEMA_VERSION,
    }


def append_collection_status(row: dict[str, Any], data_dir: str = DATA_DIR) -> None:
    """Append one collection-status.csv row."""
    append_csv(
        os.path.join(data_dir, "collection-status.csv"),
        [row],
        COLLECTION_STATUS_FIELDS,
    )


def has_nonzero_traffic(rows: list[dict[str, Any]]) -> bool:
    """Return whether any traffic row carries a non-zero traffic counter."""
    for row in rows:
        if (
            int(row.get("views_count", 0) or 0) > 0
            or int(row.get("views_uniques", 0) or 0) > 0
            or int(row.get("clones_count", 0) or 0) > 0
            or int(row.get("clones_uniques", 0) or 0) > 0
        ):
            return True
    return False


def collection_status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count known collection status categories."""
    counts = {
        "ok_with_data": 0,
        "ok_zero_data": 0,
        "skipped_unavailable": 0,
        "error": 0,
        "error_secondary_rate_limit": 0,
    }
    for row in rows:
        status = str(row.get("status", "")).strip()
        if status in counts:
            counts[status] += 1
    return counts


def write_step_summary(
    outcome: str,
    *,
    errors: list[str] | None = None,
    secondary_limit: Any | None = None,
    skipped_repos: list[str] | None = None,
    status_rows: list[dict[str, Any]] | None = None,
    network_warnings: list[NetworkWarning] | None = None,
    repo_detail_warnings: list[str] | None = None,
    repo_community_warnings: list[str] | None = None,
    repo_context_warnings: list[str] | None = None,
) -> None:
    """Write a GitHub Actions step summary when available."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    lines = _base_summary_lines(outcome, errors, skipped_repos, status_rows)
    _append_secondary_limit(lines, secondary_limit)
    _append_network_warnings(lines, network_warnings or [])
    _append_warning_section(lines, "Repository Detail Warnings", repo_detail_warnings or [])
    _append_warning_section(lines, "Community Profile Warnings", repo_community_warnings or [])
    _append_warning_section(lines, "Repository Context Warnings", repo_context_warnings or [])

    with open(summary_path, "a") as f:
        f.write("\n".join(lines) + "\n")


def _base_summary_lines(
    outcome: str,
    errors: list[str] | None,
    skipped_repos: list[str] | None,
    status_rows: list[dict[str, Any]] | None,
) -> list[str]:
    lines = ["## Traffic Collection Summary", "", f"- Outcome: **{outcome}**"]
    if errors:
        lines.append(f"- Repositories with errors: {', '.join(errors)}")
    if skipped_repos:
        lines.append("- Repositories skipped as unavailable: " + ", ".join(skipped_repos))
    if status_rows:
        counts = collection_status_counts(status_rows)
        lines.extend(
            [
                f"- Repositories collected with data: {counts['ok_with_data']}",
                f"- Repositories collected with zero traffic: {counts['ok_zero_data']}",
            ]
        )
    return lines


def _append_secondary_limit(lines: list[str], secondary_limit: Any | None) -> None:
    if secondary_limit is None:
        return
    lines.extend(
        [
            "",
            "### Secondary Rate Limit",
            "",
            f"- Endpoint: `{secondary_limit.url}`",
            f"- Status: `{secondary_limit.response.status_code}`",
            f"- Retry source: `{secondary_limit.retry_source}`",
            f"- Retry after: `{secondary_limit.retry_after_seconds}` second(s)",
            "- Do not retry before: ",
            f"**{secondary_limit.retry_at_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}**",
            "- Action: Stop rerunning the workflow until that time has passed.",
        ]
    )


def _append_network_warnings(
    lines: list[str],
    network_warnings: list[NetworkWarning],
) -> None:
    if not network_warnings:
        return
    lines.extend(
        [
            "",
            "### Network Warnings",
            "",
            "Transient network errors were observed during collection:",
        ]
    )
    for warning in network_warnings:
        lines.append(
            "- Attempt "
            + f"{warning['attempt']} for `{warning['url']}` failed with "
            + f"`{warning['error_type']}`: {warning['message']}"
        )


def _append_warning_section(lines: list[str], title: str, warnings: list[str]) -> None:
    if not warnings:
        return
    lines.extend(["", f"### {title}", ""])
    lines.extend(f"- {warning}" for warning in warnings)
