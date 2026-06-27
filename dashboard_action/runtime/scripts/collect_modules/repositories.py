"""Repository discovery and selection facade."""

from collect_modules.repository_pages import discover_repositories
from collect_modules.repository_selection import (
    current_repository,
    is_trackable_repo,
    resolve_named_repos,
    resolve_repositories,
)

__all__ = [
    "current_repository",
    "discover_repositories",
    "is_trackable_repo",
    "resolve_named_repos",
    "resolve_repositories",
]
