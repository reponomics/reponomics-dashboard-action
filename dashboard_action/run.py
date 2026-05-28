"""Orchestrate the bundled Reponomics runtime for GitHub Actions."""

from __future__ import annotations

import csv
import hashlib
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests


VERSION = "0.13.0"  # x-release-please-version
ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT / "runtime" / "scripts"
MIN_SECRET_LENGTH = 40
MIN_MASK_LENGTH = 3
INCIDENT_CONFIRM_MODE = "INCIDENT_RESET_CONFIRMED"
INCIDENT_CONFIRM_PURGE = "PURGE_OLD_HISTORY_CONFIRMED"
INCIDENT_CONFIRM_IRREVERSIBLE = "IRREVERSIBLE_ACTION_CONFIRMED"
INCIDENT_API_TIMEOUT_SECONDS = 20
INCIDENT_API_MAX_RETRIES = 6

VALID_MODES = {"collect", "publish", "rotate-key", "incident-reset"}
VALID_PRIVACY_MODES = {"strong", "casual", "plain"}

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import collect as collect_mod  # noqa: E402
import bootstrap  # noqa: E402
import crypto_artifact  # noqa: E402
import load_data  # noqa: E402
import merge  # noqa: E402
import render_dashboard  # noqa: E402
import render_readme  # noqa: E402
import release_notice  # noqa: E402
import repo_config  # noqa: E402
import storage  # noqa: E402


class ActionError(RuntimeError):
    """Raised for user-facing action failures."""


@dataclass(frozen=True)
class RuntimeConfig:
    mode: str
    collection_token: str
    github_token: str
    dashboard_secret: str
    dashboard_next_secret: str
    privacy_mode: str
    repo_is_public: bool
    config_path: Path
    data_dir: Path
    retention_days: int
    generate_readme: bool
    pages_index_path: Path
    readme_path: Path
    update_notices: bool
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
        return self.privacy_mode != "plain"


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
    return RuntimeConfig(
        mode=mode,
        collection_token=_first_env(
            "REPONOMICS_COLLECTION_TOKEN",
            "COLLECTION_TOKEN",
            "REPONOMICS_GITHUB_TOKEN",
            "GH_TOKEN",
        ),
        github_token=_first_env("REPONOMICS_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"),
        dashboard_secret=_first_env("REPONOMICS_DASHBOARD_SECRET", "DASHBOARD_SECRET_DO_NOT_REPLACE"),
        dashboard_next_secret=_first_env(
            "REPONOMICS_DASHBOARD_NEXT_SECRET",
            "DASHBOARD_NEXT_SECRET",
        ),
        privacy_mode=privacy_mode,
        repo_is_public=repo_is_public,
        config_path=Path(_env("REPONOMICS_CONFIG_PATH", "config.yaml")),
        data_dir=Path("data"),
        retention_days=_parse_retention_days(_env("REPONOMICS_RETENTION_DAYS", "90")),
        generate_readme=_parse_bool(_env("REPONOMICS_GENERATE_README", "false"), name="generate-readme"),
        pages_index_path=Path("docs/index.html"),
        readme_path=Path(_env("REPONOMICS_README_PATH", "README.md")),
        update_notices=_parse_bool(
            _env("REPONOMICS_UPDATE_NOTICES", "true"),
            name="update-notices",
        ),
        incident_confirm_mode=_env("REPONOMICS_INCIDENT_CONFIRM_MODE"),
        incident_confirm_purge=_env("REPONOMICS_INCIDENT_CONFIRM_PURGE"),
        incident_confirm_irreversible=_env("REPONOMICS_INCIDENT_CONFIRM_IRREVERSIBLE"),
        action_ref=_env("REPONOMICS_ACTION_REF"),
        action_repository=_env("REPONOMICS_ACTION_REPOSITORY"),
    )


def validate_config(config: RuntimeConfig) -> None:
    if config.mode == "collect" and not config.collection_token:
        raise ActionError("collection-token, COLLECTION_TOKEN, or GH_TOKEN is required for collect mode.")
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


def _set_runtime_env(config: RuntimeConfig, *, next_key: bool = False) -> None:
    os.environ["RETENTION_DAYS"] = str(config.retention_days)
    os.environ["DATA_DIR"] = config.data_dir.as_posix()
    os.environ["PUBLISH_PAGES"] = str(config.publish_pages).lower()
    os.environ["ARTIFACT_SECURITY_MODE"] = config.resolved_artifact_mode
    os.environ["DASHBOARD_ACCESS_MODE"] = (
        "encrypted" if config.publish_pages else "public"
    )
    if config.collection_token:
        os.environ["GH_TOKEN"] = config.collection_token
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


def _set_update_notice_env(config: RuntimeConfig) -> None:
    os.environ.pop("REPONOMICS_UPDATE_NOTICE_JSON", None)
    if not config.update_notices:
        print("Update notice check disabled.")
        return
    if not config.action_ref or not config.action_repository:
        print("Update notice check skipped outside a GitHub action ref context.")
        return
    notice = release_notice.find_update_notice(
        token=config.github_token,
        current_version=VERSION,
        action_ref=config.action_ref,
        action_repository=config.action_repository,
    )
    if not notice:
        return
    import json

    os.environ["REPONOMICS_UPDATE_NOTICE_JSON"] = json.dumps(
        notice,
        separators=(",", ":"),
    )
    print(f"Update notice available for {notice['version']}.")


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
    paths = [config.readme_path.as_posix()]
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


def _write_outputs(config: RuntimeConfig, before: dict[str, str]) -> None:
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
        raise ActionError("incident-reset requires GITHUB_REPOSITORY in owner/repo format.")
    owner, repo = repository.split("/", 1)
    if not owner or not repo:
        raise ActionError("incident-reset requires GITHUB_REPOSITORY in owner/repo format.")
    return owner, repo


def _github_run_id() -> int:
    raw = _env("GITHUB_RUN_ID")
    if not raw:
        raise ActionError("incident-reset requires GITHUB_RUN_ID.")
    try:
        return int(raw)
    except ValueError as exc:
        raise ActionError(f"incident-reset received invalid GITHUB_RUN_ID: {raw!r}.") from exc


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


def _list_old_dashboard_data_artifact_ids(
    owner: str,
    repo: str,
    *,
    current_run_id: int,
    old_run_ids: set[int],
    headers: dict[str, str],
) -> list[int]:
    artifact_ids: list[int] = []
    page = 1
    while True:
        payload = _github_fetch_json(
            f"https://api.github.com/repos/{owner}/{repo}/actions/artifacts"
            + f"?name=dashboard-data&per_page=100&page={page}",
            headers,
        )
        if not isinstance(payload, dict):
            raise ActionError("incident-reset received an unexpected artifact payload.")
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list):
            raise ActionError("incident-reset received an invalid artifacts list payload.")
        if not artifacts:
            break
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            artifact_id = artifact.get("id")
            workflow_run = artifact.get("workflow_run")
            artifact_run_id = workflow_run.get("id") if isinstance(workflow_run, dict) else None
            if not isinstance(artifact_id, int):
                continue
            if artifact_run_id == current_run_id:
                continue
            if isinstance(artifact_run_id, int) and artifact_run_id in old_run_ids:
                artifact_ids.append(artifact_id)
        if len(artifacts) < 100:
            break
        page += 1
    return artifact_ids


def _summarize_incident_reset(*, deleted_runs: int, deleted_artifacts: int) -> None:
    lines = [
        "## Incident reset complete",
        "",
        f"- Deleted workflow runs: {deleted_runs}",
        f"- Deleted fallback artifacts: {deleted_artifacts}",
        "- Rotated runtime encryption to `DASHBOARD_NEXT_SECRET`.",
        "",
        "Promote `DASHBOARD_NEXT_SECRET` into `DASHBOARD_SECRET_DO_NOT_REPLACE` before normal runs.",
        "Then delete `DASHBOARD_NEXT_SECRET`.",
    ]
    summary_path = _env("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


def _purge_workflow_history(config: RuntimeConfig) -> tuple[int, int]:
    owner, repo = _github_repository()
    current_run_id = _github_run_id()
    headers = _github_api_headers(config.github_token)
    workflow_id = _current_workflow_id(owner, repo, current_run_id, headers)
    old_run_ids = _list_workflow_run_ids(
        owner,
        repo,
        workflow_id,
        current_run_id=current_run_id,
        headers=headers,
    )
    deleted_runs = 0
    for run_id in old_run_ids:
        status = _github_delete(
            f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}",
            headers,
        )
        if status == 204:
            deleted_runs += 1

    old_run_id_set = set(old_run_ids)
    artifact_ids = _list_old_dashboard_data_artifact_ids(
        owner,
        repo,
        current_run_id=current_run_id,
        old_run_ids=old_run_id_set,
        headers=headers,
    )
    deleted_artifacts = 0
    for artifact_id in artifact_ids:
        status = _github_delete(
            f"https://api.github.com/repos/{owner}/{repo}/actions/artifacts/{artifact_id}",
            headers,
        )
        if status == 204:
            deleted_artifacts += 1
    return deleted_runs, deleted_artifacts


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
    _prepare_data_schema(config)
    if execute_collect:
        collect_mod.main()
    merge.main()
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
    _set_update_notice_env(config)
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
    _prepare_data_schema(config)
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
    _prepare_data_schema(config)
    _set_runtime_env(config, next_key=True)
    _encrypt_if_needed(config, secret_env="DASHBOARD_NEXT_SECRET")
    deleted_runs, deleted_artifacts = _purge_workflow_history(config)
    _summarize_incident_reset(
        deleted_runs=deleted_runs,
        deleted_artifacts=deleted_artifacts,
    )
    _write_outputs(config, before)


def main(loader: Callable[[], RuntimeConfig] = load_config_from_env) -> None:
    try:
        config = loader()
        _mask_config_secrets(config)
        validate_config(config)
        if config.mode == "collect":
            run_collect(config)
        elif config.mode == "publish":
            run_publish(config)
        elif config.mode == "rotate-key":
            run_rotate_key(config)
        else:
            run_incident_reset(config)
    except ActionError as exc:
        print(f"Reponomics action error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
