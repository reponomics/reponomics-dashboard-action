"""Shared runtime constants and data models."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


VERSION = "0.20.3"  # x-release-please-version
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "runtime" / "scripts"
MIN_SECRET_LENGTH = 40
MIN_MASK_LENGTH = 3
INCIDENT_CONFIRM_MODE = "INCIDENT_RESET_CONFIRMED"
INCIDENT_CONFIRM_PURGE = "PURGE_OLD_HISTORY_CONFIRMED"
INCIDENT_CONFIRM_IRREVERSIBLE = "IRREVERSIBLE_ACTION_CONFIRMED"
INCIDENT_API_TIMEOUT_SECONDS = 20
INCIDENT_API_MAX_RETRIES = 6
COLLECT_ROLLBACK_ARTIFACTS = 2
MANAGED_DOCS_NAMESPACE = Path("docs") / "reponomics"
MANAGED_DOCS_BUNDLE_DIR = ROOT / "runtime" / "managed_docs"
MANAGED_DOCS_README_LINK_ENV = "REPONOMICS_MANAGED_DOCS_README_LINK"
MANAGED_DOCS_DASHBOARD_LINK_ENV = "REPONOMICS_MANAGED_DOCS_DASHBOARD_LINK"
DOCS_SYNC_STATE_ENV = "REPONOMICS_DOCS_SYNC_STATE"
DOCS_ACTION_VERSION_ENV = "REPONOMICS_DOCS_ACTION_VERSION"
DOCS_UPDATED_AT_ENV = "REPONOMICS_DOCS_UPDATED_AT"
DOCS_STATE_STALE = "stale"

VALID_MODES = {"collect", "publish", "rotate-key", "incident-reset", "docs-sync"}
VALID_PRIVACY_MODES = {"strong", "casual", "plain"}

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


class ActionError(RuntimeError):
    """Raised for user-facing action failures."""


@dataclass(frozen=True)
class RuntimeConfig:
    mode: str
    collection_token: str
    use_github_app: bool
    github_token: str
    dashboard_secret: str
    dashboard_next_secret: str
    privacy_mode: str
    repo_is_public: bool
    config_path: Path
    data_dir: Path
    retention_days: int
    artifact_run_id: str
    publish_pages_requested: bool
    generate_readme: bool
    allow_docs_sync: bool
    pages_index_path: Path
    readme_path: Path
    incident_confirm_mode: str
    incident_confirm_purge: str
    incident_confirm_irreversible: str
    action_ref: str
    action_repository: str

    @property
    def resolved_artifact_mode(self) -> str:
        return "plain" if self.privacy_mode == "plain" else "encrypted"

    @property
    def publish_pages(self) -> bool:
        return self.publish_pages_requested and self.privacy_mode != "plain"


@dataclass(frozen=True)
class IncidentPurgeResult:
    candidate_artifacts: int
    candidate_runs: int
    deleted_runs: int
    deleted_fallback_artifacts: int


@dataclass(frozen=True)
class ActiveRetentionCleanupResult:
    prior_artifacts: int
    retained_prior_artifacts: int
    delete_candidates: int
    deleted_artifacts: int


@dataclass(frozen=True)
class DashboardDataArtifactRef:
    artifact_id: int
    workflow_run_id: int | None
    created_at: str = ""
