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
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

try:
    from scripts.repo_paths import find_repo_root
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_paths import find_repo_root  # type: ignore[import-not-found,no-redef]


ROOT = find_repo_root(Path(__file__))
DEFAULT_TEMPLATE = ROOT / "dist" / "template"
DEFAULT_ACTION_REPO = ROOT
DEFAULT_ACTION_PYTHON = DEFAULT_ACTION_REPO / "venv" / "bin" / "python"
RUNTIME_STEP_NAME = "Run Reponomics runtime"
RUNTIME_STEP_SHELL = "bash"
REQUIRED_COMPOSITE_ENV = {
    "REPONOMICS_MODE": "${{ inputs.mode }}",
    "REPONOMICS_GITHUB_TOKEN": "${{ inputs.github-token }}",
    "REPONOMICS_ACTION_REF": "${{ github.action_ref }}",
    "REPONOMICS_ACTION_REPOSITORY": "${{ github.action_repository }}",
}
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
        "data_mode": profile["data_mode"],
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
        "incident_confirm_next_secret": "",
        "incident_confirm_irreversible": "",
        "action_ref": "template-consumer-e2e",
        "action_repository": "reponomics/reponomics-dashboard-action",
        # Compatibility across action revisions used by the template contract tests.
        "use_github_app": False,
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
    if hasattr(run, "run_update_docs"):
        docs_config = build_config("update-docs")
        run.validate_config(docs_config)
        run.run_update_docs(docs_config)
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
    data_mode: str
    repo_is_public: bool
    generate_readme: bool
    dashboard_secret: str
    expected_data_mode: str
    expected_publish_pages: bool
    scenario: str = "fixture_baseline"
    expect_error: str = ""


PROFILES = [
    ConsumerProfile(
        name="encrypted-private-readme",
        data_mode="encrypted",
        repo_is_public=False,
        generate_readme=True,
        dashboard_secret="DASHBOARD_SECRET_DO_NOT_REPLACE_0123456789",
        expected_data_mode="encrypted",
        expected_publish_pages=True,
    ),
    ConsumerProfile(
        name="encrypted-private-short-key",
        data_mode="encrypted",
        repo_is_public=False,
        generate_readme=False,
        dashboard_secret="weak",
        expected_data_mode="encrypted",
        expected_publish_pages=True,
    ),
    ConsumerProfile(
        name="plaintext-private-readme",
        data_mode="plaintext",
        repo_is_public=False,
        generate_readme=True,
        dashboard_secret="",
        expected_data_mode="plaintext",
        expected_publish_pages=False,
    ),
    ConsumerProfile(
        name="plaintext-public-rejected",
        data_mode="plaintext",
        repo_is_public=True,
        generate_readme=False,
        dashboard_secret="",
        expected_data_mode="plaintext",
        expected_publish_pages=False,
        expect_error="plaintext is only supported for private repositories",
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


def _write_setup_config(
    consumer_dir: Path,
    *,
    data_mode: str = "encrypted",
    publish_pages_dashboard: bool = True,
    publish_readme_dashboard: bool = False,
    artifact_retention_days: int = 90,
    use_github_app: bool = False,
) -> None:
    config_path = consumer_dir / "config.yaml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise TemplateConsumerE2EError("Generated config.yaml must contain a mapping")
    payload.update(
        {
            "i_have_read_the_readme": True,
            "data_mode": data_mode,
            "publish_pages_dashboard": publish_pages_dashboard,
            "publish_readme_dashboard": publish_readme_dashboard,
            "artifact_retention_days": artifact_retention_days,
            "use_github_app": use_github_app,
        }
    )
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


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


def _load_action(action_repo: Path) -> dict:
    return yaml.safe_load((action_repo / "action.yml").read_text(encoding="utf-8"))


def _runtime_step(action: dict) -> dict:
    for step in action["runs"]["steps"]:
        if step.get("name") == RUNTIME_STEP_NAME:
            return step
    raise TemplateConsumerE2EError(f"action.yml is missing {RUNTIME_STEP_NAME!r}")


def _assert_runtime_step_contract(step: dict) -> None:
    if step.get("shell") != RUNTIME_STEP_SHELL:
        raise TemplateConsumerE2EError(
            f"{RUNTIME_STEP_NAME!r} must declare shell: {RUNTIME_STEP_SHELL}"
        )
    env = step.get("env")
    if not isinstance(env, dict):
        raise TemplateConsumerE2EError(f"{RUNTIME_STEP_NAME!r} must declare env mappings")
    mismatches = [
        f"{name}: expected {expected!r}, got {env.get(name)!r}"
        for name, expected in sorted(REQUIRED_COMPOSITE_ENV.items())
        if env.get(name) != expected
    ]
    if mismatches:
        details = "\n".join(f"  - {entry}" for entry in mismatches)
        raise TemplateConsumerE2EError(
            f"{RUNTIME_STEP_NAME!r} has invalid required env mappings:\n{details}"
        )
    if step.get("run") != 'PYTHONPATH="$GITHUB_ACTION_PATH" python -m dashboard_action.run':
        raise TemplateConsumerE2EError(f"{RUNTIME_STEP_NAME!r} must execute the runtime module")


def _action_input_defaults(action: dict) -> dict[str, str]:
    defaults: dict[str, str] = {}
    for name, metadata in action.get("inputs", {}).items():
        default = metadata.get("default", "") if isinstance(metadata, dict) else ""
        defaults[str(name)] = "" if default is None else str(default)
    return defaults


def _resolve_expression(value: str, *, inputs: Mapping[str, str], github: Mapping[str, str]) -> str:
    stripped = value.strip()
    prefix = "${{ "
    suffix = " }}"
    if not stripped.startswith(prefix) or not stripped.endswith(suffix):
        return value
    expression = stripped.removeprefix(prefix).removesuffix(suffix).strip()
    if expression.startswith("inputs."):
        return inputs.get(expression.removeprefix("inputs."), "")
    if expression.startswith("github."):
        return github.get(expression.removeprefix("github."), "")
    return value


def _resolve_runtime_env(
    action: dict,
    *,
    provided_inputs: Mapping[str, str],
    github: Mapping[str, str],
) -> dict[str, str]:
    step = _runtime_step(action)
    _assert_runtime_step_contract(step)
    inputs = _action_input_defaults(action)
    inputs.update(provided_inputs)
    env: dict[str, str] = {}
    for name, value in step.get("env", {}).items():
        env[str(name)] = _resolve_expression(str(value), inputs=inputs, github=github)
    return env


def _write_event_payload(path: Path, *, private: bool) -> None:
    path.write_text(
        json.dumps({"repository": {"private": private}}, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _invoke_composite_runtime_step(
    *,
    action_repo: Path,
    action_python: Path,
    consumer_dir: Path,
    output_path: Path,
) -> None:
    action = _load_action(action_repo)
    step = _runtime_step(action)
    github = {
        "action_ref": "template-action-boundary-e2e",
        "action_repository": "reponomics/reponomics-dashboard-action",
        "token": "ghp_runtime",
    }
    runtime_env = _resolve_runtime_env(
        action,
        provided_inputs={
            "mode": "update-docs",
            "github-token": github["token"],
        },
        github=github,
    )
    event_path = consumer_dir / ".e2e-github-event.json"
    _write_event_payload(event_path, private=True)
    env = os.environ.copy()
    env.update(runtime_env)
    env.update(
        {
            "GITHUB_ACTION_PATH": action_repo.as_posix(),
            "GITHUB_EVENT_PATH": event_path.as_posix(),
            "GITHUB_EVENT_REPOSITORY_PRIVATE": "true",
            "GITHUB_OUTPUT": output_path.as_posix(),
            "PATH": f"{action_python.parent.as_posix()}{os.pathsep}{env.get('PATH', '')}",
        }
    )
    _run([step["shell"], "-c", step["run"]], cwd=consumer_dir, env=env)


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


def _read_dashboard_json_payload(consumer_dir: Path, asset_name: str) -> dict[str, object]:
    asset_path = consumer_dir / "docs" / "assets" / asset_name
    if not asset_path.is_file():
        raise TemplateConsumerE2EError(f"dashboard payload asset missing: {asset_name}")
    payload = json.loads(asset_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TemplateConsumerE2EError(f"dashboard payload asset is not an object: {asset_name}")
    return payload


def _assert_chunked_dashboard_payload(profile_name: str, payload: Mapping[str, object]) -> None:
    chunks = payload.get("chunks")
    summary = payload.get("summary")
    chunk_count = payload.get("chunk_count")
    if (
        payload.get("version") != 2
        or not isinstance(summary, (dict, str))
        or not isinstance(chunks, dict)
        or not isinstance(chunk_count, int)
        or chunk_count != len(chunks)
    ):
        raise TemplateConsumerE2EError(f"{profile_name}: dashboard chunk object missing")


def _assert_successful_profile(consumer_dir: Path, profile: ConsumerProfile) -> None:
    outputs = _read_github_output(consumer_dir / ".e2e-github-output")
    if outputs.get("data-mode") != profile.expected_data_mode:
        raise TemplateConsumerE2EError(
            f"{profile.name}: data-mode={outputs.get('data-mode')!r}"
        )
    if outputs.get("publish-pages") != str(profile.expected_publish_pages).lower():
        raise TemplateConsumerE2EError(
            f"{profile.name}: publish-pages={outputs.get('publish-pages')!r}"
        )

    dashboard_path = consumer_dir / "docs" / "index.html"
    if not dashboard_path.is_file():
        raise TemplateConsumerE2EError(f"{profile.name}: dashboard HTML was not rendered")
    dashboard = dashboard_path.read_text(encoding="utf-8")
    if profile.expected_data_mode == "encrypted":
        if "encrypted-dashboard-data" not in dashboard or "export-manifest" not in dashboard:
            raise TemplateConsumerE2EError(f"{profile.name}: encrypted dashboard markers missing")
        encrypted_payload = _read_dashboard_json_payload(
            consumer_dir,
            "encrypted-dashboard-data.json",
        )
        _assert_chunked_dashboard_payload(profile.name, encrypted_payload)
        if not list((consumer_dir / "docs" / "assets").glob("export-data-*.enc")):
            raise TemplateConsumerE2EError(f"{profile.name}: encrypted export asset missing")
    elif "encrypted-dashboard-data" in dashboard or "encrypted-payload" in dashboard:
        raise TemplateConsumerE2EError(f"{profile.name}: plaintext dashboard contains encrypted data")
    else:
        if "reponomics-dashboard-data" not in dashboard or "dashboardPayload" in dashboard:
            raise TemplateConsumerE2EError(f"{profile.name}: plaintext dashboard markers missing")
        plaintext_payload = _read_dashboard_json_payload(
            consumer_dir,
            "dashboard-data.json",
        )
        _assert_chunked_dashboard_payload(profile.name, plaintext_payload)

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
            _write_setup_config(
                consumer_dir,
                data_mode=profile.data_mode,
                publish_pages_dashboard=profile.expected_publish_pages,
                publish_readme_dashboard=profile.generate_readme,
            )
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


def run_composite_boundary_e2e(
    *,
    template_dir: Path,
    action_repo: Path,
    action_python: Path,
    keep_temp: bool = False,
) -> None:
    template_dir = _absolute_path(template_dir)
    action_repo = _absolute_path(action_repo).resolve()
    action_python = _absolute_path(action_python)
    temp_root = Path(tempfile.mkdtemp(prefix="template-action-boundary-e2e-"))
    try:
        consumer_dir = temp_root / "repo"
        remote_dir = temp_root / "remote.git"
        _copy_template(template_dir.resolve(), consumer_dir)
        _write_setup_config(consumer_dir)
        _init_consumer_git_repo(consumer_dir, remote_dir)
        stale_doc = consumer_dir / "docs" / "reponomics" / "README.md"
        stale_doc.write_text("stale managed docs\n", encoding="utf-8")
        _run(["git", "add", stale_doc.as_posix()], cwd=consumer_dir)
        _run(["git", "commit", "-m", "test: stale managed docs"], cwd=consumer_dir)

        output_path = consumer_dir / ".e2e-composite-github-output"
        _invoke_composite_runtime_step(
            action_repo=action_repo,
            action_python=action_python,
            consumer_dir=consumer_dir,
            output_path=output_path,
        )
        outputs = _read_github_output(output_path)
        if outputs.get("docs-action-version") is None:
            raise TemplateConsumerE2EError("Composite boundary did not write docs-action-version")
        if outputs.get("update-docs-state") not in {"written", "updated", "unchanged"}:
            raise TemplateConsumerE2EError(
                f"Unexpected update-docs-state from composite boundary: {outputs.get('update-docs-state')!r}"
            )
        if (consumer_dir / "docs" / "reponomics" / "README.md").read_text(
            encoding="utf-8"
        ) == "stale managed docs\n":
            raise TemplateConsumerE2EError("Composite boundary did not refresh managed docs")
        print("Template action boundary e2e passed: update-docs composite runtime step")
    finally:
        if keep_temp:
            print(f"Kept composite boundary temp directory: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


def runtime_step_contract_error(action: dict) -> str:
    """Return the runtime-step contract error for tests, or an empty string."""
    try:
        _assert_runtime_step_contract(_runtime_step(deepcopy(action)))
    except TemplateConsumerE2EError as exc:
        return str(exc)
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-dir", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--action-repo", type=Path, default=DEFAULT_ACTION_REPO)
    parser.add_argument(
        "--action-python",
        type=Path,
        default=DEFAULT_ACTION_PYTHON,
    )
    parser.add_argument(
        "--composite-boundary",
        action="store_true",
        help="Run only the composite action.yml runtime-step boundary check.",
    )
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()
    if args.composite_boundary:
        run_composite_boundary_e2e(
            template_dir=args.template_dir,
            action_repo=args.action_repo,
            action_python=args.action_python,
            keep_temp=args.keep_temp,
        )
        return
    run_e2e(
        template_dir=args.template_dir,
        action_repo=args.action_repo,
        action_python=args.action_python,
        keep_temp=args.keep_temp,
    )


if __name__ == "__main__":
    main()
