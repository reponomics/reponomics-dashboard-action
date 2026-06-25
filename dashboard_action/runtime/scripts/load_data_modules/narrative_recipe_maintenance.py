"""Maintenance-pressure narrative recipe."""

from __future__ import annotations

import math

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_signals import downstream_delta, missing_templates
from load_data_modules.narrative_values import add_candidate, evidence, int_value, short_repo
from load_data_modules.types import Candidate, Row

PRESSURE_LABEL_BUCKETS = ("bug", "question", "stale")


def maintenance_pressure(candidates: list[Candidate], context: NarrativeContext) -> None:
    """Flag attention that coincides with issue/PR pressure."""
    for repo, issue_row in context.latest_issue_pr.items():
        candidate = maintenance_candidate(repo, issue_row, context)
        if candidate:
            add_maintenance_candidate(candidates, repo, candidate, context)


def maintenance_candidate(
    repo: str, issue_row: Row, context: NarrativeContext
) -> tuple[Candidate, Row] | None:
    """Return growth and issue rows for a maintenance-pressure match."""
    growth = context.growth.get("per_repo", {}).get(repo, {})
    traffic = growth.get("traffic", {})
    views = int_value(traffic.get("views"))
    downstream = downstream_delta(growth)
    open_issues = int_value(issue_row.get("open_issues_count"))
    open_prs = int_value(issue_row.get("open_prs_count"))
    return (growth, issue_row) if (views >= 40 or downstream >= 2) and (open_issues >= 5 or open_prs >= 3) else None


def add_maintenance_candidate(
    candidates: list[Candidate],
    repo: str,
    candidate: tuple[Candidate, Row],
    context: NarrativeContext,
) -> None:
    """Append a maintenance-pressure candidate."""
    growth, issue_row = candidate
    views = int_value(growth.get("traffic", {}).get("views"))
    downstream = downstream_delta(growth)
    open_issues = int_value(issue_row.get("open_issues_count"))
    open_prs = int_value(issue_row.get("open_prs_count"))
    pressure_labels = pressure_label_count(context, repo)
    missing = missing_templates(context.community.get(repo, {}))
    add_candidate(
        candidates,
        subtype="maintenance_pressure",
        tone="watch",
        repo=repo,
        metric="issues",
        score=maintenance_score(views, downstream, open_issues, open_prs, pressure_labels),
        confidence="high" if pressure_labels or missing else "medium",
        headline=f"{short_repo(repo)} attention is meeting maintenance load",
        body=maintenance_body(repo, views, downstream, open_issues, open_prs, missing),
        evidence=[
            evidence("views", f"{views:,}"),
            evidence("open issues", f"{open_issues:,}"),
            evidence("open PRs", f"{open_prs:,}"),
            evidence("pressure labels", f"{pressure_labels:,}"),
        ],
    )


def pressure_label_count(context: NarrativeContext, repo: str) -> int:
    """Return sampled label count for pressure-oriented buckets."""
    labels = context.latest_labels.get(repo, {})
    return sum(labels.get(bucket, 0) for bucket in PRESSURE_LABEL_BUCKETS)


def maintenance_score(
    views: int, downstream: int, open_issues: int, open_prs: int, pressure_labels: int
) -> float:
    """Score a maintenance-pressure candidate."""
    return math.log1p(views + downstream) + math.log1p(open_issues + open_prs) + pressure_labels


def maintenance_body(
    repo: str,
    views: int,
    downstream: int,
    open_issues: int,
    open_prs: int,
    missing: list[str],
) -> str:
    """Return maintenance-pressure body copy."""
    template_note = (
        f" Missing {', '.join(missing)} may make intake harder." if missing else ""
    )
    return (
        f"{repo} has {open_issues:,} open issues and {open_prs:,} open PRs "
        + f"near a window with {views:,} views and {downstream:+,} downstream signals."
        + template_note
    )
