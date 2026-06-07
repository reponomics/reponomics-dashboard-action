"""Repository discovery and selection facade."""

from collect_modules.repository_pages import discover_repositories
from collect_modules.repository_selection import (
    build_auto_candidates,
    current_repository,
    is_trackable_repo,
    resolve_named_repos,
    resolve_repositories,
    selection_state,
    sort_auto_candidates,
)

__all__ = [
    "build_auto_candidates",
    "current_repository",
    "discover_repositories",
    "is_trackable_repo",
    "resolve_named_repos",
    "resolve_repositories",
    "selection_state",
    "sort_auto_candidates",
]
