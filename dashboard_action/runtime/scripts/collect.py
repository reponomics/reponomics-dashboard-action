"""Fetch traffic and aggregate repository metric data from the GitHub API.

This module preserves the historical public import surface while delegating
cohesive implementation work to collect_modules.
"""

from __future__ import annotations

import random
import time
from typing import Any

import requests

from collect_modules.auth import (
    get_headers as _auth_get_headers,
    load_config as _auth_load_config,
    use_github_app_collection_token as _auth_use_github_app_collection_token,
    validate_token as _auth_validate_token,
)
from collect_modules.constants import (
    APP_REPO_DISCOVERY_URL as APP_REPO_DISCOVERY_URL,
    APP_TOKEN_VALIDATION_URL as APP_TOKEN_VALIDATION_URL,
    CONFIG_PATH as CONFIG_PATH,
    CURRENT_REPOSITORY_ENV_KEYS as CURRENT_REPOSITORY_ENV_KEYS,
    MAX_RETRIES as MAX_RETRIES,
    NOT_FOUND_RETRIES as NOT_FOUND_RETRIES,
    REPO_DISCOVERY_PAGE_SIZE as REPO_DISCOVERY_PAGE_SIZE,
    REPO_DISCOVERY_URL as REPO_DISCOVERY_URL,
    REQUEST_PACING_MAX_SECONDS,
    REQUEST_PACING_MIN_SECONDS,
    RETRY_BACKOFF as RETRY_BACKOFF,
    SECONDARY_LIMIT_FALLBACK_SECONDS as SECONDARY_LIMIT_FALLBACK_SECONDS,
    TOKEN_CREATION_URL as TOKEN_CREATION_URL,
    TOKEN_VALIDATION_URL as TOKEN_VALIDATION_URL,
)
from collect_modules.endpoints import (
    collect_commit_history as _endpoints_collect_commit_history,
    collect_code_frequency_weekly as _endpoints_collect_code_frequency_weekly,
    collect_contributor_activity_weekly as _endpoints_collect_contributor_activity_weekly,
    collect_issue_pr_snapshot as _endpoints_collect_issue_pr_snapshot,
    collect_languages as _endpoints_collect_languages,
    collect_paths as _endpoints_collect_paths,
    collect_referrers as _endpoints_collect_referrers,
    collect_release_context as _endpoints_collect_release_context,
    collect_repo_community_profile as _endpoints_collect_repo_community_profile,
    collect_repo_detail as _endpoints_collect_repo_detail,
    collect_repo_metrics as _endpoints_collect_repo_metrics,
    collect_topics as _endpoints_collect_topics,
    collect_views_clones as _endpoints_collect_views_clones,
    community_has_file as _endpoints_community_has_file,
    community_health_percentage as _endpoints_community_health_percentage,
    fallback_repo_community_warning as _endpoints_fallback_repo_community_warning,
    fallback_repo_detail_warning as _endpoints_fallback_repo_detail_warning,
)
from collect_modules.http import (
    RepoUnavailableError as RepoUnavailableError,
    SecondaryRateLimitError,
    fetch_json as _http_fetch_json,
    fetch_json_with_status as _http_fetch_json_with_status,
    is_retryable_throttle as _http_is_retryable_throttle,
    is_secondary_rate_limit as _http_is_secondary_rate_limit,
    parse_retry_after_seconds as _http_parse_retry_after_seconds,
    response_text_lower as _http_response_text_lower,
    retry_delay_with_jitter as _http_retry_delay_with_jitter,
    secondary_retry_window as _http_secondary_retry_window,
)
from collect_modules.context_endpoints import RepositoryStatisticsStatus as RepositoryStatisticsStatus
from collect_modules.repositories import (
    build_auto_candidates as _repositories_build_auto_candidates,
    current_repository as _repositories_current_repository,
    discover_repositories as _repositories_discover_repositories,
    is_trackable_repo as _repositories_is_trackable_repo,
    resolve_named_repos as _repositories_resolve_named_repos,
    resolve_repositories as _repositories_resolve_repositories,
    selection_state as _repositories_selection_state,
    sort_auto_candidates as _repositories_sort_auto_candidates,
)
from collect_modules.runner import CollectionDependencies, run_collection
from collect_modules.status import (
    append_collection_status as _status_append_collection_status,
    collection_status_counts as _status_collection_status_counts,
    collection_status_row as _status_collection_status_row,
    has_nonzero_traffic as _status_has_nonzero_traffic,
    write_step_summary as _status_write_step_summary,
)
from collect_modules.types import Headers, NetworkWarning, RepoMetadata
from storage import (
    COLLECTION_STATUS_FIELDS as COLLECTION_STATUS_FIELDS,
    DATA_DIR as DATA_DIR,
    LOG_FIELDS as LOG_FIELDS,
    PATH_FIELDS as PATH_FIELDS,
    REFERRER_FIELDS as REFERRER_FIELDS,
    REPO_METRIC_FIELDS as REPO_METRIC_FIELDS,
    SCHEMA_VERSION as SCHEMA_VERSION,
    SNAPSHOT_FIELDS as SNAPSHOT_FIELDS,
    append_csv,
    read_manifest,
    write_manifest,
)

_LAST_REQUEST_COMPLETED_AT: float | None = None
_NETWORK_WARNINGS: list[NetworkWarning] = []
_REPO_DETAIL_WARNINGS: list[str] = []
_REPO_COMMUNITY_WARNINGS: list[str] = []
_REPO_CONTEXT_WARNINGS: list[str] = []


def _reset_runtime_state() -> None:
    """Reset per-run pacing and warning state."""
    global _LAST_REQUEST_COMPLETED_AT, _NETWORK_WARNINGS, _REPO_DETAIL_WARNINGS
    global _REPO_COMMUNITY_WARNINGS, _REPO_CONTEXT_WARNINGS
    _LAST_REQUEST_COMPLETED_AT = None
    _NETWORK_WARNINGS = []
    _REPO_DETAIL_WARNINGS = []
    _REPO_COMMUNITY_WARNINGS = []
    _REPO_CONTEXT_WARNINGS = []


def _record_network_warning(
    url: str,
    attempt: int,
    exc: requests.RequestException,
) -> None:
    """Track transient network problems for the workflow summary."""
    _NETWORK_WARNINGS.append(
        {
            "url": url,
            "attempt": attempt,
            "error_type": exc.__class__.__name__,
            "message": str(exc),
        }
    )


_collection_status_row = _status_collection_status_row


def _append_collection_status(row: dict[str, Any]) -> None:
    _status_append_collection_status(row, data_dir=DATA_DIR)


_has_nonzero_traffic = _status_has_nonzero_traffic
_collection_status_counts = _status_collection_status_counts


def _write_step_summary(
    outcome: str,
    errors: list[str] | None = None,
    secondary_limit: SecondaryRateLimitError | None = None,
    skipped_repos: list[str] | None = None,
    status_rows: list[dict[str, Any]] | None = None,
) -> None:
    _status_write_step_summary(
        outcome,
        errors=errors,
        secondary_limit=secondary_limit,
        skipped_repos=skipped_repos,
        status_rows=status_rows,
        network_warnings=_NETWORK_WARNINGS,
        repo_detail_warnings=_REPO_DETAIL_WARNINGS,
        repo_community_warnings=_REPO_COMMUNITY_WARNINGS,
        repo_context_warnings=_REPO_CONTEXT_WARNINGS,
    )


def _pace_request() -> None:
    """Serialize requests with a small random gap to avoid bursty polling."""
    global _LAST_REQUEST_COMPLETED_AT
    _LAST_REQUEST_COMPLETED_AT = _LAST_REQUEST_COMPLETED_AT or None
    if _LAST_REQUEST_COMPLETED_AT is None:
        return

    target_gap = random.uniform(
        REQUEST_PACING_MIN_SECONDS,
        REQUEST_PACING_MAX_SECONDS,
    )
    elapsed = time.monotonic() - _LAST_REQUEST_COMPLETED_AT
    if elapsed < target_gap:
        time.sleep(target_gap - elapsed)


def _mark_request_complete() -> None:
    """Track when the previous request finished for pacing."""
    global _LAST_REQUEST_COMPLETED_AT
    _LAST_REQUEST_COMPLETED_AT = time.monotonic()


def _perform_get(url: str, headers: Headers, timeout: int) -> requests.Response:
    """Issue a paced GET request and update pacing state afterwards."""
    _pace_request()
    try:
        return requests.get(url, headers=headers, timeout=timeout)
    finally:
        _mark_request_complete()


_response_text_lower = _http_response_text_lower
_is_secondary_rate_limit = _http_is_secondary_rate_limit
_parse_retry_after_seconds = _http_parse_retry_after_seconds
_secondary_retry_window = _http_secondary_retry_window
_is_retryable_throttle = _http_is_retryable_throttle
_retry_delay_with_jitter = _http_retry_delay_with_jitter


def load_config() -> dict[str, Any]:
    return _auth_load_config(CONFIG_PATH)


def _use_github_app_collection_token() -> bool:
    return _auth_use_github_app_collection_token()


def get_headers() -> dict[str, str]:
    return _auth_get_headers(use_github_app=_use_github_app_collection_token)


def validate_token(headers: Headers, *, use_github_app: bool | None = None) -> None:
    _auth_validate_token(
        headers,
        use_github_app=use_github_app,
        use_github_app_collection_token=_use_github_app_collection_token,
        perform_get=_perform_get,
        record_network_warning=_record_network_warning,
        write_step_summary=_write_step_summary,
    )


def fetch_json(
    url: str,
    headers: Headers,
    allow_not_found: bool = False,
) -> Any:
    return _http_fetch_json(
        url,
        headers,
        allow_not_found,
        perform_get=_perform_get,
        record_network_warning=_record_network_warning,
        sleep=time.sleep,
        retry_delay=_retry_delay_with_jitter,
    )


def fetch_json_with_status(
    url: str,
    headers: Headers,
    allow_not_found: bool = False,
    *,
    accepted_statuses: set[int] | None = None,
) -> tuple[int, object | None, dict[str, str]]:
    return _http_fetch_json_with_status(
        url,
        headers,
        allow_not_found,
        perform_get=_perform_get,
        record_network_warning=_record_network_warning,
        sleep=time.sleep,
        retry_delay=_retry_delay_with_jitter,
        accepted_statuses=accepted_statuses,
    )


def discover_repositories(headers: Headers) -> list[RepoMetadata]:
    return _repositories_discover_repositories(
        headers,
        fetch_json=fetch_json,
        use_github_app_collection_token=_use_github_app_collection_token,
    )


_is_trackable_repo = _repositories_is_trackable_repo
_selection_state = _repositories_selection_state
_current_repository = _repositories_current_repository
_resolve_named_repos = _repositories_resolve_named_repos
_sort_auto_candidates = _repositories_sort_auto_candidates


def _build_auto_candidates(
    eligible: dict[str, RepoMetadata],
    excluded: set[str],
    selected_names: set[str],
    current_repository: str,
    include_private: bool,
    include_new: bool,
    auto_seeded_at: str,
) -> list[RepoMetadata]:
    return _repositories_build_auto_candidates(
        eligible,
        excluded,
        selected_names,
        current_repository,
        include_private,
        include_new,
        auto_seeded_at,
    )


def resolve_repositories(
    headers: Headers,
    config: dict[str, Any],
    manifest: dict[str, Any],
) -> tuple[list[str], dict[str, Any], dict[str, RepoMetadata]]:
    return _repositories_resolve_repositories(
        headers,
        config,
        manifest,
        discover_repositories=discover_repositories,
        use_github_app_collection_token=_use_github_app_collection_token,
        current_repository=_current_repository,
    )


def collect_views_clones(
    repo: str,
    headers: Headers,
    captured_at: str,
) -> list[dict[str, Any]]:
    return _endpoints_collect_views_clones(
        repo,
        headers,
        captured_at,
        fetch_json=fetch_json,
    )


def collect_referrers(
    repo: str,
    headers: Headers,
    captured_at: str,
) -> list[dict[str, Any]]:
    return _endpoints_collect_referrers(repo, headers, captured_at, fetch_json=fetch_json)


def collect_paths(
    repo: str,
    headers: Headers,
    captured_at: str,
) -> list[dict[str, Any]]:
    return _endpoints_collect_paths(repo, headers, captured_at, fetch_json=fetch_json)


def collect_repo_detail(repo: str, headers: Headers) -> RepoMetadata:
    return _endpoints_collect_repo_detail(repo, headers, fetch_json=fetch_json)


def collect_repo_community_profile(repo: str, headers: Headers) -> RepoMetadata:
    return _endpoints_collect_repo_community_profile(repo, headers, fetch_json=fetch_json)


def collect_release_context(
    repo: str,
    headers: Headers,
    captured_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return _endpoints_collect_release_context(
        repo,
        headers,
        captured_at,
        fetch_json=fetch_json,
    )


def collect_commit_history(
    repo: str,
    headers: Headers,
    captured_at: str,
    default_branch: str = "",
) -> list[dict[str, Any]]:
    return _endpoints_collect_commit_history(
        repo,
        headers,
        captured_at,
        default_branch=default_branch,
        fetch_json=fetch_json,
    )


def collect_languages(
    repo: str,
    headers: Headers,
    captured_at: str,
) -> list[dict[str, Any]]:
    return _endpoints_collect_languages(repo, headers, captured_at, fetch_json=fetch_json)


def collect_topics(
    repo: str,
    headers: Headers,
    captured_at: str,
) -> list[dict[str, Any]]:
    return _endpoints_collect_topics(repo, headers, captured_at, fetch_json=fetch_json)


def collect_issue_pr_snapshot(
    repo: str,
    headers: Headers,
    captured_at: str,
) -> list[dict[str, Any]]:
    return _endpoints_collect_issue_pr_snapshot(
        repo,
        headers,
        captured_at,
        fetch_json=fetch_json,
    )


def collect_code_frequency_weekly(
    repo: str,
    headers: Headers,
    captured_at: str,
) -> list[dict[str, Any]]:
    return _endpoints_collect_code_frequency_weekly(
        repo,
        headers,
        captured_at,
        fetch_json_with_status=fetch_json_with_status,
    )


def collect_contributor_activity_weekly(
    repo: str,
    headers: Headers,
    captured_at: str,
) -> list[dict[str, Any]]:
    return _endpoints_collect_contributor_activity_weekly(
        repo,
        headers,
        captured_at,
        fetch_json_with_status=fetch_json_with_status,
    )


_community_has_file = _endpoints_community_has_file
_community_health_percentage = _endpoints_community_health_percentage


def collect_repo_metrics(
    repo: str,
    repo_detail: RepoMetadata,
    community_profile: RepoMetadata,
    captured_at: str,
    *,
    source: str = "repo-detail",
) -> list[dict[str, Any]]:
    return _endpoints_collect_repo_metrics(
        repo,
        repo_detail,
        community_profile,
        captured_at,
        source=source,
    )


_fallback_repo_detail_warning = _endpoints_fallback_repo_detail_warning
_fallback_repo_community_warning = _endpoints_fallback_repo_community_warning


def main() -> None:
    _reset_runtime_state()
    config = load_config()
    run_collection(config, _collection_dependencies())


def _collection_dependencies() -> CollectionDependencies:
    return CollectionDependencies(
        get_headers=get_headers,
        validate_token=validate_token,
        read_manifest=read_manifest,
        resolve_repositories=resolve_repositories,
        write_manifest=write_manifest,
        collect_repo_detail=collect_repo_detail,
        collect_repo_community_profile=collect_repo_community_profile,
        collect_views_clones=collect_views_clones,
        collect_referrers=collect_referrers,
        collect_paths=collect_paths,
        collect_commit_history=collect_commit_history,
        collect_release_context=collect_release_context,
        collect_languages=collect_languages,
        collect_topics=collect_topics,
        collect_issue_pr_snapshot=collect_issue_pr_snapshot,
        collect_code_frequency_weekly=collect_code_frequency_weekly,
        collect_contributor_activity_weekly=collect_contributor_activity_weekly,
        collect_repo_metrics=collect_repo_metrics,
        append_csv=append_csv,
        collection_status_row=_collection_status_row,
        append_collection_status=_append_collection_status,
        has_nonzero_traffic=_has_nonzero_traffic,
        write_step_summary=_write_step_summary,
        repo_detail_warnings=_REPO_DETAIL_WARNINGS,
        repo_community_warnings=_REPO_COMMUNITY_WARNINGS,
        repo_context_warnings=_REPO_CONTEXT_WARNINGS,
        data_dir=DATA_DIR,
    )


if __name__ == "__main__":
    main()
