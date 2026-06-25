"""Code activity context rows for narrative insight enrichment."""

from __future__ import annotations

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_values import int_value
from load_data_modules.types import Candidate, Row, Rows


def code_churn_item(repo: str, context: NarrativeContext) -> Candidate | None:
    """Return latest code-frequency context."""
    row = latest_week_row(context.code_frequency_by_repo.get(repo, []))
    if not row:
        return None
    additions = int_value(row.get("additions"))
    deletions = int_value(row.get("deletions"))
    changed = additions + deletions
    if changed <= 0:
        return None
    return {
        "type": "code",
        "date": str(row.get("week_start") or ""),
        "label": f"{changed:,} lines changed",
        "detail": f"{additions:,} additions, {deletions:,} deletions",
    }


def latest_week_row(rows: Rows) -> Row:
    """Return the latest weekly row."""
    return max(rows, key=lambda row: str(row.get("week_start") or ""), default={})
