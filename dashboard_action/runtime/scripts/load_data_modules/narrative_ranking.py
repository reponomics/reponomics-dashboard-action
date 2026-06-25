"""Ranking and feed-diversity helpers for narrative insight candidates."""

from __future__ import annotations

from load_data_modules.types import Candidate


def ranked_narratives(candidates: list[Candidate], limit: int) -> list[Candidate]:
    """Return score-ranked, diversified narrative candidates without scores."""
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return [strip_score(item) for item in diversified(candidates, limit)]


def diversified(candidates: list[Candidate], limit: int) -> list[Candidate]:
    """Prefer distinct narrative types and repos, then backfill by score."""
    selected = select_diverse_candidates(candidates, limit)
    if len(selected) >= limit:
        return selected
    return backfill_candidates(candidates, selected, limit)


def select_diverse_candidates(candidates: list[Candidate], limit: int) -> list[Candidate]:
    """Select candidates without repeating subtype or repo."""
    selected: list[Candidate] = []
    seen_subtypes: set[str] = set()
    seen_repos: set[str] = set()
    for item in candidates:
        repo = str(item.get("repo") or "")
        subtype = str(item.get("subtype") or "")
        if is_repeated_candidate(repo, subtype, seen_repos, seen_subtypes):
            continue
        selected.append(item)
        seen_subtypes.add(subtype)
        if repo:
            seen_repos.add(repo)
        if len(selected) >= limit:
            return selected
    return selected


def backfill_candidates(
    candidates: list[Candidate], selected: list[Candidate], limit: int
) -> list[Candidate]:
    """Backfill remaining candidate slots by score."""
    out = list(selected)
    selected_ids = {id(item) for item in selected}
    for item in candidates:
        if id(item) in selected_ids:
            continue
        out.append(item)
        if len(out) >= limit:
            return out
    return out


def is_repeated_candidate(
    repo: str, subtype: str, seen_repos: set[str], seen_subtypes: set[str]
) -> bool:
    """Return whether a candidate repeats feed diversity dimensions."""
    return subtype in seen_subtypes or bool(repo and repo in seen_repos)


def strip_score(item: Candidate) -> Candidate:
    """Remove internal ranking score from a candidate payload."""
    return {key: value for key, value in item.items() if key != "score"}
