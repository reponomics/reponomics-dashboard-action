"""Repository positioning-shift narrative recipe."""

from __future__ import annotations

import math
from typing import Any

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_signals import downstream_delta
from load_data_modules.narrative_values import add_candidate, evidence, int_value, short_repo
from load_data_modules.types import Candidate, Row, Rows

MIN_POSITIONING_VIEWS = 25
MIN_LANGUAGE_SHARE_DELTA = 0.2


def positioning_shift_met_audience(
    candidates: list[Candidate], context: NarrativeContext
) -> None:
    """Flag topic or language positioning changes that align with attention."""
    repos = set(context.latest_topics) | set(context.latest_languages)
    for repo in repos:
        candidate = positioning_candidate(repo, context)
        if candidate:
            add_positioning_candidate(candidates, repo, candidate, context)


def positioning_candidate(repo: str, context: NarrativeContext) -> Candidate | None:
    """Return a positioning change when the repo also has recent demand."""
    change = positioning_change(repo, context)
    if not change:
        return None
    growth = context.growth.get("per_repo", {}).get(repo, {})
    views = int_value(growth.get("traffic", {}).get("views"))
    downstream = downstream_delta(growth)
    if views >= MIN_POSITIONING_VIEWS or downstream > 0:
        return {**change, "views": views, "downstream": downstream}
    return None


def positioning_change(repo: str, context: NarrativeContext) -> Candidate | None:
    """Return the most useful observed positioning change."""
    added_topics = topics(context.latest_topics.get(repo, [])) - topics(
        context.previous_topics.get(repo, [])
    )
    if added_topics:
        topic = sorted(added_topics)[0]
        return {"kind": "topic", "label": topic, "delta_label": f"added topic {topic}"}
    language = language_share_shift(
        context.latest_languages.get(repo, []), context.previous_languages.get(repo, [])
    )
    return language


def topics(rows: Rows) -> set[str]:
    """Return non-empty topic labels from snapshot rows."""
    return {str(row.get("topic") or "").strip() for row in rows if row.get("topic")}


def language_share_shift(latest_rows: Rows, previous_rows: Rows) -> Candidate | None:
    """Return a notable language mix shift when one is present."""
    latest = language_shares(latest_rows)
    previous = language_shares(previous_rows)
    if not latest or not previous:
        return None
    language, share = max(latest.items(), key=lambda item: item[1])
    previous_share = previous.get(language, 0.0)
    top_previous = max(previous.items(), key=lambda item: item[1])[0]
    if language != top_previous or share - previous_share >= MIN_LANGUAGE_SHARE_DELTA:
        return {
            "kind": "language",
            "label": language,
            "share": share,
            "previous_share": previous_share,
            "delta_label": f"{language} share moved from {previous_share:.0%} to {share:.0%}",
        }
    return None


def language_shares(rows: Rows) -> dict[str, float]:
    """Return language share values from snapshot rows."""
    shares: dict[str, float] = {}
    for row in rows:
        language = str(row.get("language") or "").strip()
        if language:
            shares[language] = float_value(row.get("share"))
    return shares


def add_positioning_candidate(
    candidates: list[Candidate], repo: str, candidate: Candidate, context: NarrativeContext
) -> None:
    """Append a positioning-shift candidate."""
    views = int_value(candidate.get("views"))
    downstream = int_value(candidate.get("downstream"))
    top_referrer = top_count_row(context.referrers_by_repo.get(repo, []), "count")
    top_path = top_count_row(context.paths_by_repo.get(repo, []), "count")
    add_candidate(
        candidates,
        subtype="positioning_shift_met_audience",
        tone="opportunity",
        repo=repo,
        metric=str(candidate.get("kind") or "positioning"),
        score=math.log1p(views) + math.log1p(downstream + 1) + positioning_bonus(candidate),
        confidence="high" if top_referrer or top_path else "medium",
        headline=f"{short_repo(repo)} positioning shifted before recent attention",
        body=positioning_body(repo, candidate, views, downstream, top_referrer, top_path),
        evidence=[
            evidence("change", str(candidate.get("delta_label") or "")),
            evidence("views", f"{views:,}"),
            evidence("downstream delta", f"{downstream:+,}"),
            evidence("top referrer", str(top_referrer.get("referrer") or "")),
            evidence("top path", str(top_path.get("path") or "")),
        ],
    )


def positioning_bonus(candidate: Candidate) -> float:
    """Return a small score boost for stronger positioning changes."""
    if candidate.get("kind") == "language":
        return abs(float_value(candidate.get("share")) - float_value(candidate.get("previous_share"))) * 4
    return 2.0


def positioning_body(
    repo: str,
    candidate: Candidate,
    views: int,
    downstream: int,
    top_referrer: Row,
    top_path: Row,
) -> str:
    """Return positioning-shift body copy."""
    referrer = str(top_referrer.get("referrer") or "retained referrer data")
    path = str(top_path.get("path") or "retained path data")
    return (
        f"{repo} changed its public positioning ({candidate.get('delta_label')}) "
        + f"and then saw {views:,} views with {downstream:+,} downstream signals. "
        + f"The strongest retained context was {referrer} and {path}."
    )


def top_count_row(rows: Rows, count_field: str) -> Row:
    """Return the row with the largest retained count."""
    return max(rows, key=lambda row: int_value(row.get(count_field)), default={})


def float_value(value: Any) -> float:
    """Return a tolerant float value for retained CSV fields."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
