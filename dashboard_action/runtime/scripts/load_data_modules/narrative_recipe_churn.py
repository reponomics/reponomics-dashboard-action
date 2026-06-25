"""Code churn context narrative recipe."""

from __future__ import annotations

import math
import statistics

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_events import event_near_growth_window
from load_data_modules.narrative_values import add_candidate, evidence, int_value, short_repo
from load_data_modules.types import Candidate, Row, Rows

CHURN_CLASSIFICATIONS = {"refactor", "dependency", "ci", "tests", "unknown"}
MIN_CHURN_LINES = 200
TrafficDip = dict[str, int | str]
ChurnStats = dict[str, int | str]


def code_churn_explains_dip(candidates: list[Candidate], context: NarrativeContext) -> None:
    """Flag traffic dips that align with internal code churn."""
    for repo, weekly_rows in context.code_frequency_by_repo.items():
        candidate = churn_candidate(repo, weekly_rows, context)
        if candidate:
            add_churn_candidate(candidates, repo, candidate)


def churn_candidate(
    repo: str, weekly_rows: Rows, context: NarrativeContext
) -> dict[str, object] | None:
    """Return churn context when a traffic dip aligns with churn."""
    dip = traffic_dip(context.daily_by_repo.get(repo, []))
    churn = latest_churn(weekly_rows)
    if not dip or int_value(churn.get("lines_changed")) < MIN_CHURN_LINES:
        return None
    event = latest_churn_event(context.events_by_repo.get(repo, []), context, repo)
    return {"dip": dip, "churn": churn, "event": event}


def traffic_dip(rows: Rows) -> TrafficDip | None:
    """Return latest traffic dip stats versus trailing median."""
    ordered = sorted(rows, key=lambda row: str(row.get("ts") or ""))
    if len(ordered) < 6:
        return None
    latest = int_value(ordered[-1].get("views_count"))
    baseline_values = [int_value(row.get("views_count")) for row in ordered[-6:-1]]
    median = int(statistics.median(baseline_values)) if baseline_values else 0
    if median >= 10 and latest <= median * 0.5:
        return {"latest": latest, "baseline": median, "date": str(ordered[-1].get("ts") or "")}
    return None


def latest_churn(rows: Rows) -> ChurnStats:
    """Return latest weekly churn totals."""
    row = max(rows, key=lambda item: str(item.get("week_start") or ""), default={})
    additions = int_value(row.get("additions"))
    deletions = int_value(row.get("deletions"))
    return {
        "week_start": str(row.get("week_start") or ""),
        "additions": additions,
        "deletions": deletions,
        "lines_changed": additions + deletions,
    }


def latest_churn_event(events: Rows, context: NarrativeContext, repo: str) -> Row:
    """Return latest internal-work event near the growth window."""
    growth = context.growth.get("per_repo", {}).get(repo, {})
    matches = [
        event
        for event in events
        if str(event.get("classification") or "").lower() in CHURN_CLASSIFICATIONS
        and event_near_growth_window(event, growth, slack_days=14)
    ]
    return max(matches, key=lambda row: row.get("event_date", ""), default={})


def add_churn_candidate(
    candidates: list[Candidate], repo: str, candidate: dict[str, object]
) -> None:
    """Append a code-churn explanation candidate."""
    dip = candidate["dip"] if isinstance(candidate["dip"], dict) else {}
    churn = candidate["churn"] if isinstance(candidate["churn"], dict) else {}
    event = candidate["event"] if isinstance(candidate["event"], dict) else {}
    lines_changed = int_value(churn.get("lines_changed"))
    latest = int_value(dip.get("latest"))
    baseline = int_value(dip.get("baseline"))
    add_candidate(
        candidates,
        subtype="code_churn_explains_dip",
        tone="explain",
        repo=repo,
        metric="views",
        score=math.log1p(lines_changed) + math.log1p(baseline - latest),
        confidence="high" if event else "medium",
        headline=f"{short_repo(repo)} traffic dip lines up with code churn",
        body=churn_body(repo, dip, churn, event),
        evidence=[
            evidence("latest views", f"{latest:,}"),
            evidence("baseline views", f"{baseline:,}"),
            evidence("lines changed", f"{lines_changed:,}"),
            evidence("event", str(event.get("title") or ""), event.get("url")),
        ],
    )


def churn_body(repo: str, dip: TrafficDip, churn: ChurnStats, event: Row) -> str:
    """Return code-churn body copy."""
    event_text = f" A nearby internal event was {event.get('title')}." if event else ""
    latest = int_value(dip.get("latest"))
    baseline = int_value(dip.get("baseline"))
    lines_changed = int_value(churn.get("lines_changed"))
    return (
        f"{repo} latest views fell to {latest:,} versus a "
        + f"{baseline:,} trailing median while "
        + f"{lines_changed:,} lines changed in the latest code-frequency week."
        + event_text
    )
