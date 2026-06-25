"""Contributor context rows for narrative insight enrichment."""

from __future__ import annotations

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_enrichment_code import latest_week_row
from load_data_modules.narrative_values import int_value
from load_data_modules.types import Candidate, Rows


def contributor_item(repo: str, context: NarrativeContext) -> Candidate | None:
    """Return recent contributor activity context."""
    rows = latest_week_group(context.contributor_activity_by_repo.get(repo, []))
    if not rows:
        return None
    commits = sum(int_value(row.get("commits")) for row in rows)
    if commits <= 0:
        return None
    return {
        "type": "contributors",
        "date": str(rows[0].get("week_start") or ""),
        "label": f"{active_contributors(rows):,} active contributors",
        "detail": f"{commits:,} commits in latest contributor week",
    }


def latest_week_group(rows: Rows) -> Rows:
    """Return rows from the latest week bucket."""
    week = str(latest_week_row(rows).get("week_start") or "")
    return [row for row in rows if week and str(row.get("week_start") or "") == week]


def active_contributors(rows: Rows) -> int:
    """Return the number of contributors with commits in the row set."""
    return len(
        {
            str(row.get("author_login") or row.get("author_id") or "unknown")
            for row in rows
            if int_value(row.get("commits")) > 0
        }
    )
