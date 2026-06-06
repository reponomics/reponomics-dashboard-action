"""Shared helpers for growth insight rule modules."""

from typing import Any

from load_data_modules.types import Candidate


def _add_growth_candidate(
    candidates: list[Candidate],
    *,
    repo: str,
    subtype: str,
    metric: str,
    score: float,
    text: str,
    **extra: Any,
) -> None:
    """Append a normalized growth insight candidate."""
    candidates.append(
        {
            "score": score,
            "repo": repo,
            "kind": "growth",
            "subtype": subtype,
            "metric": metric,
            "text": text,
            **extra,
        }
    )


def _downstream(context: Candidate) -> int:
    """Return the combined downstream counter movement for a repo."""
    return (
        context["stargazers_delta"]
        + context["subscribers_delta"]
        + context["forks_delta"]
    )


def _enough_for_growth(context: Candidate) -> bool:
    return context["metric_samples"] >= 2


def _enough_for_cross_signal(context: Candidate) -> bool:
    return _enough_for_growth(context) and context["traffic_samples"] >= 3
