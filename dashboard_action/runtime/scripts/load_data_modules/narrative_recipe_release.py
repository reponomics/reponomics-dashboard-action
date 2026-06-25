"""Release/adoption narrative recipe."""

from __future__ import annotations

import math

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_events import (
    event_near_growth_window,
    release_asset_downloads,
)
from load_data_modules.narrative_values import add_candidate, evidence, int_value, short_repo
from load_data_modules.types import Candidate, Row, Rows


def release_pulled_attention_forward(
    candidates: list[Candidate], context: NarrativeContext
) -> None:
    """Flag releases that align with adoption movement."""
    for repo, events in context.events_by_repo.items():
        candidate = release_candidate(repo, events, context)
        if candidate:
            add_release_candidate(candidates, repo, candidate, context)


def release_candidate(
    repo: str, events: Rows, context: NarrativeContext
) -> tuple[Candidate, Row] | None:
    """Return growth/release rows for a release-adoption match."""
    growth = context.growth.get("per_repo", {}).get(repo, {})
    traffic = growth.get("traffic", {})
    clones = int_value(traffic.get("clones"))
    forks_delta = int_value(growth.get("deltas", {}).get("forks_delta"))
    if clones < 8 and forks_delta < 2:
        return None
    release = latest_nearby_release(events, growth)
    return (growth, release) if release else None


def latest_nearby_release(events: Rows, growth: Candidate) -> Row | None:
    """Return latest release event near a growth window."""
    releases = [
        event
        for event in events
        if event.get("event_type") == "release"
        and event_near_growth_window(event, growth, slack_days=7)
    ]
    return max(releases, key=lambda row: row.get("event_date", ""), default=None)


def add_release_candidate(
    candidates: list[Candidate],
    repo: str,
    candidate: tuple[Candidate, Row],
    context: NarrativeContext,
) -> None:
    """Append a release/adoption candidate."""
    growth, release = candidate
    traffic = growth.get("traffic", {})
    clones = int_value(traffic.get("clones"))
    views = int_value(traffic.get("views"))
    forks_delta = int_value(growth.get("deltas", {}).get("forks_delta"))
    asset_downloads = release_asset_downloads(
        context.release_assets_by_release, release
    )
    add_candidate(
        candidates,
        subtype="release_pulled_attention_forward",
        tone="opportunity",
        repo=repo,
        metric="clones",
        score=release_score(clones, forks_delta, asset_downloads),
        confidence="high" if asset_downloads else "medium",
        headline=f"{short_repo(repo)} release activity is lining up with adoption",
        body=release_body(repo, release, clones, views, forks_delta, asset_downloads),
        evidence=[
            evidence(
                "release",
                str(release.get("title") or release.get("event_id") or ""),
                release.get("url"),
            ),
            evidence("clones", f"{clones:,}"),
            evidence("fork delta", f"{forks_delta:+,}"),
            evidence("asset downloads", f"{asset_downloads:,}"),
        ],
    )


def release_score(clones: int, forks_delta: int, asset_downloads: int) -> float:
    """Score a release/adoption match."""
    return (
        math.log1p(clones) * 2
        + math.log1p(max(forks_delta, 0) + 1)
        + math.log1p(asset_downloads)
    )


def release_body(
    repo: str, release: Row, clones: int, views: int, forks_delta: int, asset_downloads: int
) -> str:
    """Return release/adoption card body copy."""
    tail = (
        f"Release assets have {asset_downloads:,} recorded downloads."
        if asset_downloads
        else "The release is the nearest project event in the selected evidence."
    )
    return (
        f"{repo} shipped {release.get('title') or 'a release'} near a window "
        + f"with {clones:,} clones, {views:,} views, and {forks_delta:+,} forks. "
        + tail
    )
