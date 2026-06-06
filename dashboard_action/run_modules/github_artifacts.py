"""GitHub artifact and workflow-run maintenance operations."""

from __future__ import annotations

from .core import (
    COLLECT_ROLLBACK_ARTIFACTS,
    ActiveRetentionCleanupResult,
    DashboardDataArtifactRef,
    IncidentPurgeResult,
    RuntimeConfig,
)
from .github import (
    _github_api_headers,
    _github_delete,
    _github_repository,
    _github_run_id,
    _list_old_dashboard_data_artifacts,
)


def _purge_workflow_history(config: RuntimeConfig) -> IncidentPurgeResult:
    owner, repo = _github_repository()
    current_run_id = _github_run_id()
    headers = _github_api_headers(config.github_token)
    artifact_refs = _list_old_dashboard_data_artifacts(
        owner,
        repo,
        current_run_id=current_run_id,
        headers=headers,
    )
    old_run_ids = sorted(
        {
            artifact.workflow_run_id
            for artifact in artifact_refs
            if artifact.workflow_run_id is not None
        }
    )
    deleted_runs = _delete_workflow_runs(owner, repo, old_run_ids, headers)
    deleted_fallback_artifacts = _delete_fallback_artifacts(owner, repo, artifact_refs, headers)
    return IncidentPurgeResult(
        candidate_artifacts=len(artifact_refs),
        candidate_runs=len(old_run_ids),
        deleted_runs=deleted_runs,
        deleted_fallback_artifacts=deleted_fallback_artifacts,
    )


def _delete_workflow_runs(
    owner: str,
    repo: str,
    run_ids: list[int],
    headers: dict[str, str],
) -> int:
    deleted_runs = 0
    for run_id in run_ids:
        status = _github_delete(
            f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}",
            headers,
        )
        if status == 204:
            deleted_runs += 1
    return deleted_runs


def _delete_fallback_artifacts(
    owner: str,
    repo: str,
    artifact_refs: list[DashboardDataArtifactRef],
    headers: dict[str, str],
) -> int:
    deleted_fallback_artifacts = 0
    fallback_artifact_ids = [
        artifact.artifact_id
        for artifact in artifact_refs
        if artifact.workflow_run_id is None
    ]
    for artifact_id in fallback_artifact_ids:
        status = _github_delete(
            f"https://api.github.com/repos/{owner}/{repo}/actions/artifacts/{artifact_id}",
            headers,
        )
        if status == 204:
            deleted_fallback_artifacts += 1
    return deleted_fallback_artifacts


def _artifact_sort_key(artifact: DashboardDataArtifactRef) -> tuple[str, int]:
    return (artifact.created_at, artifact.artifact_id)


def _cleanup_superseded_collect_artifacts(config: RuntimeConfig) -> ActiveRetentionCleanupResult:
    owner, repo = _github_repository()
    current_run_id = _github_run_id()
    headers = _github_api_headers(config.github_token)
    artifact_refs = _list_old_dashboard_data_artifacts(
        owner,
        repo,
        current_run_id=current_run_id,
        headers=headers,
    )
    newest_first = sorted(artifact_refs, key=_artifact_sort_key, reverse=True)
    retained = newest_first[:COLLECT_ROLLBACK_ARTIFACTS]
    delete_candidates = newest_first[COLLECT_ROLLBACK_ARTIFACTS:]
    deleted_artifacts = _delete_one_superseded_artifact(owner, repo, delete_candidates, headers)
    return ActiveRetentionCleanupResult(
        prior_artifacts=len(artifact_refs),
        retained_prior_artifacts=len(retained),
        delete_candidates=len(delete_candidates),
        deleted_artifacts=deleted_artifacts,
    )


def _delete_one_superseded_artifact(
    owner: str,
    repo: str,
    delete_candidates: list[DashboardDataArtifactRef],
    headers: dict[str, str],
) -> int:
    if not delete_candidates:
        return 0
    artifact = delete_candidates[0]
    print(f"Deleting superseded dashboard-data artifact {artifact.artifact_id}.")
    status = _github_delete(
        f"https://api.github.com/repos/{owner}/{repo}/actions/artifacts/{artifact.artifact_id}",
        headers,
    )
    return 1 if status == 204 else 0
