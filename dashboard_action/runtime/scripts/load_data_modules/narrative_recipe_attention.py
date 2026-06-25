"""Attention/readiness narrative recipe."""

from __future__ import annotations

import math

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_signals import downstream_delta, missing_community_files
from load_data_modules.narrative_values import add_candidate, evidence, int_value, short_repo
from load_data_modules.types import Candidate


def attention_without_readiness(
    candidates: list[Candidate], context: NarrativeContext
) -> None:
    """Flag attention that does not have obvious contribution paths."""
    for repo, row in context.growth.get("per_repo", {}).items():
        if attention_readiness_candidate(repo, row, context):
            add_attention_readiness_candidate(candidates, repo, row, context)


def attention_readiness_candidate(
    repo: str, row: Candidate, context: NarrativeContext
) -> bool:
    """Return whether a repo matches the attention/readiness recipe."""
    traffic = row.get("traffic", {})
    views = int_value(traffic.get("views"))
    visitors = int_value(traffic.get("uniques"))
    community = context.community.get(repo, {})
    health = community.get("health_percentage")
    has_low_health = isinstance(health, int) and health < 70
    return (
        views >= 50
        and visitors >= 10
        and downstream_delta(row) <= 0
        and (bool(missing_community_files(community)) or has_low_health)
    )


def add_attention_readiness_candidate(
    candidates: list[Candidate],
    repo: str,
    row: Candidate,
    context: NarrativeContext,
) -> None:
    """Append an attention/readiness candidate."""
    traffic = row.get("traffic", {})
    views = int_value(traffic.get("views"))
    visitors = int_value(traffic.get("uniques"))
    community = context.community.get(repo, {})
    missing = missing_community_files(community)
    primary_gap = ", ".join(missing[:2]) if missing else "low community health"
    downstream = downstream_delta(row)
    add_candidate(
        candidates,
        subtype="attention_without_readiness",
        tone="risk",
        repo=repo,
        metric="views",
        score=math.log1p(views) + math.log1p(visitors) + len(missing),
        confidence="high" if community.get("available") else "medium",
        headline=f"{short_repo(repo)} is getting attention without contribution readiness",
        body=attention_readiness_body(repo, views, visitors, primary_gap),
        evidence=[
            evidence("views", f"{views:,}"),
            evidence("visitors", f"{visitors:,}"),
            evidence("downstream delta", f"{downstream:+,}"),
            evidence("community gaps", primary_gap),
        ],
    )


def attention_readiness_body(repo: str, views: int, visitors: int, primary_gap: str) -> str:
    """Return attention/readiness body copy."""
    return (
        f"{repo} drew {views:,} views and {visitors:,} visitors without "
        + f"downstream growth. The repo is missing {primary_gap}, so new "
        + "attention may not have an obvious path into participation."
    )
