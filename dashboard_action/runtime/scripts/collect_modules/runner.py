"""Top-level collection orchestration."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from collect_modules.http import RepoUnavailableError, SecondaryRateLimitError
from collect_modules.types import Headers, RepoMetadata
from storage import (
    LOG_FIELDS,
    PATH_FIELDS,
    REFERRER_FIELDS,
    REPO_METRIC_FIELDS,
    SNAPSHOT_FIELDS,
)


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
    collect_repo_metrics: Callable[..., list[dict[str, Any]]]
    append_csv: Callable[[str, list[dict[str, Any]], list[str]], None]
    collection_status_row: Callable[..., dict[str, Any]]
    append_collection_status: Callable[[dict[str, Any]], None]
    has_nonzero_traffic: Callable[[list[dict[str, Any]]], bool]
    write_step_summary: Callable[..., None]
    repo_detail_warnings: list[str]
    repo_community_warnings: list[str]
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
    return {
        "traffic": vc_rows,
        "referrers": ref_rows,
        "paths": path_rows,
        "metrics": metric_rows,
    }


def _snapshot_rows(vc_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in row.items() if key in SNAPSHOT_FIELDS} for row in vc_rows]


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
        + f"{len(path_rows)} path(s), {len(metric_rows)} repo metric row(s)"
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
