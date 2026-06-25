"""Clone-heavy adoption narrative recipe."""

from __future__ import annotations

import math

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_values import add_candidate, evidence, int_value, short_repo
from load_data_modules.types import Candidate


def clone_heavy_star_light_adoption(
    candidates: list[Candidate], context: NarrativeContext
) -> None:
    """Flag clone-heavy adoption that is quiet in star counters."""
    for repo, row in context.growth.get("per_repo", {}).items():
        if clone_heavy_candidate(row):
            add_clone_heavy_candidate(candidates, repo, row)


def clone_heavy_candidate(row: Candidate) -> bool:
    """Return whether a growth row matches clone-heavy/star-light adoption."""
    traffic = row.get("traffic", {})
    clones = int_value(traffic.get("clones"))
    views = int_value(traffic.get("views"))
    stars_delta = int_value(row.get("deltas", {}).get("stargazers_delta"))
    return clones >= 12 and (clones / max(views, 1)) >= 0.35 and stars_delta <= 0


def add_clone_heavy_candidate(
    candidates: list[Candidate], repo: str, row: Candidate
) -> None:
    """Append a clone-heavy/star-light candidate."""
    traffic = row.get("traffic", {})
    clones = int_value(traffic.get("clones"))
    views = int_value(traffic.get("views"))
    stars_delta = int_value(row.get("deltas", {}).get("stargazers_delta"))
    clone_ratio = clones / max(views, 1)
    add_candidate(
        candidates,
        subtype="clone_heavy_star_light_adoption",
        tone="explain",
        repo=repo,
        metric="clones",
        score=math.log1p(clones) * (1 + min(clone_ratio, 2)),
        confidence="medium",
        headline=f"{short_repo(repo)} is clone-heavy but star-light",
        body=clone_heavy_body(repo, clones, views, stars_delta),
        evidence=[
            evidence("clones", f"{clones:,}"),
            evidence("views", f"{views:,}"),
            evidence("star delta", f"{stars_delta:+,}"),
            evidence("clone/view ratio", f"{clone_ratio:.2f}"),
        ],
    )


def clone_heavy_body(repo: str, clones: int, views: int, stars_delta: int) -> str:
    """Return clone-heavy/star-light body copy."""
    return (
        f"{repo} had {clones:,} clones from {views:,} views with "
        + f"{stars_delta:+,} stars. That can be practical adoption even "
        + "when popularity counters stay quiet."
    )
