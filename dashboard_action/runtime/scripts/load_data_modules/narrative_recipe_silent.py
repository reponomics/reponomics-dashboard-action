"""Silent-but-healthy utility narrative recipe."""

from __future__ import annotations

import math
import statistics

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_signals import downstream_delta
from load_data_modules.narrative_values import add_candidate, evidence, int_value, short_repo
from load_data_modules.types import Candidate, Row, Rows

MIN_UTILITY_CLONES = 10
MAX_QUIET_VIEWS = 60


def silent_but_healthy_utility(
    candidates: list[Candidate], context: NarrativeContext
) -> None:
    """Flag repos with quiet traffic but credible utility signals."""
    quiet_view_ceiling = quiet_ceiling(context)
    for repo, row in context.growth.get("per_repo", {}).items():
        candidate = silent_utility_candidate(repo, row, context, quiet_view_ceiling)
        if candidate:
            add_silent_utility_candidate(candidates, repo, candidate)


def quiet_ceiling(context: NarrativeContext) -> int:
    """Return a repo-relative quiet traffic ceiling."""
    views = [
        int_value(row.get("traffic", {}).get("views"))
        for row in context.growth.get("per_repo", {}).values()
    ]
    median = int(statistics.median(views)) if views else MAX_QUIET_VIEWS
    return min(MAX_QUIET_VIEWS, max(15, median))


def silent_utility_candidate(
    repo: str, row: Candidate, context: NarrativeContext, quiet_view_ceiling: int
) -> Candidate | None:
    """Return utility metrics when a quiet repo appears healthy."""
    traffic = row.get("traffic", {})
    views = int_value(traffic.get("views"))
    clones = int_value(traffic.get("clones"))
    if views > quiet_view_ceiling or clones < MIN_UTILITY_CLONES:
        return None
    health = repository_health(repo, context)
    if not health["healthy"]:
        return None
    clone_ratio = clones / max(views, 1)
    downstream = downstream_delta(row)
    if clone_ratio >= 0.45 or downstream >= 1:
        return {
            "views": views,
            "clones": clones,
            "clone_ratio": clone_ratio,
            "downstream": downstream,
            **health,
        }
    return None


def repository_health(repo: str, context: NarrativeContext) -> Candidate:
    """Return practical maintenance-health signals for quiet utility repos."""
    issue_row = context.latest_issue_pr.get(repo, {})
    latest_churn = latest_code_churn(context.code_frequency_by_repo.get(repo, []))
    open_issues = int_value(issue_row.get("open_issues_count"))
    stale_issues = int_value(issue_row.get("stale_open_issues_count"))
    unanswered = int_value(issue_row.get("unanswered_issue_count"))
    lines_changed = int_value(latest_churn.get("lines_changed"))
    healthy = open_issues <= 5 and stale_issues <= 2 and unanswered <= 2
    return {
        "healthy": healthy,
        "open_issues": open_issues,
        "stale_issues": stale_issues,
        "unanswered_issues": unanswered,
        "lines_changed": lines_changed,
        "latest_week": latest_churn.get("week_start", ""),
    }


def latest_code_churn(rows: Rows) -> Row:
    """Return latest code-frequency row with a lines_changed field."""
    row = max(rows, key=lambda item: str(item.get("week_start") or ""), default={})
    return {
        **row,
        "lines_changed": int_value(row.get("additions")) + int_value(row.get("deletions")),
    }


def add_silent_utility_candidate(candidates: list[Candidate], repo: str, row: Candidate) -> None:
    """Append a silent-but-healthy utility candidate."""
    views = int_value(row.get("views"))
    clones = int_value(row.get("clones"))
    clone_ratio = float(row.get("clone_ratio") or 0)
    downstream = int_value(row.get("downstream"))
    open_issues = int_value(row.get("open_issues"))
    lines_changed = int_value(row.get("lines_changed"))
    add_candidate(
        candidates,
        subtype="silent_but_healthy_utility",
        tone="explain",
        repo=repo,
        metric="clones",
        score=math.log1p(clones) * (1 + min(clone_ratio, 2)) + math.log1p(lines_changed),
        confidence="medium",
        headline=f"{short_repo(repo)} looks quietly useful",
        body=silent_utility_body(repo, views, clones, clone_ratio, open_issues, lines_changed),
        evidence=[
            evidence("views", f"{views:,}"),
            evidence("clones", f"{clones:,}"),
            evidence("clone/view ratio", f"{clone_ratio:.2f}"),
            evidence("downstream delta", f"{downstream:+,}"),
            evidence("open issues", f"{open_issues:,}"),
            evidence("latest code churn", f"{lines_changed:,} lines"),
        ],
    )


def silent_utility_body(
    repo: str,
    views: int,
    clones: int,
    clone_ratio: float,
    open_issues: int,
    lines_changed: int,
) -> str:
    """Return silent-but-healthy utility body copy."""
    return (
        f"{repo} is not drawing broad browsing traffic ({views:,} views), "
        + f"but {clones:,} clones and a {clone_ratio:.2f} clone/view ratio suggest use. "
        + f"With {open_issues:,} open issues and {lines_changed:,} recent changed lines, "
        + "it looks more like quiet utility than neglect."
    )
