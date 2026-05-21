"""Orchestrate the bundled Reponomics runtime for GitHub Actions."""

from __future__ import annotations

import csv
import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


VERSION = "0.4.0"  # x-release-please-version
ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT / "runtime" / "scripts"
MIN_SECRET_LENGTH = 40

VALID_MODES = {"collect", "publish", "rotate-key"}
VALID_README_DASHBOARDS = {"disabled", "enabled", "metrics_summary"}
VALID_PAGES_DASHBOARDS = {"disabled", "plain", "public", "encrypted"}
VALID_ARTIFACT_MODES = {"plain", "encrypted", "auto"}

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import collect as collect_mod  # noqa: E402
import bootstrap  # noqa: E402
import crypto_artifact  # noqa: E402
import load_data  # noqa: E402
import merge  # noqa: E402
import render_dashboard  # noqa: E402
import render_dashboard_placeholder  # noqa: E402
import render_private_readme  # noqa: E402
import render_readme  # noqa: E402
import release_notice  # noqa: E402
import repo_config  # noqa: E402
import storage  # noqa: E402


class ActionError(RuntimeError):
    """Raised for user-facing action failures."""


@dataclass(frozen=True)
class RuntimeConfig:
    mode: str
    traffic_token: str
    github_token: str
    dashboard_secret: str
    dashboard_next_secret: str
    readme_dashboard: str
    pages_dashboard: str
    artifact_security_mode: str
    config_path: Path
    data_dir: Path
    retention_days: int
    commit_outputs: bool
    dashboard_path: Path
    readme_path: Path
    allow_weak_dashboard_secret: bool
    update_notices: bool
    action_ref: str
    action_repository: str

    @property
    def resolved_artifact_mode(self) -> str:
        if self.artifact_security_mode != "auto":
            return self.artifact_security_mode
        if _repo_is_public() and self.pages_dashboard != "plain":
            return "encrypted"
        return "plain"

    @property
    def normalized_readme_dashboard(self) -> str:
        return "enabled" if self.readme_dashboard == "metrics_summary" else self.readme_dashboard

    @property
    def normalized_pages_dashboard(self) -> str:
        return "plain" if self.pages_dashboard == "public" else self.pages_dashboard


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


def _normalize_readme_dashboard(value: str) -> str:
    normalized = _choice(value, VALID_README_DASHBOARDS, name="readme-dashboard")
    return "enabled" if normalized == "metrics_summary" else normalized


def _normalize_pages_dashboard(value: str) -> str:
    normalized = _choice(value, VALID_PAGES_DASHBOARDS, name="pages-dashboard")
    return "plain" if normalized == "public" else normalized


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
        return value.lower() == "false"
    event_path = _env("GITHUB_EVENT_PATH")
    if event_path:
        try:
            import json

            payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
            private = payload.get("repository", {}).get("private")
            if isinstance(private, bool):
                return not private
        except (OSError, ValueError):
            pass
    return False


def load_config_from_env() -> RuntimeConfig:
    mode = _choice(_env("REPONOMICS_MODE", "collect"), VALID_MODES, name="mode")
    readme_dashboard = _normalize_readme_dashboard(
        _env("REPONOMICS_README_DASHBOARD", "disabled"),
    )
    pages_dashboard = _normalize_pages_dashboard(
        _env("REPONOMICS_PAGES_DASHBOARD", "encrypted"),
    )
    artifact_mode = _choice(
        _env("REPONOMICS_ARTIFACT_SECURITY_MODE", "auto"),
        VALID_ARTIFACT_MODES,
        name="artifact-security-mode",
    )
    return RuntimeConfig(
        mode=mode,
        traffic_token=_first_env(
            "REPONOMICS_TRAFFIC_TOKEN",
            "TRAFFIC_TOKEN",
            "REPONOMICS_GITHUB_TOKEN",
            "GH_TOKEN",
        ),
        github_token=_first_env("REPONOMICS_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"),
        dashboard_secret=_first_env("REPONOMICS_DASHBOARD_SECRET", "TRAFFIC_DASHBOARD_SECRET"),
        dashboard_next_secret=_first_env(
            "REPONOMICS_DASHBOARD_NEXT_SECRET",
            "TRAFFIC_DASHBOARD_NEXT_SECRET",
        ),
        readme_dashboard=readme_dashboard,
        pages_dashboard=pages_dashboard,
        artifact_security_mode=artifact_mode,
        config_path=Path(_env("REPONOMICS_CONFIG_PATH", "config.yaml")),
        data_dir=Path(_env("REPONOMICS_DATA_DIR", "data")),
        retention_days=_parse_retention_days(_env("REPONOMICS_RETENTION_DAYS", "90")),
        commit_outputs=_parse_bool(_env("REPONOMICS_COMMIT_OUTPUTS", "false"), name="commit-outputs"),
        dashboard_path=Path(_env("REPONOMICS_DASHBOARD_PATH", "docs/index.html")),
        readme_path=Path(_env("REPONOMICS_README_PATH", "README.md")),
        allow_weak_dashboard_secret=_parse_bool(
            _env("REPONOMICS_ALLOW_WEAK_DASHBOARD_SECRET", "false"),
            name="allow-weak-dashboard-secret",
        ),
        update_notices=_parse_bool(
            _env("REPONOMICS_UPDATE_NOTICES", "true"),
            name="update-notices",
        ),
        action_ref=_env("REPONOMICS_ACTION_REF"),
        action_repository=_env("REPONOMICS_ACTION_REPOSITORY"),
    )


def validate_config(config: RuntimeConfig) -> None:
    if config.mode == "collect" and not config.traffic_token:
        raise ActionError("traffic-token, TRAFFIC_TOKEN, or GH_TOKEN is required for collect mode.")
    if config.mode in {"collect", "publish"} and config.resolved_artifact_mode == "encrypted":
        _validate_secret(
            config.dashboard_secret,
            "dashboard-secret or TRAFFIC_DASHBOARD_SECRET",
            allow_weak=config.allow_weak_dashboard_secret,
        )
    if config.mode == "publish" and config.pages_dashboard == "encrypted":
        _validate_secret(
            config.dashboard_secret,
            "dashboard-secret or TRAFFIC_DASHBOARD_SECRET",
            allow_weak=config.allow_weak_dashboard_secret,
        )
    if config.mode == "rotate-key":
        if config.resolved_artifact_mode != "encrypted" and config.pages_dashboard != "encrypted":
            raise ActionError("rotate-key requires encrypted artifact storage or encrypted Pages.")
        _validate_secret(
            config.dashboard_secret,
            "dashboard-secret or TRAFFIC_DASHBOARD_SECRET",
            allow_weak=True,
        )
        _validate_secret(
            config.dashboard_next_secret,
            "dashboard-next-secret or TRAFFIC_DASHBOARD_NEXT_SECRET",
            allow_weak=config.allow_weak_dashboard_secret,
        )


def _validate_secret(value: str, label: str, *, allow_weak: bool) -> None:
    if not value:
        raise ActionError(f"{label} is required for the selected encrypted mode.")
    if len(value) < MIN_SECRET_LENGTH and not allow_weak:
        raise ActionError(
            f"{label} is below the Reponomics dashboard secret entropy policy. "
            "Use a generated random secret, or set allow-weak-dashboard-secret "
            "to true if you explicitly accept the disclosure and brute-force risk."
        )


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

    assets_dir = config.dashboard_path.parent / "assets"
    readme_parent = config.readme_path.parent
    display_assets = Path(os.path.relpath(assets_dir, readme_parent))

    render_dashboard.OUTPUT_PATH = config.dashboard_path.as_posix()
    render_dashboard_placeholder.OUTPUT_PATH = config.dashboard_path
    render_readme.OUTPUT_PATH = config.readme_path.as_posix()
    render_readme.ASSET_OUTPUT_DIR = assets_dir
    render_readme.ASSET_DISPLAY_DIR = display_assets
    render_private_readme.OUTPUT_PATH = config.readme_path
    render_private_readme.ASSET_DIR = assets_dir


def _set_runtime_env(config: RuntimeConfig, *, next_key: bool = False) -> None:
    os.environ["RETENTION_DAYS"] = str(config.retention_days)
    os.environ["DATA_DIR"] = config.data_dir.as_posix()
    os.environ["README_DASHBOARD"] = config.normalized_readme_dashboard
    os.environ["PAGES_DASHBOARD"] = config.normalized_pages_dashboard
    os.environ["ARTIFACT_SECURITY_MODE"] = config.resolved_artifact_mode
    os.environ["DASHBOARD_ACCESS_MODE"] = (
        "encrypted" if config.pages_dashboard == "encrypted" else "public"
    )
    if config.traffic_token:
        os.environ["GH_TOKEN"] = config.traffic_token
    if config.dashboard_secret:
        os.environ["TRAFFIC_DASHBOARD_SECRET"] = config.dashboard_secret
    if config.dashboard_next_secret:
        os.environ["TRAFFIC_DASHBOARD_NEXT_SECRET"] = config.dashboard_next_secret
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
        "dashboard": _sha(config.dashboard_path),
    }


def _restore_artifact(config: RuntimeConfig) -> None:
    script = SCRIPTS_DIR / "restore_artifact.sh"
    if not _env("GITHUB_REPOSITORY") or not shutil.which("gh"):
        print("Skipping artifact restore outside GitHub Actions or without gh CLI.")
        return
    env = os.environ.copy()
    env["ARTIFACT_NAME"] = "traffic-data"
    env["DATA_DIR"] = config.data_dir.as_posix()
    if config.github_token:
        env["GH_TOKEN"] = config.github_token
    subprocess.run(["bash", str(script)], check=True, env=env)


def _decrypt_if_needed(config: RuntimeConfig, *, secret_env: str) -> None:
    if config.resolved_artifact_mode != "encrypted":
        encrypted = config.data_dir / "traffic-data.enc"
        encrypted.unlink(missing_ok=True)
        return
    crypto_artifact.decrypt(
        config.data_dir / "traffic-data.enc",
        config.data_dir,
        secret_env,
    )


def _encrypt_if_needed(config: RuntimeConfig, *, secret_env: str) -> None:
    if config.resolved_artifact_mode != "encrypted":
        return
    crypto_artifact.encrypt(
        config.data_dir,
        Path(".traffic-artifact") / "traffic-data.enc",
        secret_env,
    )


def _prepare_data_schema(config: RuntimeConfig) -> None:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    storage.migrate_schema(config.data_dir.as_posix())


def _render_outputs(config: RuntimeConfig) -> None:
    if config.pages_dashboard == "disabled":
        render_dashboard_placeholder.render()
    else:
        render_dashboard.render()

    if config.normalized_readme_dashboard == "enabled":
        render_readme.render()
    else:
        render_private_readme.render()


def _git_commit_readme(config: RuntimeConfig, message: str) -> None:
    if not config.commit_outputs:
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
        "dashboard-mode": config.normalized_pages_dashboard,
        "pages-path": config.dashboard_path.parent.as_posix(),
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
        "The dashboard outputs and retained traffic artifact now use",
        "`TRAFFIC_DASHBOARD_NEXT_SECRET`.",
        "",
        "Now replace `TRAFFIC_DASHBOARD_SECRET` with the new key,",
        "then delete `TRAFFIC_DASHBOARD_NEXT_SECRET`.",
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
    _decrypt_if_needed(config, secret_env="TRAFFIC_DASHBOARD_SECRET")
    _prepare_data_schema(config)
    if execute_collect:
        collect_mod.main()
    merge.main()
    _encrypt_if_needed(config, secret_env="TRAFFIC_DASHBOARD_SECRET")
    _write_outputs(config, before)


def run_publish(config: RuntimeConfig, *, restore_artifact: bool = True) -> None:
    _patch_runtime_paths(config)
    _set_runtime_env(config)
    before = _snapshot_outputs(config)
    if restore_artifact:
        _restore_artifact(config)
    _decrypt_if_needed(config, secret_env="TRAFFIC_DASHBOARD_SECRET")
    _prepare_data_schema(config)
    _set_update_notice_env(config)
    _render_outputs(config)
    _git_commit_readme(config, "chore: publish Reponomics README dashboard [skip ci]")
    _write_outputs(config, before)


def run_rotate_key(config: RuntimeConfig, *, restore_artifact: bool = True) -> None:
    _patch_runtime_paths(config)
    _set_runtime_env(config)
    before = _snapshot_outputs(config)
    if restore_artifact:
        _restore_artifact(config)
    _decrypt_if_needed(config, secret_env="TRAFFIC_DASHBOARD_SECRET")
    _prepare_data_schema(config)
    _set_runtime_env(config, next_key=True)
    _render_outputs(config)
    _encrypt_if_needed(config, secret_env="TRAFFIC_DASHBOARD_NEXT_SECRET")
    _git_commit_readme(config, "chore: rotate Reponomics README dashboard key [skip ci]")
    _summarize_rotation()
    _write_outputs(config, before)


def main(loader: Callable[[], RuntimeConfig] = load_config_from_env) -> None:
    try:
        config = loader()
        validate_config(config)
        if config.mode == "collect":
            run_collect(config)
        elif config.mode == "publish":
            run_publish(config)
        else:
            run_rotate_key(config)
    except ActionError as exc:
        print(f"Reponomics action error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
