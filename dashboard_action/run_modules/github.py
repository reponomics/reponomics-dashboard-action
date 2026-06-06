"""GitHub API helpers for incident reset and artifact retention cleanup."""

from __future__ import annotations

import time
from typing import Any

import requests

from .config import _env
from .core import (
    INCIDENT_API_MAX_RETRIES,
    INCIDENT_API_TIMEOUT_SECONDS,
    ActionError,
    DashboardDataArtifactRef,
)

import collect as collect_mod  # noqa: E402


def _github_api_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": "reponomics-dashboard-action-runtime",
    }


def _github_delete(url: str, headers: dict[str, str]) -> int:
    last_status = 0
    for attempt in range(1, INCIDENT_API_MAX_RETRIES + 1):
        response = _delete_once_or_retry_later(url, headers, attempt)
        if response is None:
            continue
        last_status = response.status_code
        if response.status_code in {204, 404}:
            return response.status_code
        if _sleep_before_delete_retry(response, url, attempt):
            continue
        _raise_delete_failure(url, response)
    raise ActionError(f"GitHub API delete failed after retries for {url} (last status {last_status}).")


def _delete_once_or_retry_later(
    url: str,
    headers: dict[str, str],
    attempt: int,
) -> requests.Response | None:
    try:
        return requests.delete(url, headers=headers, timeout=INCIDENT_API_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        if attempt < INCIDENT_API_MAX_RETRIES:
            wait = collect_mod._retry_delay_with_jitter(attempt)
            print(
                "GitHub API delete network error for "
                + f"{url}: {exc}. retrying in {wait:.2f}s..."
            )
            time.sleep(wait)
            return None
        raise ActionError(f"GitHub API delete failed for {url}: {exc}") from exc


def _sleep_before_delete_retry(response: requests.Response, url: str, attempt: int) -> bool:
    if attempt >= INCIDENT_API_MAX_RETRIES:
        return False
    if collect_mod._is_secondary_rate_limit(response):
        retry_after_seconds, retry_at_utc, source = collect_mod._secondary_retry_window(response)
        wait: float = max(1, retry_after_seconds)
        print(
            "GitHub secondary rate limit while deleting "
            + f"{url}; retry at {retry_at_utc.strftime('%Y-%m-%d %H:%M:%S UTC')} "
            + f"(source: {source}, sleeping {wait}s)."
        )
        time.sleep(wait)
        return True
    if collect_mod._is_retryable_throttle(response) or response.status_code >= 500:
        wait = collect_mod._retry_delay_with_jitter(attempt)
        print(
            f"GitHub API delete throttle/server error {response.status_code} "
            + f"for {url}; retrying in {wait:.2f}s..."
        )
        time.sleep(wait)
        return True
    return False


def _raise_delete_failure(url: str, response: requests.Response) -> None:
    response_text = (getattr(response, "text", "") or "").strip().replace("\n", " ")
    if len(response_text) > 240:
        response_text = response_text[:240] + "..."
    raise ActionError(
        f"GitHub API delete failed ({response.status_code}) for {url}: "
        + (response_text or "no response body")
    )


def _github_fetch_json(url: str, headers: dict[str, str]) -> Any:
    try:
        return collect_mod.fetch_json(url, headers)
    except collect_mod.SecondaryRateLimitError as exc:
        raise ActionError(str(exc)) from exc
    except requests.HTTPError as exc:
        response = getattr(exc, "response", None)
        status = response.status_code if response is not None else "unknown"
        raise ActionError(f"GitHub API request failed for {url} with status {status}.") from exc
    except requests.RequestException as exc:
        raise ActionError(f"GitHub API request failed for {url}: {exc}") from exc


def _github_repository() -> tuple[str, str]:
    repository = _env("GITHUB_REPOSITORY")
    if "/" not in repository:
        raise ActionError("GitHub artifact maintenance requires GITHUB_REPOSITORY in owner/repo format.")
    owner, repo = repository.split("/", 1)
    if not owner or not repo:
        raise ActionError("GitHub artifact maintenance requires GITHUB_REPOSITORY in owner/repo format.")
    return owner, repo


def _github_run_id() -> int:
    raw = _env("GITHUB_RUN_ID")
    if not raw:
        raise ActionError("GitHub artifact maintenance requires GITHUB_RUN_ID.")
    try:
        return int(raw)
    except ValueError as exc:
        raise ActionError(f"GitHub artifact maintenance received invalid GITHUB_RUN_ID: {raw!r}.") from exc


def _current_workflow_id(owner: str, repo: str, run_id: int, headers: dict[str, str]) -> int:
    run_payload = _github_fetch_json(
        f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}",
        headers,
    )
    workflow_id = run_payload.get("workflow_id") if isinstance(run_payload, dict) else None
    if not isinstance(workflow_id, int):
        raise ActionError("incident-reset could not determine workflow_id for the current run.")
    return workflow_id


def _list_workflow_run_ids(
    owner: str,
    repo: str,
    workflow_id: int,
    *,
    current_run_id: int,
    headers: dict[str, str],
) -> list[int]:
    run_ids: list[int] = []
    for workflow_runs in _workflow_run_pages(owner, repo, workflow_id, headers):
        for row in workflow_runs:
            if not isinstance(row, dict):
                continue
            run_id = row.get("id")
            if isinstance(run_id, int) and run_id != current_run_id:
                run_ids.append(run_id)
    return run_ids


def _workflow_run_pages(
    owner: str,
    repo: str,
    workflow_id: int,
    headers: dict[str, str],
) -> list[list[Any]]:
    pages: list[list[Any]] = []
    page = 1
    while True:
        payload = _github_fetch_json(
            f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs"
            + f"?per_page=100&page={page}",
            headers,
        )
        if not isinstance(payload, dict):
            raise ActionError("incident-reset received an unexpected workflow-runs payload.")
        workflow_runs = payload.get("workflow_runs")
        if not isinstance(workflow_runs, list):
            raise ActionError("incident-reset received an invalid workflow-runs list payload.")
        if not workflow_runs:
            break
        pages.append(workflow_runs)
        if len(workflow_runs) < 100:
            break
        page += 1
    return pages


def _list_old_dashboard_data_artifacts(
    owner: str,
    repo: str,
    *,
    current_run_id: int,
    headers: dict[str, str],
) -> list[DashboardDataArtifactRef]:
    artifact_refs: list[DashboardDataArtifactRef] = []
    for artifacts in _dashboard_data_artifact_pages(owner, repo, headers):
        for artifact in artifacts:
            artifact_ref = _artifact_ref(artifact, current_run_id=current_run_id)
            if artifact_ref is not None:
                artifact_refs.append(artifact_ref)
    return artifact_refs


def _dashboard_data_artifact_pages(
    owner: str,
    repo: str,
    headers: dict[str, str],
) -> list[list[Any]]:
    pages: list[list[Any]] = []
    page = 1
    while True:
        payload = _github_fetch_json(
            f"https://api.github.com/repos/{owner}/{repo}/actions/artifacts"
            + f"?name=dashboard-data&per_page=100&page={page}",
            headers,
        )
        if not isinstance(payload, dict):
            raise ActionError("GitHub artifact maintenance received an unexpected artifact payload.")
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list):
            raise ActionError("GitHub artifact maintenance received an invalid artifacts list payload.")
        if not artifacts:
            break
        pages.append(artifacts)
        if len(artifacts) < 100:
            break
        page += 1
    return pages


def _artifact_ref(
    artifact: object,
    *,
    current_run_id: int,
) -> DashboardDataArtifactRef | None:
    if not isinstance(artifact, dict):
        return None
    artifact_id = artifact.get("id")
    workflow_run = artifact.get("workflow_run")
    artifact_run_id = workflow_run.get("id") if isinstance(workflow_run, dict) else None
    created_at = artifact.get("created_at")
    if not isinstance(artifact_id, int) or artifact_run_id == current_run_id:
        return None
    return DashboardDataArtifactRef(
        artifact_id=artifact_id,
        workflow_run_id=artifact_run_id if isinstance(artifact_run_id, int) else None,
        created_at=created_at if isinstance(created_at, str) else "",
    )

