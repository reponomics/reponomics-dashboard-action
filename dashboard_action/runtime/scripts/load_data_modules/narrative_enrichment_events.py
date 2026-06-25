"""Event context rows for narrative insight enrichment."""

from __future__ import annotations

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_events import event_near_growth_window
from load_data_modules.types import Candidate, Row


def event_items(repo: str, context: NarrativeContext) -> list[Candidate]:
    """Return normalized repository event context rows."""
    growth = context.growth.get("per_repo", {}).get(repo, {})
    events = [
        event
        for event in context.events_by_repo.get(repo, [])
        if event_near_growth_window(event, growth, slack_days=14)
    ]
    ordered = sorted(events, key=lambda row: str(row.get("event_date") or ""), reverse=True)
    return [event_item(event) for event in ordered[:2]]


def event_item(event: Row) -> Candidate:
    """Return one display-ready event context item."""
    return {
        "type": str(event.get("event_type") or "event"),
        "date": str(event.get("event_date") or ""),
        "label": str(event.get("title") or event.get("event_type") or "Repository event"),
        "detail": str(event.get("classification") or ""),
        "url": str(event.get("url") or ""),
    }
