"""Collect provenance helpers for publish/runtime epoch validation."""

from __future__ import annotations

import json
import re
import requests
import subprocess
from dataclasses import asdict
from pathlib import Path
from urllib.parse import quote

from .config import _env, _first_env
from .core import (
    COLLECT_PROVENANCE_PATH,
    INCIDENT_API_TIMEOUT_SECONDS,
    VERSION,
    ActionError,
    CollectProvenance,
    RuntimeConfig,
)

SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
PROVENANCE_SCHEMA_VERSION = 1
GITHUB_API_URL = "https://api.github.com"


def _git_output(args: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _commit_sha(value: str) -> str:
    normalized = value.strip().lower()
    return normalized if SHA_RE.fullmatch(normalized) else ""


def current_source_sha() -> str:
    explicit = _commit_sha(_env("GITHUB_SHA"))
    if explicit:
        return explicit
    value = _git_output(["git", "rev-parse", "HEAD"])
    return _commit_sha(value)


def current_action_sha() -> str:
    explicit = _commit_sha(_env("REPONOMICS_ACTION_SHA"))
    if explicit:
        return explicit
    ref_sha = _commit_sha(_env("REPONOMICS_ACTION_REF"))
    if ref_sha:
        return ref_sha
    action_path = _env("GITHUB_ACTION_PATH")
    if action_path:
        value = _git_output(["git", "rev-parse", "HEAD"], cwd=Path(action_path))
        action_path_sha = _commit_sha(value)
        if action_path_sha:
            return action_path_sha
    return _resolve_action_ref_sha(
        _env("REPONOMICS_ACTION_REPOSITORY"),
        _env("REPONOMICS_ACTION_REF"),
    )


def _resolve_action_ref_sha(action_repository: str, action_ref: str) -> str:
    if "/" not in action_repository or not action_ref:
        return ""
    owner_repo = action_repository.strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": "reponomics-dashboard-action-runtime",
    }
    token = _first_env("REPONOMICS_GITHUB_TOKEN", "GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for candidate in _action_ref_candidates(action_ref):
        url = f"{GITHUB_API_URL}/repos/{owner_repo}/commits/{quote(candidate, safe='')}"
        try:
            response = requests.get(url, headers=headers, timeout=INCIDENT_API_TIMEOUT_SECONDS)
        except requests.RequestException:
            return ""
        if response.status_code == 404:
            continue
        if response.status_code != 200:
            return ""
        try:
            payload = response.json()
        except ValueError:
            return ""
        if isinstance(payload, dict):
            resolved = _commit_sha(str(payload.get("sha") or ""))
            if resolved:
                return resolved
    return ""


def _action_ref_candidates(action_ref: str) -> list[str]:
    raw = action_ref.strip()
    candidates = [raw]
    for prefix in ("refs/heads/", "refs/tags/"):
        if raw.startswith(prefix):
            candidates.append(raw.removeprefix(prefix))
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def write_collect_provenance(config: RuntimeConfig) -> CollectProvenance:
    if not _env("GITHUB_REPOSITORY") or not _env("GITHUB_RUN_ID"):
        raise ActionError("Collect provenance requires GitHub Actions repository and run context.")
    action_sha = current_action_sha()
    if not action_sha:
        raise ActionError(
            "Could not determine the resolved Reponomics action commit SHA for collect provenance."
        )
    source_sha = current_source_sha()
    if not source_sha:
        raise ActionError("Could not determine the repository source SHA for collect provenance.")
    provenance = CollectProvenance(
        schema_version=PROVENANCE_SCHEMA_VERSION,
        source_repository=_env("GITHUB_REPOSITORY"),
        source_sha=source_sha,
        workflow_run_id=_env("GITHUB_RUN_ID"),
        workflow_run_attempt=_env("GITHUB_RUN_ATTEMPT"),
        action_repository=config.action_repository,
        action_ref=config.action_ref,
        action_sha=action_sha,
        runtime_version=VERSION,
        privacy_mode=config.privacy_mode,
        retention_days=str(config.retention_days),
        publish_pages=str(config.publish_pages_requested).lower(),
        generate_readme=str(config.generate_readme).lower(),
    )
    validate_collect_provenance(provenance, config, require_current_runtime=False)
    COLLECT_PROVENANCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    COLLECT_PROVENANCE_PATH.write_text(
        json.dumps(asdict(provenance), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote collect provenance to {COLLECT_PROVENANCE_PATH.as_posix()}.")
    return provenance


def should_write_collect_provenance() -> bool:
    return bool(
        _env("GITHUB_REPOSITORY")
        and _env("GITHUB_RUN_ID")
        and (_env("GITHUB_ACTION_PATH") or _env("REPONOMICS_ACTION_SHA"))
    )


def read_collect_provenance(path: Path = COLLECT_PROVENANCE_PATH) -> CollectProvenance:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ActionError(f"Could not read collect provenance from {path}.") from exc
    if not isinstance(payload, dict):
        raise ActionError("Collect provenance payload must be a JSON object.")
    try:
        raw_schema_version = payload.get("schema_version")
        if not isinstance(raw_schema_version, str | int):
            raise ValueError("schema_version must be a string or integer")
        provenance = CollectProvenance(
            schema_version=int(raw_schema_version),
            source_repository=str(payload.get("source_repository") or ""),
            source_sha=str(payload.get("source_sha") or ""),
            workflow_run_id=str(payload.get("workflow_run_id") or ""),
            workflow_run_attempt=str(payload.get("workflow_run_attempt") or ""),
            action_repository=str(payload.get("action_repository") or ""),
            action_ref=str(payload.get("action_ref") or ""),
            action_sha=str(payload.get("action_sha") or ""),
            runtime_version=str(payload.get("runtime_version") or ""),
            privacy_mode=str(payload.get("privacy_mode") or ""),
            retention_days=str(payload.get("retention_days") or ""),
            publish_pages=str(payload.get("publish_pages") or ""),
            generate_readme=str(payload.get("generate_readme") or ""),
        )
    except (TypeError, ValueError) as exc:
        raise ActionError("Collect provenance payload is malformed.") from exc
    return provenance


def validate_collect_provenance(
    provenance: CollectProvenance,
    config: RuntimeConfig,
    *,
    require_current_runtime: bool,
) -> None:
    if provenance.schema_version != PROVENANCE_SCHEMA_VERSION:
        raise ActionError("Collect provenance schema version is unsupported.")
    if provenance.source_repository != _env("GITHUB_REPOSITORY"):
        raise ActionError("Collect provenance belongs to another repository.")
    if not re.fullmatch(r"[1-9]\d*", provenance.workflow_run_id):
        raise ActionError("Collect provenance workflow run ID is invalid.")
    for label, value in {
        "source_sha": provenance.source_sha,
        "action_sha": provenance.action_sha,
    }.items():
        if not _commit_sha(value):
            raise ActionError(f"Collect provenance {label} is not a commit SHA.")
    if provenance.privacy_mode not in {"strong", "casual", "plain"}:
        raise ActionError("Collect provenance privacy mode is invalid.")
    try:
        retention_days = int(provenance.retention_days)
    except ValueError as exc:
        raise ActionError("Collect provenance retention days is not an integer.") from exc
    if retention_days < 1 or retention_days > 90:
        raise ActionError("Collect provenance retention days is out of range.")
    for label, value in {
        "publish_pages": provenance.publish_pages,
        "generate_readme": provenance.generate_readme,
    }.items():
        if value not in {"true", "false"}:
            raise ActionError(f"Collect provenance {label} must be true or false.")
    if provenance.action_repository != config.action_repository:
        raise ActionError("Collect provenance action repository differs from this workflow.")
    if require_current_runtime:
        action_sha = current_action_sha()
        if not action_sha:
            raise ActionError("Could not determine current Reponomics action commit SHA.")
        if action_sha != provenance.action_sha:
            raise ActionError(
                "Collect provenance was produced by action commit "
                + f"{provenance.action_sha}, but this publish run is using {action_sha}. "
                + "Run collect again before republishing with this action version."
            )
        if provenance.runtime_version != VERSION:
            raise ActionError(
                "Collect provenance was produced by runtime version "
                + f"{provenance.runtime_version}, but this publish run is using {VERSION}. "
                + "Run collect again before republishing with this action version."
            )
