"""Counter-oriented cross-signal growth insight rules."""

import math

from load_data_modules.growth.insight_support import (
    _add_growth_candidate,
    _enough_for_growth,
)
from load_data_modules.types import Candidate


def _fork_spike(candidates: list[Candidate], context: Candidate) -> None:
    """Flag meaningful fork growth in the selected window."""
    fork_delta = context["forks_delta"]
    if not (_enough_for_growth(context) and fork_delta >= 2):
        return
    score, denom = _conversion_adjusted_score(context, "forks", fork_delta, 2.4, 0.5)
    _add_growth_candidate(
        candidates,
        repo=context["repo"],
        subtype="fork_spike",
        metric="forks",
        score=score,
        delta=fork_delta,
        denominator=denom,
        text=f"`{context['repo']}` forks jumped {fork_delta:+,} in the selected window.",
    )


def _watcher_subscriber_spike(candidates: list[Candidate], context: Candidate) -> None:
    """Flag meaningful watcher/subscriber growth in the selected window."""
    subscriber_delta = context["subscribers_delta"]
    if not (_enough_for_growth(context) and subscriber_delta >= 3):
        return
    score, denom = _conversion_adjusted_score(
        context, "subscribers", subscriber_delta, 2.0, 0.4
    )
    _add_growth_candidate(
        candidates,
        repo=context["repo"],
        subtype="watcher_subscriber_spike",
        metric="subscribers",
        score=score,
        delta=subscriber_delta,
        denominator=denom,
        text=f"`{context['repo']}` watchers rose {subscriber_delta:+,} in the selected window.",
    )


def _conversion_adjusted_score(
    context: Candidate, metric: str, delta: int, multiplier: float, cap: float
) -> tuple[float, int]:
    """Score counter movement, boosting it when conversion data is reliable."""
    conversion = context["conversions"].get(metric, {})
    denom = conversion.get("denominator", 0) or 0
    value = conversion.get("value")
    score = math.log1p(delta) * multiplier
    if denom >= 10 and value is not None:
        score *= 1.0 + min(abs(value), cap)
    return score, denom


def _negative_counter_movement(candidates: list[Candidate], context: Candidate) -> None:
    """Flag any observed negative downstream counter movement."""
    if not _enough_for_growth(context):
        return
    for metric, delta in _negative_deltas(context).items():
        _add_growth_candidate(
            candidates,
            repo=context["repo"],
            subtype="negative_counter_movement",
            metric=metric,
            score=math.log1p(abs(delta)) * 3.0,
            delta=delta,
            text=f"`{context['repo']}` {metric} moved backward {delta:+,} in the selected window.",
        )


def _negative_deltas(context: Candidate) -> dict[str, int]:
    """Return downstream metrics whose window deltas are below zero."""
    return {
        metric: delta
        for metric, delta in {
            "stars": context["stargazers_delta"],
            "subscribers": context["subscribers_delta"],
            "forks": context["forks_delta"],
        }.items()
        if delta < 0
    }
