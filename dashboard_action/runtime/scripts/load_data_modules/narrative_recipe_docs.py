"""Documentation audience narrative recipe."""

from __future__ import annotations

import math

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_events import (
    event_near_growth_window,
    latest_classified_event,
    looks_like_docs_path,
)
from load_data_modules.narrative_values import add_candidate, evidence, int_value, short_repo
from load_data_modules.types import Candidate, Row, Rows


def docs_or_example_found_audience(
    candidates: list[Candidate], context: NarrativeContext
) -> None:
    """Flag docs/example events that align with documentation path attention."""
    for repo, events in context.events_by_repo.items():
        candidate = docs_candidate(repo, events, context)
        if candidate:
            add_docs_candidate(candidates, repo, candidate, context)


def docs_candidate(
    repo: str, events: Rows, context: NarrativeContext
) -> tuple[Row, Rows, int] | None:
    """Return event, path rows, and views for a docs-audience match."""
    growth = context.growth.get("per_repo", {}).get(repo, {})
    doc_event = latest_classified_event(events, {"docs", "documentation"})
    if not doc_event or not event_near_growth_window(doc_event, growth, slack_days=7):
        return None
    docs_paths = [row for row in context.paths_by_repo.get(repo, []) if looks_like_docs_path(row)]
    views = sum(int_value(row.get("count")) for row in docs_paths)
    return (doc_event, docs_paths, views) if docs_paths and views >= 10 else None


def add_docs_candidate(
    candidates: list[Candidate],
    repo: str,
    candidate: tuple[Row, Rows, int],
    context: NarrativeContext,
) -> None:
    """Append a documentation-audience candidate."""
    doc_event, _docs_paths, views = candidate
    top_referrer = top_referrer_for_repo(context, repo)
    add_candidate(
        candidates,
        subtype="docs_or_example_found_audience",
        tone="opportunity",
        repo=repo,
        metric="paths",
        score=math.log1p(views) + math.log1p(int_value(top_referrer.get("count"))) + 2,
        confidence="medium",
        headline=f"{short_repo(repo)} documentation is carrying attention",
        body=docs_body(repo, views),
        evidence=[
            evidence("event", str(doc_event.get("title") or ""), doc_event.get("url")),
            evidence("docs path views", f"{views:,}"),
            evidence("top referrer", str(top_referrer.get("referrer") or "unknown")),
        ],
    )


def docs_body(repo: str, views: int) -> str:
    """Return documentation-audience body copy."""
    return (
        f"{repo} had a nearby docs/example commit and {views:,} views on "
        + "README, docs, or example paths. The pattern suggests discovery "
        + "material is doing useful work."
    )


def top_referrer_for_repo(context: NarrativeContext, repo: str) -> Row:
    """Return top retained referrer row for a repository."""
    return max(
        context.referrers_by_repo.get(repo, []),
        key=lambda row: int_value(row.get("count")),
        default={},
    )
