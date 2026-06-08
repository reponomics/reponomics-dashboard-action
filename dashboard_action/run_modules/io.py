"""Artifact, output, and README publishing helpers."""

from __future__ import annotations

import csv
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from .config import _env
from .core import SCRIPTS_DIR, VERSION, RuntimeConfig

import crypto_artifact  # noqa: E402
import render_dashboard  # noqa: E402
import render_readme  # noqa: E402
import storage  # noqa: E402


def _sha(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_outputs(config: RuntimeConfig) -> dict[str, str]:
    return {
        "readme": _sha(config.readme_path),
        "dashboard": _sha(config.pages_index_path),
    }


def _restore_artifact(
    config: RuntimeConfig,
    *,
    artifact_name: str = "dashboard-data",
    data_dir: Path | None = None,
    required: bool | None = None,
    artifact_run_id: str | None = None,
) -> None:
    script = SCRIPTS_DIR / "restore_artifact.sh"
    if not _env("GITHUB_REPOSITORY") or not shutil.which("gh"):
        print("Skipping artifact restore outside GitHub Actions or without gh CLI.")
        return
    env = os.environ.copy()
    env["ARTIFACT_NAME"] = artifact_name
    env["DATA_DIR"] = (data_dir or config.data_dir).as_posix()
    restore_run_id = config.artifact_run_id if artifact_run_id is None else artifact_run_id
    if restore_run_id:
        env["ARTIFACT_RUN_ID"] = restore_run_id
    if required is not None:
        env["ARTIFACT_REQUIRED"] = str(required).lower()
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
    result: object | None,
) -> dict[str, str]:
    if result is None:
        return {
            "docs-sync-state": "",
            "docs-action-version": "",
            "docs-updated-at": "",
        }
    return {
        "docs-sync-state": getattr(result, "state"),
        "docs-action-version": getattr(result, "manifest_action_version"),
        "docs-updated-at": getattr(result, "docs_updated_at"),
    }


def _write_outputs(
    config: RuntimeConfig,
    before: dict[str, str],
    *,
    docs_result: object | None = None,
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
