"""Event matching helpers for narrative insight recipes."""

from __future__ import annotations

from datetime import date, timedelta

from load_data_modules.narrative_values import int_value
from load_data_modules.types import Candidate, Row, Rows

DOC_TEXT_TOKENS = ("readme", "docs", "doc ", "example", "guide")
DOC_PATH_TOKENS = ("readme", "docs", "doc/", "example", "guide")


def release_asset_downloads(
    release_assets_by_release: dict[tuple[str, str], Rows], release: Row
) -> int:
    """Return latest retained download count sum for a release."""
    key = (str(release.get("repo") or ""), str(release.get("release_id") or ""))
    return sum(
        int_value(row.get("download_count"))
        for row in release_assets_by_release.get(key, [])
    )


def latest_classified_event(events: Rows, classifications: set[str]) -> Row | None:
    """Return latest event whose class or title looks relevant."""
    matches = [row for row in events if classified_event_matches(row, classifications)]
    return max(matches, key=lambda row: row.get("event_date", ""), default=None)


def classified_event_matches(row: Row, classifications: set[str]) -> bool:
    """Return whether an event row belongs to a recipe classification set."""
    classification = str(row.get("classification") or "").lower()
    return classification in classifications or looks_like_docs_text(
        str(row.get("title") or "")
    )


def looks_like_docs_path(row: Row) -> bool:
    """Return whether a path row is likely documentation or examples."""
    text = f"{row.get('path') or ''} {row.get('title') or ''}".lower()
    return any(token in text for token in DOC_PATH_TOKENS)


def looks_like_docs_text(text: str) -> bool:
    """Return whether text looks documentation/example-related."""
    normalized = text.lower()
    return any(token in normalized for token in DOC_TEXT_TOKENS)


def event_near_growth_window(event: Row, growth_row: Candidate, *, slack_days: int) -> bool:
    """Return whether an event falls inside or near a growth window."""
    event_day = parse_date(str(event.get("event_date") or ""))
    start, end = growth_window(growth_row)
    if not event_day or not start or not end:
        return True
    return start - timedelta(days=slack_days) <= event_day <= end + timedelta(days=slack_days)


def growth_window(growth_row: Candidate) -> tuple[date | None, date | None]:
    """Return start/end dates from a growth analytics row."""
    deltas = growth_row.get("deltas", {}) if isinstance(growth_row, dict) else {}
    return (
        parse_date(str(deltas.get("start_date") or "")),
        parse_date(str(deltas.get("end_date") or "")),
    )


def parse_date(value: str) -> date | None:
    """Parse an ISO date or datetime prefix."""
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
