"""Maintenance queue context rows for narrative insight enrichment."""

from __future__ import annotations

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_values import int_value
from load_data_modules.types import Candidate


def maintenance_item(repo: str, context: NarrativeContext) -> Candidate | None:
    """Return issue and PR queue context."""
    row = context.latest_issue_pr.get(repo, {})
    if not row:
        return None
    open_issues = int_value(row.get("open_issues_count"))
    open_prs = int_value(row.get("open_prs_count"))
    stale = int_value(row.get("stale_open_issues_count"))
    return {
        "type": "maintenance",
        "date": str(row.get("captured_at") or row.get("ts") or ""),
        "label": f"{open_issues:,} open issues, {open_prs:,} open PRs",
        "detail": f"{stale:,} stale open issues",
    }
