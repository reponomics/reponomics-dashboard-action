"""Contextual narrative insight orchestration for the HTML dashboard."""

from __future__ import annotations

from load_data_modules.growth.core import growth_analytics
from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_enrichment import enrich_narrative_candidates
from load_data_modules.narrative_ranking import ranked_narratives
from load_data_modules.narrative_rules import build_narrative_candidates
from load_data_modules.types import Candidate, Rows


def narrative_insights_structured(
    daily_rows: Rows,
    metric_rows: Rows,
    *,
    path_rows: Rows | None = None,
    referrer_rows: Rows | None = None,
    event_rows: Rows | None = None,
    release_asset_rows: Rows | None = None,
    issue_pr_rows: Rows | None = None,
    issue_label_rows: Rows | None = None,
    endpoint_rows: Rows | None = None,
    collection_day_rows: Rows | None = None,
    language_rows: Rows | None = None,
    topic_rows: Rows | None = None,
    code_frequency_rows: Rows | None = None,
    contributor_activity_rows: Rows | None = None,
    growth: Candidate | None = None,
    limit: int = 5,
) -> list[Candidate]:
    """Return ranked contextual narrative cards for the dashboard insight feed."""
    if limit <= 0:
        return []
    context = narrative_context(
        metric_rows=metric_rows,
        daily_rows=daily_rows,
        path_rows=path_rows,
        referrer_rows=referrer_rows,
        event_rows=event_rows,
        release_asset_rows=release_asset_rows,
        issue_pr_rows=issue_pr_rows,
        issue_label_rows=issue_label_rows,
        endpoint_rows=endpoint_rows,
        collection_day_rows=collection_day_rows,
        language_rows=language_rows,
        topic_rows=topic_rows,
        code_frequency_rows=code_frequency_rows,
        contributor_activity_rows=contributor_activity_rows,
        growth=growth if growth is not None else growth_analytics(daily_rows, metric_rows),
    )
    candidates = build_narrative_candidates(context)
    enrich_narrative_candidates(candidates, context)
    return ranked_narratives(candidates, limit)


def narrative_context(
    *,
    metric_rows: Rows,
    daily_rows: Rows | None,
    path_rows: Rows | None,
    referrer_rows: Rows | None,
    event_rows: Rows | None,
    release_asset_rows: Rows | None,
    issue_pr_rows: Rows | None,
    issue_label_rows: Rows | None,
    endpoint_rows: Rows | None,
    collection_day_rows: Rows | None,
    language_rows: Rows | None,
    topic_rows: Rows | None,
    code_frequency_rows: Rows | None,
    contributor_activity_rows: Rows | None,
    growth: Candidate,
) -> NarrativeContext:
    """Build the indexed narrative context from optional retained rows."""
    context = NarrativeContext(
        metric_rows=metric_rows,
        daily_rows=rows_or_empty(daily_rows),
        path_rows=rows_or_empty(path_rows),
        referrer_rows=rows_or_empty(referrer_rows),
        event_rows=rows_or_empty(event_rows),
        release_asset_rows=rows_or_empty(release_asset_rows),
        issue_pr_rows=rows_or_empty(issue_pr_rows),
        issue_label_rows=rows_or_empty(issue_label_rows),
        endpoint_rows=rows_or_empty(endpoint_rows),
        collection_day_rows=rows_or_empty(collection_day_rows),
        language_rows=rows_or_empty(language_rows),
        topic_rows=rows_or_empty(topic_rows),
        code_frequency_rows=rows_or_empty(code_frequency_rows),
        contributor_activity_rows=rows_or_empty(contributor_activity_rows),
        growth=growth,
    )
    return context


def rows_or_empty(rows: Rows | None) -> Rows:
    """Normalize optional retained rows."""
    return [] if rows is None else rows
