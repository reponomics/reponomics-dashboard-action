"""Contributor concentration narrative recipe."""

from __future__ import annotations

import math
from collections import defaultdict

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_signals import downstream_delta, missing_community_files
from load_data_modules.narrative_values import add_candidate, evidence, int_value, short_repo
from load_data_modules.types import Candidate, Rows

MIN_CONTRIBUTOR_COMMITS = 5
CONCENTRATION_SHARE = 0.8
ContributorStats = dict[str, int | float | str]


def contributor_concentration_risk(
    candidates: list[Candidate], context: NarrativeContext
) -> None:
    """Flag repos where rising demand depends on one contributor."""
    for repo, rows in context.contributor_activity_by_repo.items():
        candidate = contributor_concentration_candidate(repo, rows, context)
        if candidate:
            add_contributor_concentration_candidate(candidates, repo, candidate, context)


def contributor_concentration_candidate(
    repo: str, rows: Rows, context: NarrativeContext
) -> ContributorStats | None:
    """Return concentration metrics for a contributor-risk match."""
    stats = contributor_stats(rows)
    growth = context.growth.get("per_repo", {}).get(repo, {})
    views = int_value(growth.get("traffic", {}).get("views"))
    downstream = downstream_delta(growth)
    open_issues = int_value(context.latest_issue_pr.get(repo, {}).get("open_issues_count"))
    has_demand = views >= 40 or downstream >= 2 or open_issues >= 5
    total_commits = int(stats["total_commits"])
    top_share = float(stats["top_share"])
    if has_demand and total_commits >= MIN_CONTRIBUTOR_COMMITS:
        return stats if top_share >= CONCENTRATION_SHARE else None
    return None


def contributor_stats(rows: Rows) -> ContributorStats:
    """Return recent contributor concentration stats."""
    commits_by_author: dict[str, int] = defaultdict(int)
    for row in recent_week_rows(rows, 4):
        author = str(row.get("author_login") or row.get("author_id") or "unknown")
        commits_by_author[author] += int_value(row.get("commits"))
    total = sum(commits_by_author.values())
    top_author, top_commits = max(
        commits_by_author.items(), key=lambda item: item[1], default=("", 0)
    )
    return {
        "active_contributors": len([value for value in commits_by_author.values() if value]),
        "top_author": top_author,
        "top_commits": top_commits,
        "top_share": top_commits / max(total, 1),
        "total_commits": total,
    }


def recent_week_rows(rows: Rows, week_count: int) -> Rows:
    """Return rows from the latest retained week buckets."""
    weeks = sorted({str(row.get("week_start") or "") for row in rows if row.get("week_start")})
    selected = set(weeks[-week_count:])
    return [row for row in rows if str(row.get("week_start") or "") in selected]


def add_contributor_concentration_candidate(
    candidates: list[Candidate],
    repo: str,
    stats: ContributorStats,
    context: NarrativeContext,
) -> None:
    """Append a contributor concentration candidate."""
    growth = context.growth.get("per_repo", {}).get(repo, {})
    views = int_value(growth.get("traffic", {}).get("views"))
    downstream = downstream_delta(growth)
    missing = missing_community_files(context.community.get(repo, {}))
    active = int(stats["active_contributors"])
    top_share = float(stats["top_share"])
    add_candidate(
        candidates,
        subtype="contributor_concentration_risk",
        tone="watch",
        repo=repo,
        metric="contributors",
        score=math.log1p(int(stats["total_commits"])) + top_share * 4 + math.log1p(views),
        confidence="high" if active > 1 else "medium",
        headline=f"{short_repo(repo)} demand is concentrated on one contributor",
        body=contributor_body(repo, views, downstream, stats, missing),
        evidence=[
            evidence("views", f"{views:,}"),
            evidence("downstream delta", f"{downstream:+,}"),
            evidence("top contributor share", f"{top_share:.0%}"),
            evidence("active contributors", f"{active:,}"),
        ],
    )


def contributor_body(
    repo: str,
    views: int,
    downstream: int,
    stats: ContributorStats,
    missing: list[str],
) -> str:
    """Return contributor concentration body copy."""
    guidance = (
        f" Missing {', '.join(missing[:2])} may keep that load concentrated."
        if missing
        else ""
    )
    return (
        f"{repo} saw {views:,} views and {downstream:+,} downstream signals while "
        + f"{stats['top_author'] or 'one contributor'} accounted for "
        + f"{float(stats['top_share']):.0%} of recent commits."
        + guidance
    )
