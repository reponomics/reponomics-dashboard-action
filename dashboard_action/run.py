"""Orchestrate the bundled Reponomics runtime for GitHub Actions."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests
import yaml


VERSION = "0.18.0"  # x-release-please-version
ROOT = Path(__file__).resolve().parent
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

import collect as collect_mod  # noqa: E402
import bootstrap  # noqa: E402
import crypto_artifact  # noqa: E402
import load_data  # noqa: E402
import lineage  # noqa: E402
import managed_docs  # noqa: E402
import merge  # noqa: E402
import render_dashboard  # noqa: E402
import render_readme  # noqa: E402
import repo_config  # noqa: E402
import storage  # noqa: E402
import version_status  # noqa: E402


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


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _first_env(*names: str) -> str:
    for name in names:
        value = _env(name)
        if value:
            return value
    return ""


def _parse_bool(raw: str, *, name: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ActionError(f"{name} must be true or false, got {raw!r}.")


def _choice(value: str, choices: set[str], *, name: str) -> str:
    normalized = value.strip().lower()
    if normalized not in choices:
        allowed = ", ".join(sorted(choices))
        raise ActionError(f"{name} must be one of: {allowed}.")
    return normalized


def _normalize_privacy_mode(value: str, *, repo_is_public: bool) -> str:
    normalized = value.strip().lower()
    if normalized == "encrypted":
        return "strong"
    if normalized == "auto":
        return "strong" if repo_is_public else "plain"
    return _choice(normalized, VALID_PRIVACY_MODES, name="privacy-mode")


def _parse_retention_days(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ActionError(f"retention-days must be an integer, got {raw!r}.") from exc
    if value < 1 or value > 90:
        raise ActionError("retention-days must be between 1 and 90.")
    return value


def _validate_artifact_run_id(raw: str) -> str:
    if not raw:
        return ""
    if not re.fullmatch(r"[1-9]\d*", raw):
        raise ActionError(f"artifact-run-id must be a positive integer, got {raw!r}.")
    return raw


def _config_allow_docs_sync(config_path: Path) -> bool | None:
    if not config_path.exists():
        return None
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ActionError(f"Could not read allow_docs_sync from {config_path}.") from exc
    if not isinstance(payload, dict) or "allow_docs_sync" not in payload:
        return None
    value = payload["allow_docs_sync"]
    if isinstance(value, bool):
        return value
    raise ActionError("allow_docs_sync in config.yaml must be a YAML boolean.")


def _allow_docs_sync_from_env(config_path: Path) -> bool:
    raw = _env("REPONOMICS_ALLOW_DOCS_SYNC")
    if raw:
        return _parse_bool(raw, name="allow-docs-sync")
    configured = _config_allow_docs_sync(config_path)
    if configured is not None:
        return configured
    return True


def _repo_is_public() -> bool:
    value = _env("GITHUB_EVENT_REPOSITORY_PRIVATE")
    if value:
        normalized = value.lower()
        if normalized == "true":
            return False
        if normalized == "false":
            return True
        raise ActionError(
            "Could not determine repository visibility: "
            + f"GITHUB_EVENT_REPOSITORY_PRIVATE={value!r} is not a boolean."
        )
    event_path = _env("GITHUB_EVENT_PATH")
    if event_path:
        try:
            import json

            payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
            private = payload.get("repository", {}).get("private")
            if isinstance(private, bool):
                return not private
        except (OSError, ValueError):
            raise ActionError(
                "Could not determine repository visibility from GITHUB_EVENT_PATH."
            ) from None
        raise ActionError(
            "Could not determine repository visibility: "
            + "repository.private is missing from the event payload."
        )
    raise ActionError(
        "Could not determine repository visibility: missing GitHub event context."
    )


def load_config_from_env() -> RuntimeConfig:
    mode = _choice(_env("REPONOMICS_MODE", "collect"), VALID_MODES, name="mode")
    repo_is_public = _repo_is_public()
    privacy_mode = _normalize_privacy_mode(
        _first_env("REPONOMICS_PRIVACY_MODE", "REPONOMICS_ARTIFACT_SECURITY_MODE") or "strong",
        repo_is_public=repo_is_public,
    )
    config_path = Path(_env("REPONOMICS_CONFIG_PATH", "config.yaml"))
    return RuntimeConfig(
        mode=mode,
        collection_token=_first_env(
            "REPONOMICS_COLLECTION_TOKEN",
            "COLLECTION_TOKEN",
            "REPONOMICS_GITHUB_TOKEN",
            "GH_TOKEN",
        ),
        use_github_app=_parse_bool(
            _env("REPONOMICS_USE_GITHUB_APP", "false"),
            name="use-github-app",
        ),
        github_token=_first_env("REPONOMICS_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"),
        dashboard_secret=_first_env("REPONOMICS_DASHBOARD_SECRET", "DASHBOARD_SECRET_DO_NOT_REPLACE"),
        dashboard_next_secret=_first_env(
            "REPONOMICS_DASHBOARD_NEXT_SECRET",
            "DASHBOARD_NEXT_SECRET",
        ),
        privacy_mode=privacy_mode,
        repo_is_public=repo_is_public,
        config_path=config_path,
        data_dir=Path("data"),
        retention_days=_parse_retention_days(_env("REPONOMICS_RETENTION_DAYS", "90")),
        artifact_run_id=_validate_artifact_run_id(_env("REPONOMICS_ARTIFACT_RUN_ID")),
        publish_pages_requested=_parse_bool(
            _env("REPONOMICS_PUBLISH_PAGES", "true"),
            name="publish-pages",
        ),
        generate_readme=_parse_bool(_env("REPONOMICS_GENERATE_README", "false"), name="generate-readme"),
        allow_docs_sync=_allow_docs_sync_from_env(config_path),
        pages_index_path=Path("docs/index.html"),
        readme_path=Path(_env("REPONOMICS_README_PATH", "README.md")),
        incident_confirm_mode=_env("REPONOMICS_INCIDENT_CONFIRM_MODE"),
        incident_confirm_purge=_env("REPONOMICS_INCIDENT_CONFIRM_PURGE"),
        incident_confirm_irreversible=_env("REPONOMICS_INCIDENT_CONFIRM_IRREVERSIBLE"),
        action_ref=_env("REPONOMICS_ACTION_REF"),
        action_repository=_env("REPONOMICS_ACTION_REPOSITORY"),
    )


def validate_config(config: RuntimeConfig) -> None:
    if config.mode == "collect" and not config.collection_token:
        raise ActionError("collection-token, COLLECTION_TOKEN, or GH_TOKEN is required for collect mode.")
    if config.mode == "collect" and not config.github_token:
        raise ActionError("github-token, GITHUB_TOKEN, or GH_TOKEN is required for collect mode.")
    if config.repo_is_public and config.privacy_mode == "plain":
        raise ActionError("privacy-mode plain is only supported for private repositories.")
    if config.repo_is_public and config.generate_readme:
        raise ActionError("generate-readme is only supported for private repositories.")
    if config.mode in {"collect", "publish"} and config.privacy_mode in {"strong", "casual"}:
        _validate_secret(
            config.dashboard_secret,
            "dashboard-secret or DASHBOARD_SECRET_DO_NOT_REPLACE",
            allow_weak=config.privacy_mode == "casual",
        )
    if config.mode == "rotate-key":
        if config.privacy_mode == "plain":
            raise ActionError("rotate-key requires strong or casual privacy mode.")
        _validate_secret(
            config.dashboard_secret,
            "dashboard-secret or DASHBOARD_SECRET_DO_NOT_REPLACE",
            allow_weak=True,
        )
        _validate_secret(
            config.dashboard_next_secret,
            "dashboard-next-secret or DASHBOARD_NEXT_SECRET",
            allow_weak=config.privacy_mode == "casual",
        )
    if config.mode == "incident-reset":
        if config.privacy_mode == "plain":
            raise ActionError("incident-reset requires strong or casual privacy mode.")
        _validate_secret(
            config.dashboard_secret,
            "dashboard-secret or DASHBOARD_SECRET_DO_NOT_REPLACE",
            allow_weak=True,
        )
        _validate_secret(
            config.dashboard_next_secret,
            "dashboard-next-secret or DASHBOARD_NEXT_SECRET",
            allow_weak=config.privacy_mode == "casual",
        )
        if not config.github_token:
            raise ActionError("github-token, GITHUB_TOKEN, or GH_TOKEN is required for incident-reset mode.")
        _validate_incident_confirmations(config)


def validate_collect_cleanup_config(config: RuntimeConfig) -> None:
    if config.mode != "collect":
        raise ActionError("collect-retention-cleanup-only requires collect mode.")
    if not config.github_token:
        raise ActionError("github-token, GITHUB_TOKEN, or GH_TOKEN is required for collect artifact cleanup.")


def _validate_secret(value: str, label: str, *, allow_weak: bool) -> None:
    if not value:
        raise ActionError(f"{label} is required for the selected encrypted mode.")
    if len(value) < MIN_SECRET_LENGTH and not allow_weak:
        raise ActionError(
            f"{label} is below the Reponomics dashboard secret entropy policy. "
            + "Use a generated random secret, or set allow-weak-dashboard-secret "
            + "to true if you explicitly accept the disclosure and brute-force risk."
        )


def _validate_incident_confirmations(config: RuntimeConfig) -> None:
    if config.incident_confirm_mode != INCIDENT_CONFIRM_MODE:
        raise ActionError(
            "incident-confirm-mode must be set to "
            + f"{INCIDENT_CONFIRM_MODE!r} for incident-reset mode."
        )
    if config.incident_confirm_purge != INCIDENT_CONFIRM_PURGE:
        raise ActionError(
            "incident-confirm-purge must be set to "
            + f"{INCIDENT_CONFIRM_PURGE!r} for incident-reset mode."
        )
    if config.incident_confirm_irreversible != INCIDENT_CONFIRM_IRREVERSIBLE:
        raise ActionError(
            "incident-confirm-irreversible must be set to "
            + f"{INCIDENT_CONFIRM_IRREVERSIBLE!r} for incident-reset mode."
        )


def _mask_secret(value: str) -> None:
    def escape_workflow_data(raw: str) -> str:
        return raw.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")

    for line in value.splitlines():
        if len(line) >= MIN_MASK_LENGTH:
            # Emit the workflow command through fd-level stdout writes to avoid
            # log APIs that static analysis treats as clear-text secret logging.
            os.write(1, f"::add-mask::{escape_workflow_data(line)}\n".encode("utf-8"))


def _mask_config_secrets(config: RuntimeConfig) -> None:
    _mask_secret(config.collection_token)
    _mask_secret(config.github_token)
    _mask_secret(config.dashboard_secret)
    _mask_secret(config.dashboard_next_secret)


def _patch_runtime_paths(config: RuntimeConfig) -> None:
    data_dir = config.data_dir.as_posix()
    storage.DATA_DIR = data_dir
    storage.RETENTION_DAYS = config.retention_days
    bootstrap.DATA_DIR = data_dir
    collect_mod.DATA_DIR = data_dir
    collect_mod.CONFIG_PATH = config.config_path.as_posix()
    merge.DATA_DIR = data_dir
    merge.RETENTION_DAYS = config.retention_days
    repo_config.CONFIG_PATH = config.config_path.as_posix()
    def load_config(config_path: str = config.config_path.as_posix()) -> dict[str, Any]:
        return repo_config.load_repo_config(config_path)

    load_data.load_repo_config = load_config

    assets_dir = config.pages_index_path.parent / "assets"
    readme_parent = config.readme_path.parent
    display_assets = Path(os.path.relpath(assets_dir, readme_parent))

    render_dashboard.PAGE_INDEX_OUTPUT_PATH = config.pages_index_path.as_posix()
    render_readme.OUTPUT_PATH = config.readme_path.as_posix()
    render_readme.ASSET_OUTPUT_DIR = assets_dir
    render_readme.ASSET_DISPLAY_DIR = display_assets


def _relative_link_if_present(target: Path, base_dir: Path) -> str:
    if not target.is_file():
        return ""
    return Path(os.path.relpath(target, base_dir)).as_posix()


def _set_managed_docs_link_env(config: RuntimeConfig) -> None:
    managed_index = MANAGED_DOCS_NAMESPACE / "README.md"
    readme_parent = config.readme_path.parent
    dashboard_parent = config.pages_index_path.parent
    os.environ[MANAGED_DOCS_README_LINK_ENV] = _relative_link_if_present(
        managed_index,
        readme_parent,
    )
    os.environ[MANAGED_DOCS_DASHBOARD_LINK_ENV] = _relative_link_if_present(
        managed_index,
        dashboard_parent,
    )
    _set_managed_docs_status_env()


def _set_empty_managed_docs_status_env() -> None:
    os.environ[DOCS_SYNC_STATE_ENV] = ""
    os.environ[DOCS_ACTION_VERSION_ENV] = ""
    os.environ[DOCS_UPDATED_AT_ENV] = ""


def _set_managed_docs_status_env() -> None:
    existing_state = os.environ.get(DOCS_SYNC_STATE_ENV, "").strip()

    manifest_path = MANAGED_DOCS_NAMESPACE / managed_docs.MANIFEST_NAME
    if not manifest_path.is_file():
        if not existing_state:
            _set_empty_managed_docs_status_env()
        return

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        if existing_state:
            return
        os.environ[DOCS_SYNC_STATE_ENV] = managed_docs.STATE_MANIFEST_INCONSISTENT
        os.environ[DOCS_ACTION_VERSION_ENV] = ""
        os.environ[DOCS_UPDATED_AT_ENV] = ""
        return

    manifest_action_version = str(manifest.get("action_version") or "")
    if not os.environ.get(DOCS_ACTION_VERSION_ENV, "").strip():
        os.environ[DOCS_ACTION_VERSION_ENV] = manifest_action_version
    if not os.environ.get(DOCS_UPDATED_AT_ENV, "").strip():
        os.environ[DOCS_UPDATED_AT_ENV] = str(manifest.get("updated_at") or "")
    if existing_state:
        return
    if manifest_action_version == VERSION:
        os.environ[DOCS_SYNC_STATE_ENV] = managed_docs.STATE_UNCHANGED
        return

    os.environ[DOCS_SYNC_STATE_ENV] = DOCS_STATE_STALE


def _set_runtime_env(config: RuntimeConfig, *, next_key: bool = False) -> None:
    os.environ["RETENTION_DAYS"] = str(config.retention_days)
    os.environ["DATA_DIR"] = config.data_dir.as_posix()
    os.environ["PUBLISH_PAGES"] = str(config.publish_pages).lower()
    os.environ["ARTIFACT_SECURITY_MODE"] = config.resolved_artifact_mode
    os.environ["DASHBOARD_ACCESS_MODE"] = (
        "public" if config.resolved_artifact_mode == "plain" else "encrypted"
    )
    if config.collection_token:
        os.environ["GH_TOKEN"] = config.collection_token
    os.environ["REPONOMICS_USE_GITHUB_APP"] = str(config.use_github_app).lower()
    if config.dashboard_secret:
        os.environ["DASHBOARD_SECRET_DO_NOT_REPLACE"] = config.dashboard_secret
    if config.dashboard_next_secret:
        os.environ["DASHBOARD_NEXT_SECRET"] = config.dashboard_next_secret
    dashboard_key = config.dashboard_next_secret if next_key else config.dashboard_secret
    if dashboard_key:
        os.environ["DASHBOARD_KEY"] = dashboard_key
    if config.action_ref:
        os.environ["REPONOMICS_ACTION_REF"] = config.action_ref
    if config.action_repository:
        os.environ["REPONOMICS_ACTION_REPOSITORY"] = config.action_repository
    _set_managed_docs_link_env(config)


def _set_version_status_env(config: RuntimeConfig) -> None:
    os.environ.pop("REPONOMICS_VERSION_STATUS_JSON", None)
    status = version_status.build_status_payload(
        current_version=VERSION,
        action_ref=config.action_ref,
        action_repository=config.action_repository,
        check_latest=True,
    )
    if not status:
        return
    import json

    os.environ["REPONOMICS_VERSION_STATUS_JSON"] = json.dumps(
        status,
        separators=(",", ":"),
    )
    if status.get("latest_version"):
        print(f"Version status available for {status['latest_version']}.")
    else:
        print("Version status available without latest-release details.")


def _sha(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_outputs(config: RuntimeConfig) -> dict[str, str]:
    return {
        "readme": _sha(config.readme_path),
        "dashboard": _sha(config.pages_index_path),
    }


def _restore_artifact(config: RuntimeConfig) -> None:
    script = SCRIPTS_DIR / "restore_artifact.sh"
    if not _env("GITHUB_REPOSITORY") or not shutil.which("gh"):
        print("Skipping artifact restore outside GitHub Actions or without gh CLI.")
        return
    env = os.environ.copy()
    env["ARTIFACT_NAME"] = "dashboard-data"
    env["DATA_DIR"] = config.data_dir.as_posix()
    if config.artifact_run_id:
        env["ARTIFACT_RUN_ID"] = config.artifact_run_id
    if config.github_token:
        env["GH_TOKEN"] = config.github_token
    subprocess.run(["bash", str(script)], check=True, env=env)


def _decrypt_if_needed(config: RuntimeConfig, *, secret_env: str) -> None:
    if config.resolved_artifact_mode != "encrypted":
        encrypted = config.data_dir / "dashboard-data.enc"
        encrypted.unlink(missing_ok=True)
        return
    crypto_artifact.decrypt(
        config.data_dir / "dashboard-data.enc",
        config.data_dir,
        secret_env,
    )


def _encrypt_if_needed(config: RuntimeConfig, *, secret_env: str) -> None:
    if config.resolved_artifact_mode != "encrypted":
        return
    crypto_artifact.encrypt(
        config.data_dir,
        Path(".dashboard-data-artifact") / "dashboard-data.enc",
        secret_env,
    )


def _prepare_data_schema(config: RuntimeConfig) -> None:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    storage.migrate_schema(config.data_dir.as_posix())


def _render_outputs(config: RuntimeConfig, *, generate_readme: bool) -> None:
    render_dashboard.render()

    if not generate_readme:
        print("Skipping README render because generate-readme is false.")
        return

    render_readme.render()


def _readme_svg_asset_paths(config: RuntimeConfig) -> list[str]:
    assets_dir = config.pages_index_path.parent / "assets"
    if not assets_dir.exists():
        return []
    return [
        path.as_posix()
        for path in sorted(assets_dir.glob("*.svg"))
        if path.is_file()
    ]


def _git_commit_readme(config: RuntimeConfig, message: str) -> None:
    if not config.generate_readme:
        return
    in_repo = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        check=False,
        capture_output=True,
        text=True,
    )
    in_repo_stdout = in_repo.stdout.strip() if isinstance(in_repo.stdout, str) else ""
    if in_repo.returncode != 0 or in_repo_stdout != "true":
        print("Skipping README commit outside a git worktree.")
        return
    paths = [config.readme_path.as_posix(), *_readme_svg_asset_paths(config)]
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(
        ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
        check=True,
    )
    subprocess.run(["git", "add", *paths], check=True)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
    if diff.returncode == 0:
        print("No generated output changes to commit.")
        return
    subprocess.run(["git", "commit", "-m", message], check=True)
    subprocess.run(["git", "push"], check=True)


def _docs_result_with_state(
    result: managed_docs.ManagedDocsResult,
    *,
    state: str,
    reason: str,
) -> managed_docs.ManagedDocsResult:
    return managed_docs.ManagedDocsResult(
        state=state,
        reason=reason,
        manifest_action_version=result.manifest_action_version,
        docs_updated_at=result.docs_updated_at,
        namespace=result.namespace,
        changed=result.changed,
    )


def _git_failure_text(exc: subprocess.CalledProcessError) -> str:
    chunks = []
    stdout = getattr(exc, "stdout", "")
    stderr = getattr(exc, "stderr", "")
    if isinstance(stdout, str) and stdout.strip():
        chunks.append(stdout.strip())
    if isinstance(stderr, str) and stderr.strip():
        chunks.append(stderr.strip())
    if not chunks:
        chunks.append(str(exc))
    return " ".join(chunks)


def _is_permission_failure(text: str) -> bool:
    normalized = text.lower()
    return any(
        marker in normalized
        for marker in (
            "403",
            "authentication failed",
            "could not read username",
            "not authorized",
            "permission denied",
            "protected branch",
            "repository not found",
            "write access",
        )
    )


def _is_push_race(text: str) -> bool:
    normalized = text.lower()
    return any(
        marker in normalized
        for marker in (
            "fetch first",
            "non-fast-forward",
            "stale info",
            "updates were rejected",
        )
    )


def _run_git_capture(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, capture_output=True, text=True)


def _push_managed_docs_with_retry() -> None:
    try:
        _run_git_capture(["git", "push"])
        return
    except subprocess.CalledProcessError as first_exc:
        first_text = _git_failure_text(first_exc)
        if _is_permission_failure(first_text) or not _is_push_race(first_text):
            raise

    try:
        _run_git_capture(["git", "pull", "--rebase"])
        _run_git_capture(["git", "push"])
    except subprocess.CalledProcessError:
        raise


def _git_commit_managed_docs(
    config: RuntimeConfig,
    result: managed_docs.ManagedDocsResult,
) -> managed_docs.ManagedDocsResult:
    if not result.changed:
        return result
    in_repo = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        check=False,
        capture_output=True,
        text=True,
    )
    in_repo_stdout = in_repo.stdout.strip() if isinstance(in_repo.stdout, str) else ""
    if in_repo.returncode != 0 or in_repo_stdout != "true":
        return _docs_result_with_state(
            result,
            state=managed_docs.STATE_PERMISSION_MISSING,
            reason="Managed docs were written locally but could not be committed outside a git worktree.",
        )

    namespace = MANAGED_DOCS_NAMESPACE.as_posix()
    message = f"docs: update Reponomics managed docs for action v{VERSION} [skip ci]"
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(
            ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
            check=True,
        )
        subprocess.run(["git", "add", "--", namespace], check=True)
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--", namespace],
            check=False,
        )
        if diff.returncode == 0:
            return _docs_result_with_state(
                result,
                state=managed_docs.STATE_UNCHANGED,
                reason="Managed documentation was already committed.",
            )
        subprocess.run(["git", "commit", "-m", message, "--", namespace], check=True)
        _push_managed_docs_with_retry()
    except subprocess.CalledProcessError as exc:
        text = _git_failure_text(exc)
        if _is_permission_failure(text):
            return _docs_result_with_state(
                result,
                state=managed_docs.STATE_PERMISSION_MISSING,
                reason="Managed docs were written locally but Git push was not permitted.",
            )
        return _docs_result_with_state(
            result,
            state=managed_docs.STATE_PUSH_RACE,
            reason="Managed docs were written locally but Git push did not complete after retry.",
        )
    return result


def _tracked_repos(data_dir: Path) -> list[str]:
    repos: set[str] = set()
    for filename in ("traffic-daily.csv", "traffic-log.csv", "traffic-snapshots.csv"):
        path = data_dir / filename
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                repo = row.get("repo", "").strip()
                if repo:
                    repos.add(repo)
    return sorted(repos)


def _manifest_value(data_dir: Path, key: str) -> str:
    try:
        return str(storage.read_manifest(data_dir.as_posix()).get(key, ""))
    except Exception:
        return ""


def _docs_sync_output_values(
    result: managed_docs.ManagedDocsResult | None,
) -> dict[str, str]:
    if result is None:
        return {
            "docs-sync-state": "",
            "docs-action-version": "",
            "docs-updated-at": "",
        }
    return {
        "docs-sync-state": result.state,
        "docs-action-version": result.manifest_action_version,
        "docs-updated-at": result.docs_updated_at,
    }


def _write_outputs(
    config: RuntimeConfig,
    before: dict[str, str],
    *,
    docs_result: managed_docs.ManagedDocsResult | None = None,
) -> None:
    after = _snapshot_outputs(config)
    outputs = {
        "tracked-repos": ",".join(_tracked_repos(config.data_dir)),
        "collected-at": _manifest_value(config.data_dir, "last_updated"),
        "artifact-mode": config.resolved_artifact_mode,
        "publish-pages": str(config.publish_pages).lower(),
        "pages-path": config.pages_index_path.parent.as_posix(),
        "readme-updated": str(before.get("readme") != after.get("readme")).lower(),
        "dashboard-updated": str(before.get("dashboard") != after.get("dashboard")).lower(),
        "schema-version": storage.SCHEMA_VERSION,
        "runtime-version": VERSION,
    }
    outputs.update(_docs_sync_output_values(docs_result))
    output_path = _env("GITHUB_OUTPUT")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as handle:
            for key, value in outputs.items():
                handle.write(f"{key}={value}\n")
    for key, value in outputs.items():
        print(f"{key}: {value}")


def _summarize_rotation() -> None:
    lines = [
        "## Dashboard key rotation complete",
        "",
        "The dashboard outputs and retained dashboard data artifact now use",
        "`DASHBOARD_NEXT_SECRET`.",
        "",
        "Now replace `DASHBOARD_SECRET_DO_NOT_REPLACE` with the new key,",
        "then delete `DASHBOARD_NEXT_SECRET`.",
        "",
        "Normal setup and collection runs should wait until that manual",
        "promotion step is complete.",
    ]
    summary_path = _env("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


def _github_api_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "reponomics-dashboard-action-runtime",
    }


def _github_delete(url: str, headers: dict[str, str]) -> int:
    last_status = 0
    for attempt in range(1, INCIDENT_API_MAX_RETRIES + 1):
        try:
            response = requests.delete(url, headers=headers, timeout=INCIDENT_API_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            if attempt < INCIDENT_API_MAX_RETRIES:
                wait = collect_mod._retry_delay_with_jitter(attempt)
                print(
                    "GitHub API delete network error for "
                    + f"{url}: {exc}. retrying in {wait:.2f}s..."
                )
                time.sleep(wait)
                continue
            raise ActionError(f"GitHub API delete failed for {url}: {exc}") from exc

        last_status = response.status_code
        if response.status_code in {204, 404}:
            return response.status_code

        if collect_mod._is_secondary_rate_limit(response) and attempt < INCIDENT_API_MAX_RETRIES:
            retry_after_seconds, retry_at_utc, source = collect_mod._secondary_retry_window(response)
            wait = max(1, retry_after_seconds)
            print(
                "GitHub secondary rate limit while deleting "
                + f"{url}; retry at {retry_at_utc.strftime('%Y-%m-%d %H:%M:%S UTC')} "
                + f"(source: {source}, sleeping {wait}s)."
            )
            time.sleep(wait)
            continue

        if (
            collect_mod._is_retryable_throttle(response) or response.status_code >= 500
        ) and attempt < INCIDENT_API_MAX_RETRIES:
            wait = collect_mod._retry_delay_with_jitter(attempt)
            print(
                f"GitHub API delete throttle/server error {response.status_code} "
                + f"for {url}; retrying in {wait:.2f}s..."
            )
            time.sleep(wait)
            continue

        response_text = (getattr(response, "text", "") or "").strip().replace("\n", " ")
        if len(response_text) > 240:
            response_text = response_text[:240] + "..."
        raise ActionError(
            f"GitHub API delete failed ({response.status_code}) for {url}: "
            + (response_text or "no response body")
        )

    raise ActionError(f"GitHub API delete failed after retries for {url} (last status {last_status}).")


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
        for row in workflow_runs:
            if not isinstance(row, dict):
                continue
            run_id = row.get("id")
            if isinstance(run_id, int) and run_id != current_run_id:
                run_ids.append(run_id)
        if len(workflow_runs) < 100:
            break
        page += 1
    return run_ids


def _list_old_dashboard_data_artifacts(
    owner: str,
    repo: str,
    *,
    current_run_id: int,
    headers: dict[str, str],
) -> list[DashboardDataArtifactRef]:
    artifact_refs: list[DashboardDataArtifactRef] = []
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
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            artifact_id = artifact.get("id")
            workflow_run = artifact.get("workflow_run")
            artifact_run_id = workflow_run.get("id") if isinstance(workflow_run, dict) else None
            created_at = artifact.get("created_at")
            if not isinstance(artifact_id, int):
                continue
            if artifact_run_id == current_run_id:
                continue
            artifact_refs.append(
                DashboardDataArtifactRef(
                    artifact_id=artifact_id,
                    workflow_run_id=artifact_run_id if isinstance(artifact_run_id, int) else None,
                    created_at=created_at if isinstance(created_at, str) else "",
                )
            )
        if len(artifacts) < 100:
            break
        page += 1
    return artifact_refs


def _summarize_incident_reset_prepared() -> None:
    lines = [
        "## Incident reset artifact prepared",
        "",
        "Retained dashboard data was restored, decrypted with",
        "`DASHBOARD_SECRET_DO_NOT_REPLACE`, and re-encrypted with",
        "`DASHBOARD_NEXT_SECRET`.",
        "",
        "The composite action uploads the re-encrypted `dashboard-data`",
        "artifact before the purge step starts. If this is a serious exposure,",
        "make the repository private and disable any published Pages dashboard",
        "before relying on the purge.",
    ]
    summary_path = _env("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


def _summarize_incident_reset_purge(result: IncidentPurgeResult) -> None:
    lines = [
        "## Incident reset purge complete",
        "",
        f"- Prior dashboard-data artifacts found: {result.candidate_artifacts}",
        f"- Associated workflow runs found: {result.candidate_runs}",
        f"- Deleted workflow runs: {result.deleted_runs}",
        f"- Deleted fallback artifacts: {result.deleted_fallback_artifacts}",
        "",
        "Promote `DASHBOARD_NEXT_SECRET` into `DASHBOARD_SECRET_DO_NOT_REPLACE`",
        "before normal runs, then delete `DASHBOARD_NEXT_SECRET`.",
        "",
        "Forks do not preserve this repository's workflow runs, Actions",
        "artifacts, or secrets. The relevant exposure surfaces are current",
        "repository access, Actions artifacts/runs, Pages output, local",
        "downloads, browser/cache copies, and anyone who already had the",
        "dashboard key.",
    ]
    summary_path = _env("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


def _summarize_active_retention_cleanup(result: ActiveRetentionCleanupResult) -> None:
    lines = [
        "## Dashboard data retention cleanup complete",
        "",
        f"- Prior dashboard-data artifacts found: {result.prior_artifacts}",
        f"- Prior artifacts retained for rollback: {result.retained_prior_artifacts}",
        f"- Superseded artifacts eligible this run: {result.delete_candidates}",
        f"- Deleted superseded artifacts: {result.deleted_artifacts}",
        "",
        "Routine cleanup deletes only old `dashboard-data` artifacts after a fresh collect artifact has been uploaded. It does not delete workflow runs.",
    ]
    summary_path = _env("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


def _summarize_docs_sync(result: managed_docs.ManagedDocsResult) -> None:
    lines = [
        "## Managed Reponomics docs",
        "",
        f"- State: `{result.state}`",
        f"- Details: {result.reason}",
        f"- Action version: `{VERSION}`",
    ]
    if result.manifest_action_version:
        lines.append(f"- Docs action version: `{result.manifest_action_version}`")
    if result.docs_updated_at:
        lines.append(f"- Docs updated at: `{result.docs_updated_at}`")
    if result.state == managed_docs.STATE_PERMISSION_MISSING:
        lines.extend(
            [
                "",
                "Grant `contents: write` to the docs sync job or disable docs sync with `allow_docs_sync: false` in `config.yaml`.",
            ]
        )
    elif result.state == managed_docs.STATE_MANIFEST_INCONSISTENT:
        lines.extend(
            [
                "",
                "Reponomics could not safely write the managed docs namespace. Avoid symlinks in `docs/reponomics/`, and check for invalid managed-docs metadata.",
            ]
        )
    elif result.state == managed_docs.STATE_PUSH_RACE:
        lines.extend(
            [
                "",
                "The docs update was prepared but could not be pushed after a bounded retry. Rerun the workflow after the branch settles.",
            ]
        )
    summary_path = _env("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


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
    deleted_runs = 0
    for run_id in old_run_ids:
        status = _github_delete(
            f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}",
            headers,
        )
        if status == 204:
            deleted_runs += 1

    fallback_artifact_ids = [
        artifact.artifact_id
        for artifact in artifact_refs
        if artifact.workflow_run_id is None
    ]
    deleted_fallback_artifacts = 0
    for artifact_id in fallback_artifact_ids:
        status = _github_delete(
            f"https://api.github.com/repos/{owner}/{repo}/actions/artifacts/{artifact_id}",
            headers,
        )
        if status == 204:
            deleted_fallback_artifacts += 1
    return IncidentPurgeResult(
        candidate_artifacts=len(artifact_refs),
        candidate_runs=len(old_run_ids),
        deleted_runs=deleted_runs,
        deleted_fallback_artifacts=deleted_fallback_artifacts,
    )


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
    deleted_artifacts = 0
    if delete_candidates:
        artifact = delete_candidates[0]
        print(f"Deleting superseded dashboard-data artifact {artifact.artifact_id}.")
        status = _github_delete(
            f"https://api.github.com/repos/{owner}/{repo}/actions/artifacts/{artifact.artifact_id}",
            headers,
        )
        if status == 204:
            deleted_artifacts += 1
    return ActiveRetentionCleanupResult(
        prior_artifacts=len(artifact_refs),
        retained_prior_artifacts=len(retained),
        delete_candidates=len(delete_candidates),
        deleted_artifacts=deleted_artifacts,
    )


def _write_verified_lineage(config: RuntimeConfig, parent: lineage.PayloadSnapshot, *, operation: str) -> None:
    try:
        child = lineage.write_verified_lineage(
            config.data_dir,
            parent=parent,
            retention_days=config.retention_days,
            action_version=VERSION,
            operation=operation,
        )
    except lineage.LineageError as exc:
        raise ActionError(str(exc)) from exc
    print(
        "Verified dashboard-data lineage "
        + f"({operation}); payload digest {child.payload_digest[:12]}, semantic root {child.semantic_root_digest[:12]}."
    )


def _validate_parent_lineage(parent: lineage.PayloadSnapshot) -> None:
    try:
        lineage.validate_snapshot_lineage(parent)
    except lineage.LineageError as exc:
        raise ActionError(str(exc)) from exc


def run_collect(
    config: RuntimeConfig,
    *,
    restore_artifact: bool = True,
    execute_collect: bool = True,
) -> None:
    _patch_runtime_paths(config)
    _set_runtime_env(config)
    before = _snapshot_outputs(config)
    if restore_artifact:
        _restore_artifact(config)
    _decrypt_if_needed(config, secret_env="DASHBOARD_SECRET_DO_NOT_REPLACE")
    restored_parent = lineage.snapshot_payload(config.data_dir)
    _validate_parent_lineage(restored_parent)
    _prepare_data_schema(config)
    parent = lineage.snapshot_payload(config.data_dir)
    if execute_collect:
        collect_mod.main()
    merge.main()
    _write_verified_lineage(config, parent, operation="collect")
    _encrypt_if_needed(config, secret_env="DASHBOARD_SECRET_DO_NOT_REPLACE")
    _write_outputs(config, before)


def run_publish(config: RuntimeConfig, *, restore_artifact: bool = True) -> None:
    _patch_runtime_paths(config)
    _set_runtime_env(config)
    before = _snapshot_outputs(config)
    if restore_artifact:
        _restore_artifact(config)
    _decrypt_if_needed(config, secret_env="DASHBOARD_SECRET_DO_NOT_REPLACE")
    _prepare_data_schema(config)
    _set_version_status_env(config)
    _render_outputs(config, generate_readme=config.generate_readme)
    _git_commit_readme(config, "chore: publish Reponomics README dashboard [skip ci]")
    _write_outputs(config, before)


def run_rotate_key(config: RuntimeConfig, *, restore_artifact: bool = True) -> None:
    _patch_runtime_paths(config)
    _set_runtime_env(config)
    before = _snapshot_outputs(config)
    if restore_artifact:
        _restore_artifact(config)
    _decrypt_if_needed(config, secret_env="DASHBOARD_SECRET_DO_NOT_REPLACE")
    restored_parent = lineage.snapshot_payload(config.data_dir)
    _validate_parent_lineage(restored_parent)
    _prepare_data_schema(config)
    parent = lineage.snapshot_payload(config.data_dir)
    _write_verified_lineage(config, parent, operation="rotate-key")
    _set_runtime_env(config, next_key=True)
    _render_outputs(config, generate_readme=config.generate_readme)
    _encrypt_if_needed(config, secret_env="DASHBOARD_NEXT_SECRET")
    _git_commit_readme(config, "chore: rotate Reponomics README dashboard key [skip ci]")
    _summarize_rotation()
    _write_outputs(config, before)


def run_incident_reset(config: RuntimeConfig, *, restore_artifact: bool = True) -> None:
    _patch_runtime_paths(config)
    _set_runtime_env(config)
    before = _snapshot_outputs(config)
    if restore_artifact:
        _restore_artifact(config)
    _decrypt_if_needed(config, secret_env="DASHBOARD_SECRET_DO_NOT_REPLACE")
    restored_parent = lineage.snapshot_payload(config.data_dir)
    _validate_parent_lineage(restored_parent)
    _prepare_data_schema(config)
    parent = lineage.snapshot_payload(config.data_dir)
    _set_runtime_env(config, next_key=True)
    _write_verified_lineage(config, parent, operation="incident-reset")
    _encrypt_if_needed(config, secret_env="DASHBOARD_NEXT_SECRET")
    _summarize_incident_reset_prepared()
    _write_outputs(config, before)


def run_incident_reset_purge(config: RuntimeConfig) -> None:
    result = _purge_workflow_history(config)
    _summarize_incident_reset_purge(result)


def run_collect_retention_cleanup(config: RuntimeConfig) -> None:
    result = _cleanup_superseded_collect_artifacts(config)
    _summarize_active_retention_cleanup(result)


def run_docs_sync(config: RuntimeConfig) -> None:
    _patch_runtime_paths(config)
    before = _snapshot_outputs(config)
    try:
        result = managed_docs.sync_managed_docs(
            namespace=MANAGED_DOCS_NAMESPACE,
            bundle_dir=MANAGED_DOCS_BUNDLE_DIR,
            action_repository=config.action_repository or version_status.ACTION_REPOSITORY,
            action_version=VERSION,
            allowed=config.allow_docs_sync,
        )
    except managed_docs.ManagedDocsError as exc:
        raise ActionError(str(exc)) from exc
    result = _git_commit_managed_docs(config, result)
    _summarize_docs_sync(result)
    _write_outputs(config, before, docs_result=result)


def main(loader: Callable[[], RuntimeConfig] = load_config_from_env) -> None:
    try:
        config = loader()
        _mask_config_secrets(config)
        if _parse_bool(
            _env("REPONOMICS_COLLECT_RETENTION_CLEANUP_ONLY", "false"),
            name="collect-retention-cleanup-only",
        ):
            validate_collect_cleanup_config(config)
            run_collect_retention_cleanup(config)
            return
        validate_config(config)
        if config.mode == "collect":
            run_collect(config)
        elif config.mode == "publish":
            run_publish(config)
        elif config.mode == "rotate-key":
            run_rotate_key(config)
        elif config.mode == "docs-sync":
            run_docs_sync(config)
        elif _parse_bool(
            _env("REPONOMICS_INCIDENT_RESET_PURGE_ONLY", "false"),
            name="incident-reset-purge-only",
        ):
            run_incident_reset_purge(config)
        else:
            run_incident_reset(config)
    except ActionError as exc:
        print(f"Reponomics action error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
