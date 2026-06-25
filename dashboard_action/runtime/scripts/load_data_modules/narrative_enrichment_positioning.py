"""Repository positioning context rows for narrative insight enrichment."""

from __future__ import annotations

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.types import Candidate, Row, Rows


def positioning_item(repo: str, context: NarrativeContext) -> Candidate | None:
    """Return topic or language positioning context."""
    added = topic_set(context.latest_topics.get(repo, [])) - topic_set(
        context.previous_topics.get(repo, [])
    )
    if added:
        return {
            "type": "positioning",
            "date": latest_capture(context.latest_topics.get(repo, [])),
            "label": f"Added topic {sorted(added)[0]}",
            "detail": "Repository topic changed",
        }
    language = top_language(context.latest_languages.get(repo, []))
    if not language:
        return None
    return {
        "type": "positioning",
        "date": latest_capture(context.latest_languages.get(repo, [])),
        "label": f"Top language {language.get('language')}",
        "detail": f"{float_value(language.get('share')):.0%} of retained language share",
    }


def topic_set(rows: Rows) -> set[str]:
    """Return non-empty topic strings."""
    return {str(row.get("topic") or "").strip() for row in rows if row.get("topic")}


def top_language(rows: Rows) -> Row:
    """Return the largest retained language row."""
    return max(rows, key=lambda row: float_value(row.get("share")), default={})


def latest_capture(rows: Rows) -> str:
    """Return the latest captured_at value from snapshot rows."""
    return max((str(row.get("captured_at") or "") for row in rows), default="")


def float_value(value: object) -> float:
    """Return a tolerant float value."""
    try:
        return float(str(value or 0))
    except (TypeError, ValueError):
        return 0.0
