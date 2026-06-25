"""Shared narrative context enrichment for dashboard insight cards."""

from __future__ import annotations

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_enrichment_code import code_churn_item
from load_data_modules.narrative_enrichment_contributors import contributor_item
from load_data_modules.narrative_enrichment_events import event_items
from load_data_modules.narrative_enrichment_maintenance import maintenance_item
from load_data_modules.narrative_enrichment_positioning import positioning_item
from load_data_modules.types import Candidate

MAX_CONTEXT_ITEMS = 4


def enrich_narrative_candidates(
    candidates: list[Candidate], context: NarrativeContext
) -> None:
    """Attach nearby repository context to narrative candidates."""
    for candidate in candidates:
        repo = str(candidate.get("repo") or "")
        if not repo:
            continue
        items = nearby_context_items(repo, context)
        if items:
            candidate["nearby_context"] = items[:MAX_CONTEXT_ITEMS]


def nearby_context_items(repo: str, context: NarrativeContext) -> list[Candidate]:
    """Return concise context rows describing what changed near the signal."""
    items: list[Candidate] = []
    items.extend(event_items(repo, context))
    add_item(items, code_churn_item(repo, context))
    add_item(items, contributor_item(repo, context))
    add_item(items, positioning_item(repo, context))
    add_item(items, maintenance_item(repo, context))
    return sorted(items, key=context_sort_key, reverse=True)


def context_sort_key(item: Candidate) -> str:
    """Return date-ish key for context sorting."""
    return str(item.get("date") or "")


def add_item(items: list[Candidate], item: Candidate | None) -> None:
    """Append an optional context item."""
    if item:
        items.append(item)
