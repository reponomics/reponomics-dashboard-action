"""Run deterministic template-consumer checks against the action runtime."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "dist" / "template"
DEFAULT_ACTION_REPO = ROOT
ACTION_HELPER = r"""
import csv
import json
import os
import sys
from pathlib import Path

action_repo = Path(os.environ["E2E_ACTION_REPO"]).resolve()
consumer_repo = Path(os.environ["E2E_CONSUMER_REPO"]).resolve()
profile = json.loads(os.environ["E2E_PROFILE"])

sys.path.insert(0, action_repo.as_posix())

from dashboard_action import run  # noqa: E402
from scripts import dashboard_scenarios  # noqa: E402


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


scenario = next(
    item
    for item in dashboard_scenarios.build_scenarios()
    if item.key == profile["scenario"]
)
data_dir = consumer_repo / "data"
write_csv(data_dir / "traffic-daily.csv", run.storage.DAILY_FIELDS, scenario.daily_rows)
write_csv(data_dir / "traffic-referrers.csv", run.storage.REFERRER_FIELDS, scenario.referrer_rows)
write_csv(data_dir / "traffic-paths.csv", run.storage.PATH_FIELDS, scenario.path_rows)
write_csv(data_dir / "repo-metrics.csv", run.storage.REPO_METRIC_FIELDS, scenario.metric_rows)
write_csv(
    data_dir / "collection-status.csv",
    run.storage.COLLECTION_STATUS_FIELDS,
    scenario.status_rows,
)

def build_config(mode):
    runtime_kwargs = {
        "mode": mode,
        "collection_token": "ghp_collection",
        "github_token": "ghp_runtime",
        "dashboard_secret": profile["dashboard_secret"],
        "dashboard_next_secret": "",
        "comparison_secret": "",
        "privacy_mode": profile["privacy_mode"],
        "repo_is_public": profile["repo_is_public"],
        "config_path": consumer_repo / "config.yaml",
        "data_dir": data_dir,
        "retention_days": 90,
        "artifact_run_id": "",
        "generate_readme": profile["generate_readme"],
        "publish_pages_requested": profile.get("expected_publish_pages", True),
        "pages_index_path": consumer_repo / "docs" / "index.html",
        "readme_path": consumer_repo / "README.md",
        "incident_confirm_mode": "",
        "incident_confirm_purge": "",
        "incident_confirm_irreversible": "",
        "action_ref": "template-consumer-e2e",
        "action_repository": "reponomics/reponomics-dashboard-action",
        # Compatibility across action revisions used by dashboard-dev CI.
        "use_github_app": False,
        "allow_docs_sync": True,
        "update_notices": False,
    }
    accepted_runtime_fields = set(getattr(run.RuntimeConfig, "__dataclass_fields__", {}))
    return run.RuntimeConfig(**{
        key: value
        for key, value in runtime_kwargs.items()
        if key in accepted_runtime_fields
    })

os.environ["GITHUB_OUTPUT"] = (consumer_repo / ".e2e-github-output").as_posix()
os.chdir(consumer_repo)

try:
    if hasattr(run, "run_docs_sync"):
        docs_config = build_config("docs-sync")
        run.validate_config(docs_config)
        run.run_docs_sync(docs_config)
    config = build_config("publish")
    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)
except run.ActionError as exc:
    if profile["expect_error"] and profile["expect_error"] in str(exc):
        print(f"Expected failure for {profile['name']}: {exc}")
        raise SystemExit(0)
    raise

if profile["expect_error"]:
    raise AssertionError(f"{profile['name']} should have failed with {profile['expect_error']!r}")
"""


@dataclass(frozen=True)
class ConsumerProfile:
    name: str
    privacy_mode: str
    repo_is_public: bool
    generate_readme: bool
    dashboard_secret: str
    expected_artifact_mode: str
    expected_publish_pages: bool
    scenario: str = "fixture_baseline"
    expect_error: str = ""


PROFILES = [
    ConsumerProfile(
        name="strong-private-readme",
        privacy_mode="strong",
        repo_is_public=False,
        generate_readme=True,
        dashboard_secret="DASHBOARD_SECRET_DO_NOT_REPLACE_0123456789",
        expected_artifact_mode="encrypted",
        expected_publish_pages=True,
    ),
    ConsumerProfile(
        name="casual-private-encrypted",
        privacy_mode="casual",
        repo_is_public=False,
        generate_readme=False,
        dashboard_secret="weak",
        expected_artifact_mode="encrypted",
        expected_publish_pages=True,
    ),
    ConsumerProfile(
        name="plain-private-readme",
        privacy_mode="plain",
        repo_is_public=False,
        generate_readme=True,
        dashboard_secret="",
        expected_artifact_mode="plain",
        expected_publish_pages=False,
    ),
    ConsumerProfile(
        name="plain-public-rejected",
        privacy_mode="plain",
        repo_is_public=True,
        generate_readme=False,
        dashboard_secret="",
        expected_artifact_mode="plain",
        expected_publish_pages=False,
        expect_error="plain is only supported for private repositories",
    ),
]


class TemplateConsumerE2EError(RuntimeError):
    """Raised when the template-consumer e2e check fails."""


def _absolute_path(path: Path) -> Path:
    """Make a path cwd-relative without resolving virtualenv symlinks."""
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd or ROOT,
        env=dict(env) if env is not None else None,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"Command failed: {' '.join(args)}", file=sys.stderr)
        if result.stdout:
            print(result.stdout, file=sys.stderr, end="" if result.stdout.endswith("\n") else "\n")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
        result.check_returncode()
    return result


def _copy_template(template_dir: Path, consumer_dir: Path) -> None:
    if not template_dir.exists():
        raise TemplateConsumerE2EError(f"Template directory does not exist: {template_dir}")
    shutil.copytree(template_dir, consumer_dir)


def _init_consumer_git_repo(consumer_dir: Path, remote_dir: Path) -> None:
    _run(["git", "init", "-b", "main"], cwd=consumer_dir)
    _run(["git", "config", "user.name", "template-consumer-e2e"], cwd=consumer_dir)
    _run(["git", "config", "user.email", "template-consumer-e2e@example.invalid"], cwd=consumer_dir)
    _run(["git", "add", "."], cwd=consumer_dir)
    _run(["git", "commit", "-m", "chore: seed generated template"], cwd=consumer_dir)
    _run(["git", "init", "--bare", remote_dir.as_posix()])
    _run(["git", "remote", "add", "origin", remote_dir.as_posix()], cwd=consumer_dir)
    _run(["git", "push", "-u", "origin", "main"], cwd=consumer_dir)


def _invoke_action_runtime(
    *,
    action_python: Path,
    action_repo: Path,
    consumer_dir: Path,
    profile: ConsumerProfile,
) -> None:
    if not action_python.exists():
        raise TemplateConsumerE2EError(f"Action Python does not exist: {action_python}")
    if not action_repo.exists():
        raise TemplateConsumerE2EError(f"Action repository does not exist: {action_repo}")
    env = os.environ.copy()
    env.update(
        {
            "E2E_ACTION_REPO": action_repo.as_posix(),
            "E2E_CONSUMER_REPO": consumer_dir.as_posix(),
            "E2E_PROFILE": json.dumps(asdict(profile), separators=(",", ":")),
        }
    )
    _run([action_python.as_posix(), "-c", ACTION_HELPER], cwd=consumer_dir, env=env)


def _read_github_output(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def _git_tree(consumer_dir: Path) -> set[str]:
    output = _run(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=consumer_dir).stdout
    return set(output.splitlines())


def _assert_successful_profile(consumer_dir: Path, profile: ConsumerProfile) -> None:
    outputs = _read_github_output(consumer_dir / ".e2e-github-output")
    if outputs.get("artifact-mode") != profile.expected_artifact_mode:
        raise TemplateConsumerE2EError(
            f"{profile.name}: artifact-mode={outputs.get('artifact-mode')!r}"
        )
    if outputs.get("publish-pages") != str(profile.expected_publish_pages).lower():
        raise TemplateConsumerE2EError(
            f"{profile.name}: publish-pages={outputs.get('publish-pages')!r}"
        )

    dashboard_path = consumer_dir / "docs" / "index.html"
    if not dashboard_path.is_file():
        raise TemplateConsumerE2EError(f"{profile.name}: dashboard HTML was not rendered")
    dashboard = dashboard_path.read_text(encoding="utf-8")
    if profile.expected_artifact_mode == "encrypted":
        if "encrypted-dashboard-data" not in dashboard or "export-manifest" not in dashboard:
            raise TemplateConsumerE2EError(f"{profile.name}: encrypted dashboard markers missing")
        if not list((consumer_dir / "docs" / "assets").glob("export-data-*.enc")):
            raise TemplateConsumerE2EError(f"{profile.name}: encrypted export asset missing")
    elif "encrypted-dashboard-data" in dashboard or "encrypted-payload" in dashboard:
        raise TemplateConsumerE2EError(f"{profile.name}: plain dashboard contains encrypted data")
    elif "dashboardDataObject" not in dashboard or "dashboardPayload" in dashboard:
        raise TemplateConsumerE2EError(f"{profile.name}: plain dashboard chunk object missing")

    managed_manifest = consumer_dir / "docs" / "reponomics" / ".manifest.json"
    if not managed_manifest.is_file():
        raise TemplateConsumerE2EError(f"{profile.name}: managed docs manifest missing")

    if not profile.generate_readme:
        return

    readme = consumer_dir / "README.md"
    if not readme.is_file():
        raise TemplateConsumerE2EError(f"{profile.name}: README was not rendered")

    tree = _git_tree(consumer_dir)
    svg_assets = sorted(
        path for path in tree if path.startswith("docs/assets/") and path.endswith(".svg")
    )
    if not svg_assets:
        raise TemplateConsumerE2EError(f"{profile.name}: README SVG assets were not committed")
    if "docs/assets/chart.umd.min.js" in tree:
        raise TemplateConsumerE2EError(f"{profile.name}: Pages Chart.js asset was committed")
    if any(path.startswith("docs/assets/export-data-") for path in tree):
        raise TemplateConsumerE2EError(f"{profile.name}: encrypted export asset was committed")


def run_e2e(
    *,
    template_dir: Path,
    action_repo: Path,
    action_python: Path,
    keep_temp: bool = False,
) -> None:
    template_dir = _absolute_path(template_dir)
    action_repo = _absolute_path(action_repo)
    action_python = _absolute_path(action_python)
    temp_root = Path(tempfile.mkdtemp(prefix="template-consumer-e2e-"))
    try:
        for profile in PROFILES:
            consumer_dir = temp_root / profile.name / "repo"
            remote_dir = temp_root / profile.name / "remote.git"
            _copy_template(template_dir.resolve(), consumer_dir)
            _init_consumer_git_repo(consumer_dir, remote_dir)
            _invoke_action_runtime(
                action_python=action_python,
                action_repo=action_repo.resolve(),
                consumer_dir=consumer_dir,
                profile=profile,
            )
            if not profile.expect_error:
                _assert_successful_profile(consumer_dir, profile)
            print(f"Template consumer e2e passed: {profile.name}")
    finally:
        if keep_temp:
            print(f"Kept e2e temp directory: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-dir", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--action-repo", type=Path, default=DEFAULT_ACTION_REPO)
    parser.add_argument(
        "--action-python",
        type=Path,
        default=DEFAULT_ACTION_REPO / "venv" / "bin" / "python",
    )
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()
    run_e2e(
        template_dir=args.template_dir,
        action_repo=args.action_repo,
        action_python=args.action_python,
        keep_temp=args.keep_temp,
    )


if __name__ == "__main__":
    main()
