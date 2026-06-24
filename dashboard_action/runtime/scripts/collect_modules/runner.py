"""Top-level collection orchestration."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypeAlias

import requests

from collect_modules.context_endpoints import RepositoryStatisticsStatus
from collect_modules.http import RepoUnavailableError, SecondaryRateLimitError
from collect_modules.types import Headers, RepoMetadata
from storage import (
    COLLECTION_ENDPOINT_FIELDS,
    LOG_FIELDS,
    PATH_FIELDS,
    REFERRER_FIELDS,
    REPO_CODE_FREQUENCY_WEEKLY_FIELDS,
    REPO_COMMIT_FIELDS,
    REPO_CONTRIBUTOR_ACTIVITY_WEEKLY_FIELDS,
    REPO_ISSUE_PR_SNAPSHOT_FIELDS,
    REPO_LANGUAGE_FIELDS,
    REPO_METRIC_FIELDS,
    REPO_RELEASE_ASSET_FIELDS,
    REPO_RELEASE_FIELDS,
    REPO_TOPIC_FIELDS,
    SCHEMA_VERSION,
    SNAPSHOT_FIELDS,
)

Rows: TypeAlias = list[dict[str, Any]]
_STATISTICS_ENDPOINTS = {"code-frequency", "contributor-activity"}


@dataclass(frozen=True)
class CollectionDependencies:
    """Facade-injected operations used by the collection runner."""

    get_headers: Callable[[], dict[str, str]]
    validate_token: Callable[[Headers], None]
    read_manifest: Callable[[str], dict[str, Any]]
    resolve_repositories: Callable[
        [Headers, dict[str, Any], dict[str, Any]],
        tuple[list[str], dict[str, Any], dict[str, RepoMetadata]],
    ]
    write_manifest: Callable[[dict[str, Any], str], None]
    collect_repo_detail: Callable[[str, Headers], RepoMetadata]
    collect_repo_community_profile: Callable[[str, Headers], RepoMetadata]
    collect_views_clones: Callable[[str, Headers, str], list[dict[str, Any]]]
    collect_referrers: Callable[[str, Headers, str], list[dict[str, Any]]]
    collect_paths: Callable[[str, Headers, str], list[dict[str, Any]]]
    collect_commit_history: Callable[[str, Headers, str, str], Rows]
    collect_release_context: Callable[[str, Headers, str], tuple[Rows, Rows]]
    collect_languages: Callable[[str, Headers, str], Rows]
    collect_topics: Callable[[str, Headers, str], Rows]
    collect_issue_pr_snapshot: Callable[[str, Headers, str], Rows]
    collect_code_frequency_weekly: Callable[[str, Headers, str], Rows]
    collect_contributor_activity_weekly: Callable[[str, Headers, str], Rows]
    collect_repo_metrics: Callable[..., list[dict[str, Any]]]
    append_csv: Callable[[str, list[dict[str, Any]], list[str]], None]
    collection_status_row: Callable[..., dict[str, Any]]
    append_collection_status: Callable[[dict[str, Any]], None]
    has_nonzero_traffic: Callable[[list[dict[str, Any]]], bool]
    write_step_summary: Callable[..., None]
    repo_detail_warnings: list[str]
    repo_community_warnings: list[str]
    repo_context_warnings: list[str]
    data_dir: str


@dataclass
class CollectionRun:
    """Mutable context for one collection run."""

    headers: Headers
    captured_at: str
    run_id: str
    repo_metadata: dict[str, RepoMetadata]
    errors: list[str]
    skipped_repos: list[str]
    status_rows: list[dict[str, Any]]


def run_collection(config: dict[str, Any], deps: CollectionDependencies) -> None:
    """Run collection for configured repositories."""
    headers = deps.get_headers()
    deps.validate_token(headers)
    manifest = deps.read_manifest(deps.data_dir)
    repos, manifest, repo_metadata = deps.resolve_repositories(headers, config, manifest)
    deps.write_manifest(manifest, deps.data_dir)

    run = CollectionRun(
        headers=headers,
        captured_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        run_id=os.environ.get("GITHUB_RUN_ID", ""),
        repo_metadata=repo_metadata,
        errors=[],
        skipped_repos=[],
        status_rows=[],
    )
    for repo in repos:
        _collect_repo(repo, run, deps)
    _finish_run(run, deps)


def _collect_repo(repo: str, run: CollectionRun, deps: CollectionDependencies) -> None:
    print(f"Collecting traffic for {repo}...")
    metric_source = "repo-detail"
    try:
        detail, metric_source = _repo_detail(repo, run, deps)
        community_profile = _community_profile(repo, run, deps)
        artifacts = _collect_artifacts(repo, run, deps, detail, community_profile, metric_source)
        _record_success(repo, run, deps, artifacts, metric_source)
    except SecondaryRateLimitError as exc:
        _handle_secondary_limit(repo, run, deps, exc, metric_source)
    except RepoUnavailableError as exc:
        _handle_unavailable_repo(repo, run, deps, exc, metric_source)
    except (requests.HTTPError, requests.RequestException) as exc:
        _handle_repo_error(repo, run, deps, exc, metric_source)
    else:
        deps.append_collection_status(run.status_rows[-1])


def _repo_detail(
    repo: str,
    run: CollectionRun,
    deps: CollectionDependencies,
) -> tuple[RepoMetadata, str]:
    try:
        return deps.collect_repo_detail(repo, run.headers), "repo-detail"
    except SecondaryRateLimitError:
        raise
    except (requests.HTTPError, requests.RequestException) as exc:
        warning = _fallback_repo_detail_warning(repo, exc)
        deps.repo_detail_warnings.append(warning)
        print(f"  Warning: {warning}")
        return run.repo_metadata.get(repo, {}), "discovery-fallback"


def _community_profile(
    repo: str,
    run: CollectionRun,
    deps: CollectionDependencies,
) -> RepoMetadata:
    try:
        return deps.collect_repo_community_profile(repo, run.headers)
    except SecondaryRateLimitError:
        raise
    except (requests.HTTPError, requests.RequestException) as exc:
        warning = _fallback_repo_community_warning(repo, exc)
        deps.repo_community_warnings.append(warning)
        print(f"  Warning: {warning}")
        return {}


def _collect_artifacts(
    repo: str,
    run: CollectionRun,
    deps: CollectionDependencies,
    detail: RepoMetadata,
    community_profile: RepoMetadata,
    metric_source: str,
) -> dict[str, list[dict[str, Any]]]:
    vc_rows = deps.collect_views_clones(repo, run.headers, run.captured_at)
    deps.append_csv(os.path.join(deps.data_dir, "traffic-log.csv"), vc_rows, LOG_FIELDS)
    deps.append_csv(
        os.path.join(deps.data_dir, "traffic-snapshots.csv"),
        _snapshot_rows(vc_rows),
        SNAPSHOT_FIELDS,
    )

    ref_rows = deps.collect_referrers(repo, run.headers, run.captured_at)
    deps.append_csv(
        os.path.join(deps.data_dir, "traffic-referrers.csv"),
        ref_rows,
        REFERRER_FIELDS,
    )
    path_rows = deps.collect_paths(repo, run.headers, run.captured_at)
    deps.append_csv(os.path.join(deps.data_dir, "traffic-paths.csv"), path_rows, PATH_FIELDS)

    metric_rows = deps.collect_repo_metrics(
        repo,
        detail or {},
        community_profile,
        run.captured_at,
        source=metric_source,
    )
    deps.append_csv(os.path.join(deps.data_dir, "repo-metrics.csv"), metric_rows, REPO_METRIC_FIELDS)
    context_rows = _collect_context_artifacts(repo, run, deps, detail or {})
    return {
        "traffic": vc_rows,
        "referrers": ref_rows,
        "paths": path_rows,
        "metrics": metric_rows,
        **context_rows,
    }


def _snapshot_rows(vc_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in row.items() if key in SNAPSHOT_FIELDS} for row in vc_rows]


def _collect_context_artifacts(
    repo: str,
    run: CollectionRun,
    deps: CollectionDependencies,
    detail: RepoMetadata,
) -> dict[str, Rows]:
    endpoint_rows: Rows = []
    commit_rows = _context_rows(
        repo,
        run,
        deps,
        "commits",
        "commits",
        lambda selected_repo, headers, captured_at: deps.collect_commit_history(
            selected_repo,
            headers,
            captured_at,
            str(detail.get("default_branch") or ""),
        ),
        endpoint_rows,
    )
    release_rows, release_asset_rows = _release_context_rows(repo, run, deps, endpoint_rows)
    language_rows = _context_rows(
        repo,
        run,
        deps,
        "languages",
        "languages",
        deps.collect_languages,
        endpoint_rows,
    )
    topic_rows = _context_rows(
        repo,
        run,
        deps,
        "topics",
        "topics",
        deps.collect_topics,
        endpoint_rows,
    )
    issue_pr_rows = _context_rows(
        repo,
        run,
        deps,
        "issue/pr snapshot",
        "issue-pr-snapshot",
        deps.collect_issue_pr_snapshot,
        endpoint_rows,
    )
    code_frequency_rows = _context_rows(
        repo,
        run,
        deps,
        "code frequency",
        "code-frequency",
        deps.collect_code_frequency_weekly,
        endpoint_rows,
    )
    contributor_activity_rows = _context_rows(
        repo,
        run,
        deps,
        "contributor activity",
        "contributor-activity",
        deps.collect_contributor_activity_weekly,
        endpoint_rows,
    )
    deps.append_csv(
        os.path.join(deps.data_dir, "repo-commits.csv"),
        commit_rows,
        REPO_COMMIT_FIELDS,
    )
    deps.append_csv(
        os.path.join(deps.data_dir, "repo-releases.csv"),
        release_rows,
        REPO_RELEASE_FIELDS,
    )
    deps.append_csv(
        os.path.join(deps.data_dir, "repo-release-assets.csv"),
        release_asset_rows,
        REPO_RELEASE_ASSET_FIELDS,
    )
    deps.append_csv(
        os.path.join(deps.data_dir, "repo-languages.csv"),
        language_rows,
        REPO_LANGUAGE_FIELDS,
    )
    deps.append_csv(os.path.join(deps.data_dir, "repo-topics.csv"), topic_rows, REPO_TOPIC_FIELDS)
    deps.append_csv(
        os.path.join(deps.data_dir, "repo-issue-pr-snapshots.csv"),
        issue_pr_rows,
        REPO_ISSUE_PR_SNAPSHOT_FIELDS,
    )
    deps.append_csv(
        os.path.join(deps.data_dir, "repo-code-frequency-weekly.csv"),
        code_frequency_rows,
        REPO_CODE_FREQUENCY_WEEKLY_FIELDS,
    )
    deps.append_csv(
        os.path.join(deps.data_dir, "repo-contributor-activity-weekly.csv"),
        contributor_activity_rows,
        REPO_CONTRIBUTOR_ACTIVITY_WEEKLY_FIELDS,
    )
    deps.append_csv(
        os.path.join(deps.data_dir, "collection-endpoints.csv"),
        endpoint_rows,
        COLLECTION_ENDPOINT_FIELDS,
    )
    return {
        "commits": commit_rows,
        "releases": release_rows,
        "release_assets": release_asset_rows,
        "languages": language_rows,
        "topics": topic_rows,
        "issue_pr_snapshots": issue_pr_rows,
        "code_frequency": code_frequency_rows,
        "contributor_activity": contributor_activity_rows,
    }


def _release_context_rows(
    repo: str,
    run: CollectionRun,
    deps: CollectionDependencies,
    endpoint_rows: Rows,
) -> tuple[Rows, Rows]:
    try:
        release_rows, asset_rows = deps.collect_release_context(repo, run.headers, run.captured_at)
        _record_endpoint_row(
            endpoint_rows,
            repo=repo,
            captured_at=run.captured_at,
            endpoint_key="releases",
            status="ok",
            rows_written=len(release_rows) + len(asset_rows),
        )
        return release_rows, asset_rows
    except SecondaryRateLimitError:
        raise
    except (requests.HTTPError, requests.RequestException) as exc:
        _record_context_warning(repo, "releases", deps, exc)
        _record_endpoint_error(
            endpoint_rows,
            repo=repo,
            captured_at=run.captured_at,
            endpoint_key="releases",
            exc=exc,
        )
        return [], []


def _context_rows(
    repo: str,
    run: CollectionRun,
    deps: CollectionDependencies,
    family: str,
    endpoint_key: str,
    collector: Callable[[str, Headers, str], Rows],
    endpoint_rows: Rows,
) -> Rows:
    try:
        rows = collector(repo, run.headers, run.captured_at)
        _record_endpoint_row(
            endpoint_rows,
            repo=repo,
            captured_at=run.captured_at,
            endpoint_key=endpoint_key,
            status="ok",
            rows_written=len(rows),
            cache_state="ready" if endpoint_key in _STATISTICS_ENDPOINTS else "",
        )
        return rows
    except SecondaryRateLimitError:
        raise
    except RepositoryStatisticsStatus as exc:
        _record_endpoint_row(
            endpoint_rows,
            repo=repo,
            captured_at=run.captured_at,
            endpoint_key=endpoint_key,
            status=exc.status,
            http_status=exc.http_status,
            rows_written=0,
            cache_state=exc.cache_state,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
        )
        print(f"  Info: {exc}")
        return []
    except (requests.HTTPError, requests.RequestException) as exc:
        _record_context_warning(repo, family, deps, exc)
        _record_endpoint_error(
            endpoint_rows,
            repo=repo,
            captured_at=run.captured_at,
            endpoint_key=endpoint_key,
            exc=exc,
        )
        return []


def _record_endpoint_error(
    endpoint_rows: Rows,
    *,
    repo: str,
    captured_at: str,
    endpoint_key: str,
    exc: Exception,
) -> None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    _record_endpoint_row(
        endpoint_rows,
        repo=repo,
        captured_at=captured_at,
        endpoint_key=endpoint_key,
        status="error",
        http_status=getattr(response, "status_code", ""),
        rows_written=0,
        cache_state="",
        rate_limit_remaining=headers.get("X-RateLimit-Remaining", ""),
        retry_after_seconds=headers.get("Retry-After", ""),
        error_type=exc.__class__.__name__,
        error_message=str(exc),
    )


def _record_endpoint_row(
    endpoint_rows: Rows,
    *,
    repo: str,
    captured_at: str,
    endpoint_key: str,
    status: str,
    http_status: Any = "",
    rows_written: int = 0,
    cache_state: str = "",
    rate_limit_remaining: Any = "",
    retry_after_seconds: Any = "",
    duration_ms: Any = "",
    error_type: str = "",
    error_message: str = "",
) -> None:
    endpoint_rows.append(
        {
            "repo": repo,
            "captured_at": captured_at,
            "endpoint_key": endpoint_key,
            "credential_class": "collection-token",
            "status": status,
            "http_status": http_status,
            "rows_written": rows_written,
            "cache_state": cache_state,
            "rate_limit_remaining": rate_limit_remaining,
            "retry_after_seconds": retry_after_seconds,
            "duration_ms": duration_ms,
            "error_type": error_type,
            "error_message": error_message,
            "schema_version": SCHEMA_VERSION,
        }
    )


def _record_success(
    repo: str,
    run: CollectionRun,
    deps: CollectionDependencies,
    artifacts: dict[str, list[dict[str, Any]]],
    metric_source: str,
) -> None:
    vc_rows = artifacts["traffic"]
    ref_rows = artifacts["referrers"]
    path_rows = artifacts["paths"]
    metric_rows = artifacts["metrics"]
    context_row_count = sum(
        len(artifacts[key])
        for key in (
            "releases",
            "commits",
            "release_assets",
            "languages",
            "topics",
            "issue_pr_snapshots",
            "code_frequency",
            "contributor_activity",
        )
    )
    run.status_rows.append(
        deps.collection_status_row(
            repo=repo,
            captured_at=run.captured_at,
            run_id=run.run_id,
            status="ok_with_data" if deps.has_nonzero_traffic(vc_rows) else "ok_zero_data",
            metric_source=metric_source,
            traffic_days=len(vc_rows),
            referrer_rows=len(ref_rows),
            path_rows=len(path_rows),
        )
    )
    print(
        f"  OK: {len(vc_rows)} day(s), {len(ref_rows)} referrer(s), "
        + f"{len(path_rows)} path(s), {len(metric_rows)} repo metric row(s), "
        + f"{context_row_count} context row(s)"
    )


def _handle_secondary_limit(
    repo: str,
    run: CollectionRun,
    deps: CollectionDependencies,
    exc: SecondaryRateLimitError,
    metric_source: str,
) -> None:
    run.errors.append(repo)
    _append_error_status(repo, run, deps, exc, metric_source, "error_secondary_rate_limit")
    print(f"  Error collecting {repo}: {exc}")
    print("  Stop rerunning this workflow until the reported retry window has passed.")
    deps.append_collection_status(run.status_rows[-1])
    deps.write_step_summary(
        "failed",
        errors=run.errors,
        secondary_limit=exc,
        skipped_repos=run.skipped_repos,
        status_rows=run.status_rows,
    )
    sys.exit(1)


def _handle_unavailable_repo(
    repo: str,
    run: CollectionRun,
    deps: CollectionDependencies,
    exc: RepoUnavailableError,
    metric_source: str,
) -> None:
    run.skipped_repos.append(repo)
    _append_error_status(repo, run, deps, exc, metric_source, "skipped_unavailable")
    deps.append_collection_status(run.status_rows[-1])
    print(f"  Skipping {repo}: {exc}")


def _handle_repo_error(
    repo: str,
    run: CollectionRun,
    deps: CollectionDependencies,
    exc: requests.RequestException,
    metric_source: str,
) -> None:
    print(f"  Error collecting {repo}: {exc}")
    run.errors.append(repo)
    _append_error_status(repo, run, deps, exc, metric_source, "error")
    deps.append_collection_status(run.status_rows[-1])


def _append_error_status(
    repo: str,
    run: CollectionRun,
    deps: CollectionDependencies,
    exc: Exception,
    metric_source: str,
    status: str,
) -> None:
    run.status_rows.append(
        deps.collection_status_row(
            repo=repo,
            captured_at=run.captured_at,
            run_id=run.run_id,
            status=status,
            metric_source=metric_source,
            traffic_days=0,
            referrer_rows=0,
            path_rows=0,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
        )
    )


def _finish_run(run: CollectionRun, deps: CollectionDependencies) -> None:
    if run.errors:
        deps.write_step_summary(
            "failed",
            errors=run.errors,
            skipped_repos=run.skipped_repos,
            status_rows=run.status_rows,
        )
        print(f"\nCollection finished with errors for: {', '.join(run.errors)}")
        sys.exit(1)

    if run.skipped_repos:
        deps.write_step_summary(
            "success-with-skips",
            skipped_repos=run.skipped_repos,
            status_rows=run.status_rows,
        )
        print(
            "Collection complete with unavailable repositories skipped: "
            + ", ".join(run.skipped_repos)
        )
        return

    deps.write_step_summary("success", status_rows=run.status_rows)
    print("Collection complete.")


def _fallback_repo_detail_warning(repo: str, exc: Exception) -> str:
    return (
        f"{repo}: repository detail request failed ({exc}); "
        + "traffic collection continued and repo metrics used discovery fallback."
    )


def _fallback_repo_community_warning(repo: str, exc: Exception) -> str:
    return (
        f"{repo}: community profile request failed ({exc}); "
        + "collection continued and community metrics were left blank."
    )


def _record_context_warning(
    repo: str,
    family: str,
    deps: CollectionDependencies,
    exc: Exception,
) -> None:
    warning = _fallback_repo_context_warning(repo, family, exc)
    deps.repo_context_warnings.append(warning)
    print(f"  Warning: {warning}")


def _fallback_repo_context_warning(repo: str, family: str, exc: Exception) -> str:
    return (
        f"{repo}: {family} request failed ({exc}); "
        + "collection continued and contextual rows were left blank."
    )
