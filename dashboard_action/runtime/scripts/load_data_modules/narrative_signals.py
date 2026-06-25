"""Repository signal helpers for narrative insight recipes."""

from __future__ import annotations

from load_data_modules.parse import _bool_or_none
from load_data_modules.narrative_values import int_value
from load_data_modules.types import Candidate, Result


def missing_community_files(community: Result) -> list[str]:
    """Return missing community-file labels from a community profile."""
    labels = [
        ("contributing guide", "has_contributing"),
        ("issue template", "has_issue_template"),
        ("pull request template", "has_pull_request_template"),
        ("README", "has_readme"),
        ("license", "has_license"),
        ("code of conduct", "has_code_of_conduct"),
    ]
    return [label for label, key in labels if _bool_or_none(community.get(key)) is False]


def missing_templates(community: Result) -> list[str]:
    """Return missing issue/PR intake template labels."""
    labels = [
        ("issue template", "has_issue_template"),
        ("pull request template", "has_pull_request_template"),
    ]
    return [label for label, key in labels if _bool_or_none(community.get(key)) is False]


def downstream_delta(row: Candidate) -> int:
    """Return combined stars, watchers, and forks delta."""
    deltas = row.get("deltas", {}) if isinstance(row, dict) else {}
    return (
        int_value(deltas.get("stargazers_delta"))
        + int_value(deltas.get("subscribers_delta"))
        + int_value(deltas.get("forks_delta"))
    )
