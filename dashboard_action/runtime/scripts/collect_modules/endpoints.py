"""GitHub API endpoint row-shaping facade."""

from collect_modules.context_endpoints import (
    collect_commit_history,
    collect_issue_pr_snapshot,
    collect_languages,
    collect_release_context,
    collect_topics,
)
from collect_modules.repo_metric_endpoints import (
    collect_repo_community_profile,
    collect_repo_detail,
    collect_repo_metrics,
    community_has_file,
    community_health_percentage,
    fallback_repo_community_warning,
    fallback_repo_detail_warning,
)
from collect_modules.traffic_endpoints import (
    collect_paths,
    collect_referrers,
    collect_views_clones,
)

__all__ = [
    "collect_commit_history",
    "collect_issue_pr_snapshot",
    "collect_languages",
    "collect_paths",
    "collect_referrers",
    "collect_release_context",
    "collect_repo_community_profile",
    "collect_repo_detail",
    "collect_repo_metrics",
    "collect_topics",
    "collect_views_clones",
    "community_has_file",
    "community_health_percentage",
    "fallback_repo_community_warning",
    "fallback_repo_detail_warning",
]
