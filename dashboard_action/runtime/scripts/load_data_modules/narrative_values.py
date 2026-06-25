"""Value and payload helpers for narrative insight recipes."""

from __future__ import annotations

from typing import Any

from load_data_modules.parse import _int_or_none
from load_data_modules.types import Candidate, Result

NARRATIVE_KIND = "narrative"


def add_candidate(
    candidates: list[Candidate],
    *,
    subtype: str,
    tone: str,
    repo: str,
    metric: str,
    score: float,
    confidence: str,
    headline: str,
    body: str,
    evidence: list[Result],
) -> None:
    """Append a normalized narrative candidate."""
    candidates.append(
        {
            "score": score,
            "kind": NARRATIVE_KIND,
            "subtype": subtype,
            "tone": tone,
            "repo": repo,
            "metric": metric,
            "confidence": confidence,
            "headline": headline,
            "body": body,
            "text": f"{headline} {body}",
            "evidence": [item for item in evidence if item.get("value")],
        }
    )


def evidence(label: str, value: str, url: Any = "") -> Result:
    """Return one display evidence fact."""
    item: Result = {"label": label, "value": value}
    if url:
        item["url"] = str(url)
    return item


def short_repo(repo: str) -> str:
    """Return a repository name without owner when possible."""
    return repo.rsplit("/", 1)[-1] if "/" in repo else repo


def int_value(value: Any) -> int:
    """Return a tolerant integer value for retained CSV fields."""
    try:
        parsed = _int_or_none(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed is not None else 0
