"""Run candidate action checks against current and minimum compatible templates."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

try:
    from scripts.repo_paths import find_repo_root
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_paths import find_repo_root  # type: ignore[import-not-found,no-redef]


ROOT = find_repo_root(Path(__file__))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import template_consumer_e2e  # noqa: E402
from scripts import template_contract  # noqa: E402
from scripts import template_provenance  # noqa: E402


DEFAULT_ACTION_REPO = ROOT
DEFAULT_ACTION_PYTHON = DEFAULT_ACTION_REPO / "venv" / "bin" / "python"
DEFAULT_CURRENT_TEMPLATE = ROOT / "dist" / "template"
ACTION_REPOSITORY = template_contract.ACTION_REPOSITORY
RETAINED_MIGRATION_FIXTURE = ROOT / "tests" / "fixtures" / "compat_v2"

RETAINED_MIGRATION_HELPER = r"""
from __future__ import annotations

import csv
import json
import os
import shutil
import sys
from pathlib import Path

action_repo = Path(os.environ["E2E_ACTION_REPO"]).resolve()
work_root = Path(os.environ["E2E_WORK_ROOT"]).resolve()
template_name = os.environ["E2E_TEMPLATE_NAME"]
template_version = os.environ["E2E_TEMPLATE_VERSION"]
fixture_source = Path(os.environ["E2E_RETAINED_FIXTURE"]).resolve()

sys.path.insert(0, action_repo.as_posix())

from dashboard_action import run  # noqa: E402

OLD_KEY = "DASHBOARD_SECRET_DO_NOT_REPLACE_0123456789"
NEXT_KEY = "DASHBOARD_NEXT_SECRET_DO_NOT_REPLACE_9876543210"


def copy_fixture(label: str) -> Path:
    target = work_root / label
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(fixture_source, target)
    return target


def config_for(root: Path, fixture: Path, mode: str, *, next_secret: str = ""):
    return run.RuntimeConfig(
        mode=mode,
        collection_token="ghp_collection",
        use_github_app=False,
        github_token="ghp_runtime",
        dashboard_secret=OLD_KEY,
        dashboard_next_secret=next_secret,
        comparison_secret="",
        data_mode="encrypted",
        repo_is_public=False,
        config_path=fixture / "config.yaml",
        data_dir=fixture / "data",
        retention_days=90,
        auto_doctor_every_n_days=0,
        artifact_run_id="",
        publish_pages_requested=True,
        generate_readme=False,
        pages_index_path=root / "docs" / mode / "index.html",
        readme_path=root / f"README-{mode}.md",
        incident_confirm_mode="",
        incident_confirm_purge="",
        incident_confirm_next_secret="",
        incident_confirm_irreversible="",
        action_ref=f"template-compat-{template_version}",
        action_repository="reponomics/reponomics-dashboard-action",
    )


def assert_current_schema(data_dir: Path) -> None:
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != run.storage.SCHEMA_VERSION:
        raise AssertionError(
            f"{template_name}: retained fixture did not migrate to schema "
            + run.storage.SCHEMA_VERSION
        )
    with (data_dir / "repo-metrics.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not any(row.get("repo") == "demo/reponomics" for row in rows):
        raise AssertionError(f"{template_name}: retained repo-metrics row was lost")
    if rows[0].get("repo_id", None) != "":
        raise AssertionError(f"{template_name}: repo-metrics header was not canonicalized")


def run_publish_fixture() -> None:
    fixture = copy_fixture("publish")
    root = work_root / "publish-run"
    root.mkdir(parents=True, exist_ok=True)
    config = config_for(root, fixture, "publish")
    before_config = config.config_path.read_text(encoding="utf-8")
    previous_cwd = Path.cwd()
    os.chdir(root)
    try:
        run.validate_config(config)
        run.run_publish(config, restore_artifact=False)
    finally:
        os.chdir(previous_cwd)
    if config.config_path.read_text(encoding="utf-8") != before_config:
        raise AssertionError(f"{template_name}: publish rewrote config.yaml")
    if not config.pages_index_path.is_file():
        raise AssertionError(f"{template_name}: publish did not render dashboard")
    assert_current_schema(config.data_dir)


def run_collect_fixture() -> None:
    fixture = copy_fixture("collect")
    root = work_root / "collect-run"
    root.mkdir(parents=True, exist_ok=True)
    config = config_for(root, fixture, "collect")
    before_config = config.config_path.read_text(encoding="utf-8")
    previous_cwd = Path.cwd()
    os.chdir(root)
    try:
        run.validate_config(config)
        run.run_collect(config, restore_artifact=False, execute_collect=False)
    finally:
        os.chdir(previous_cwd)
    if config.config_path.read_text(encoding="utf-8") != before_config:
        raise AssertionError(f"{template_name}: collect rewrote config.yaml")
    if not (root / ".dashboard-data-artifact" / "dashboard-data.enc").is_file():
        raise AssertionError(f"{template_name}: collect did not write encrypted artifact")
    assert_current_schema(config.data_dir)


def run_rotate_key_fixture() -> None:
    fixture = copy_fixture("rotate")
    root = work_root / "rotate-run"
    root.mkdir(parents=True, exist_ok=True)
    seed_config = config_for(root, fixture, "rotate-key", next_secret=NEXT_KEY)
    before_config = seed_config.config_path.read_text(encoding="utf-8")

    previous_cwd = Path.cwd()
    os.chdir(root)
    try:
        run._patch_runtime_paths(seed_config)  # noqa: SLF001
        run._set_runtime_env(seed_config)  # noqa: SLF001
        encrypted_path = root / ".dashboard-data-artifact" / "dashboard-data.enc"
        run.crypto_artifact.encrypt(seed_config.data_dir, encrypted_path, "DASHBOARD_SECRET_DO_NOT_REPLACE")
        for path in seed_config.data_dir.iterdir():
            path.unlink()
        (seed_config.data_dir / "dashboard-data.enc").write_text(
            encrypted_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        rotated = config_for(root, fixture, "rotate-key", next_secret=NEXT_KEY)
        run.validate_config(rotated)
        run.run_rotate_key(rotated, restore_artifact=False)
        if rotated.config_path.read_text(encoding="utf-8") != before_config:
            raise AssertionError(f"{template_name}: rotate-key rewrote config.yaml")

        for path in rotated.data_dir.iterdir():
            path.unlink()
        (rotated.data_dir / "dashboard-data.enc").write_text(
            encrypted_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        os.environ["DASHBOARD_SECRET_DO_NOT_REPLACE"] = NEXT_KEY
        run.crypto_artifact.decrypt(
            rotated.data_dir / "dashboard-data.enc",
            rotated.data_dir,
            "DASHBOARD_SECRET_DO_NOT_REPLACE",
        )
        assert_current_schema(rotated.data_dir)
    finally:
        os.chdir(previous_cwd)


run.version_status._fetch_releases = lambda: []
work_root.mkdir(parents=True, exist_ok=True)
os.environ["GITHUB_OUTPUT"] = (work_root / ".github-output").as_posix()

run_publish_fixture()
run_collect_fixture()
run_rotate_key_fixture()
print(f"Retained migration fixture passed: {template_name} ({template_version})")
"""


class TemplateCompatibilityError(RuntimeError):
    """Raised when a generated template release is incompatible with the candidate action."""


@dataclass(frozen=True)
class GeneratedTemplate:
    name: str
    repo_dir: Path
    template_version: str
    source_commit: str


def _load_mapping(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise TemplateCompatibilityError(f"{path} must contain a YAML mapping")
    return payload


def _absolute_path(path: Path) -> Path:
    """Make a path cwd-relative without resolving virtualenv symlinks."""
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _command_output(
    args: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> str:
    try:
        return subprocess.check_output(
            args,
            cwd=cwd,
            env=env,
            stderr=subprocess.STDOUT,
            text=True,
        ).strip()
    except subprocess.CalledProcessError as exc:
        output = exc.output.strip()
        details = f": {output}" if output else ""
        raise TemplateCompatibilityError(f"Command failed: {' '.join(args)}{details}") from exc


def _git_output(args: list[str], *, cwd: Path = ROOT) -> str:
    return _command_output(args, cwd=cwd)


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":  # pragma: no cover - Windows compatibility path
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _install_isolated_python_env(
    *,
    source_dir: Path,
    venv_dir: Path,
    base_python: Path,
    label: str,
) -> Path:
    print(f"Creating isolated {label} environment: {venv_dir}")
    _command_output([base_python.as_posix(), "-m", "venv", venv_dir.as_posix()])
    python = _venv_python(venv_dir)
    _command_output([python.as_posix(), "-m", "pip", "install", "--upgrade", "pip"])
    _command_output(
        [python.as_posix(), "-m", "pip", "install", "-e", source_dir.as_posix()],
        cwd=source_dir,
    )
    return python


def _source_commit() -> str:
    return _git_output(["git", "rev-parse", "HEAD"])


def _ensure_git_ref(template_ref: str) -> str:
    rev_parse_args = ["git", "rev-parse", "--verify", f"{template_ref}^{{commit}}"]
    try:
        return _git_output(rev_parse_args)
    except TemplateCompatibilityError:
        _git_output(["git", "fetch", "--tags", "origin"])
        return _git_output(rev_parse_args)


def _checkout_ref(template_ref: str, destination: Path) -> str:
    source_commit = _ensure_git_ref(template_ref)
    _git_output(
        [
            "git",
            "worktree",
            "add",
            "--detach",
            destination.as_posix(),
            template_ref,
        ]
    )
    return source_commit


def _remove_worktree(path: Path) -> None:
    if not path.exists():
        return
    subprocess.run(
        ["git", "-C", ROOT.as_posix(), "worktree", "remove", path.as_posix()],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _current_template(
    template_dir: Path,
    *,
    contract: template_contract.TemplateContract,
) -> GeneratedTemplate:
    if not template_dir.exists():
        raise TemplateCompatibilityError(
            f"Current generated template does not exist: {template_dir}"
        )
    provenance = template_provenance.verify_template_provenance(
        template_dir,
        contract=contract,
    )
    template_version = str(provenance.get("template", {}).get("version") or "")
    if template_version != contract.template_version:
        raise TemplateCompatibilityError(
            "current generated template provenance does not match template-contract.yml"
        )
    return GeneratedTemplate(
        name=f"current template {contract.template_version}",
        repo_dir=template_dir,
        template_version=contract.template_version,
        source_commit=_source_commit(),
    )


def _build_template_from_ref(
    protected_ref: template_contract.ProtectedTemplateRef,
    *,
    base_python: Path,
    work_root: Path,
) -> GeneratedTemplate:
    source_dir = work_root / "source"
    output_dir = work_root / "generated-template"
    source_commit = _checkout_ref(protected_ref.ref, source_dir)
    if source_commit != protected_ref.source_commit:
        raise TemplateCompatibilityError(
            (
                f"{protected_ref.ref}: expected source commit "
                + f"{protected_ref.source_commit}, got {source_commit}"
            )
        )

    source_contract = _load_mapping(source_dir / "template-contract.yml")
    source_version = str(source_contract.get("template_version") or "")
    if source_version != protected_ref.template_version:
        raise TemplateCompatibilityError(
            (
                f"{protected_ref.ref}: contract version {source_version!r} does not "
                + f"match protected version {protected_ref.template_version}"
            )
        )

    build_python = _install_isolated_python_env(
        source_dir=source_dir,
        venv_dir=work_root / "template-build-runtime",
        base_python=base_python,
        label=f"{protected_ref.ref} template build",
    )
    _git_output(
        [
            build_python.as_posix(),
            (source_dir / "scripts" / "build_template.py").as_posix(),
            "--output",
            output_dir.as_posix(),
        ],
        cwd=source_dir,
    )
    provenance = _load_mapping(output_dir / ".reponomics" / "template-provenance.json")
    provenance_template_version = str(provenance.get("template", {}).get("version") or "")
    if provenance_template_version != protected_ref.template_version:
        raise TemplateCompatibilityError(
            f"{protected_ref.ref}: generated provenance does not match template version"
        )
    if str(provenance.get("source", {}).get("commit") or "") != protected_ref.source_commit:
        raise TemplateCompatibilityError(
            f"{protected_ref.ref}: generated provenance does not match source commit"
        )

    return GeneratedTemplate(
        name=protected_ref.ref,
        repo_dir=output_dir,
        template_version=protected_ref.template_version,
        source_commit=protected_ref.source_commit,
    )


def _current_action_inputs(action_repo: Path) -> set[str]:
    action_path = action_repo / "action.yml"
    action = _load_mapping(action_path)
    inputs = action.get("inputs")
    if not isinstance(inputs, dict):
        raise TemplateCompatibilityError(f"{action_path} must declare action inputs")
    return {str(name) for name in inputs}


def _workflow_documents(repo_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    workflow_dir = repo_dir / ".github" / "workflows"
    if not workflow_dir.is_dir():
        raise TemplateCompatibilityError(f"{repo_dir}: missing .github/workflows")
    documents: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(workflow_dir.glob("*.yml")) + sorted(workflow_dir.glob("*.yaml")):
        payload = _load_mapping(path)
        documents.append((path, payload))
    return documents


def _iter_steps(value: Any) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if isinstance(value.get("steps"), list):
            steps.extend(step for step in value["steps"] if isinstance(step, dict))
        for child in value.values():
            steps.extend(_iter_steps(child))
    elif isinstance(value, list):
        for child in value:
            steps.extend(_iter_steps(child))
    return steps


def _assert_template_workflow_inputs_supported(
    generated_template: GeneratedTemplate,
    *,
    action_inputs: set[str],
) -> None:
    wrapper_path = (
        generated_template.repo_dir / template_contract.TEMPLATE_ACTION_WRAPPER_PATH
    )
    if not wrapper_path.is_file():
        _assert_legacy_template_workflow_inputs_supported(
            generated_template,
            action_inputs=action_inputs,
        )
        return
    wrapper = _load_mapping(wrapper_path)
    forwarded: set[str] = set()
    seen_reponomics_step = False
    for step in _iter_steps(wrapper):
        uses = str(step.get("uses") or "")
        if not uses.startswith(f"{ACTION_REPOSITORY}@"):
            continue
        seen_reponomics_step = True
        with_payload = step.get("with") or {}
        if not isinstance(with_payload, dict):
            continue
        forwarded.update(str(name) for name in with_payload)
    if not seen_reponomics_step:
        raise TemplateCompatibilityError(
            f"{generated_template.name}: local wrapper does not invoke {ACTION_REPOSITORY}"
        )
    missing = forwarded - action_inputs
    if missing:
        raise TemplateCompatibilityError(
            (
                f"{generated_template.name}: local wrapper forwards input(s) no longer "
                + f"declared by action.yml: {', '.join(sorted(missing))}"
            )
        )


def _assert_legacy_template_workflow_inputs_supported(
    generated_template: GeneratedTemplate,
    *,
    action_inputs: set[str],
) -> None:
    missing: dict[str, set[str]] = {}
    seen_reponomics_step = False
    for path, workflow in _workflow_documents(generated_template.repo_dir):
        for step in _iter_steps(workflow):
            uses = str(step.get("uses") or "")
            if not uses.startswith(f"{ACTION_REPOSITORY}@"):
                continue
            seen_reponomics_step = True
            with_payload = step.get("with") or {}
            if not isinstance(with_payload, dict):
                continue
            unsupported = {
                str(name) for name in with_payload if str(name) not in action_inputs
            }
            if unsupported:
                missing[path.relative_to(generated_template.repo_dir).as_posix()] = unsupported
    if not seen_reponomics_step:
        raise TemplateCompatibilityError(
            f"{generated_template.name}: no generated workflow invokes {ACTION_REPOSITORY}"
        )
    if missing:
        details = "; ".join(
            f"{path}: {', '.join(sorted(inputs))}" for path, inputs in sorted(missing.items())
        )
        raise TemplateCompatibilityError(
            (
                f"{generated_template.name}: generated workflows pass inputs no longer "
                + f"declared by action.yml: {details}"
            )
        )


def _run_generated_template(
    generated_template: GeneratedTemplate,
    *,
    action_repo: Path,
    action_python: Path,
    action_inputs: set[str],
    compat_root: Path,
    keep_temp: bool,
) -> None:
    print(
        "Checking template compatibility: "
        + f"{generated_template.name} "
        + f"({generated_template.template_version}, {generated_template.source_commit[:7]})"
    )
    _assert_template_workflow_inputs_supported(
        generated_template,
        action_inputs=action_inputs,
    )
    template_consumer_e2e.run_e2e(
        template_dir=generated_template.repo_dir,
        action_repo=action_repo,
        action_python=action_python,
        keep_temp=keep_temp,
    )
    _run_retained_migration_fixture(
        generated_template,
        action_repo=action_repo,
        action_python=action_python,
        compat_root=compat_root,
        keep_temp=keep_temp,
    )


def _run_retained_migration_fixture(
    generated_template: GeneratedTemplate,
    *,
    action_repo: Path,
    action_python: Path,
    compat_root: Path,
    keep_temp: bool,
) -> None:
    if not RETAINED_MIGRATION_FIXTURE.is_dir():
        raise TemplateCompatibilityError(
            f"Retained migration fixture is missing: {RETAINED_MIGRATION_FIXTURE}"
        )
    work_root = Path(tempfile.mkdtemp(prefix="retained-", dir=compat_root))
    helper = work_root / "run_retained_migration_fixture.py"
    helper.write_text(RETAINED_MIGRATION_HELPER, encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "E2E_ACTION_REPO": action_repo.as_posix(),
            "E2E_WORK_ROOT": (work_root / "work").as_posix(),
            "E2E_TEMPLATE_NAME": generated_template.name,
            "E2E_TEMPLATE_VERSION": generated_template.template_version,
            "E2E_RETAINED_FIXTURE": RETAINED_MIGRATION_FIXTURE.as_posix(),
        }
    )
    try:
        output = _command_output(
            [action_python.as_posix(), helper.as_posix()],
            cwd=action_repo,
            env=env,
        )
        if output:
            print(output)
        if keep_temp:
            print(f"Kept retained migration fixture work tree: {work_root}")
    finally:
        if not keep_temp:
            shutil.rmtree(work_root, ignore_errors=True)


def run_compatibility_checks(
    *,
    current_template_dir: Path,
    action_repo: Path,
    action_python: Path,
    extra_template_refs: list[str] | None = None,
    keep_temp: bool = False,
) -> None:
    contract = template_contract.validate_local_contract(ROOT)
    action_repo = _absolute_path(action_repo).resolve()
    base_python = _absolute_path(action_python)
    action_inputs = _current_action_inputs(action_repo)
    failures: list[str] = []
    checked = 0
    compat_root = Path(tempfile.mkdtemp(prefix="reponomics-template-compat-run-"))

    try:
        isolated_action_python: Path | None = None
        try:
            isolated_action_python = _install_isolated_python_env(
                source_dir=action_repo,
                venv_dir=compat_root / "candidate-action-runtime",
                base_python=base_python,
                label="candidate action runtime",
            )
            _run_generated_template(
                _current_template(current_template_dir.resolve(), contract=contract),
                action_repo=action_repo,
                action_python=isolated_action_python,
                action_inputs=action_inputs,
                compat_root=compat_root,
                keep_temp=keep_temp,
            )
            checked += 1
        except Exception as exc:
            failures.append(f"current template: {exc}")

        protected_refs = list(contract.protected_template_refs)
        for extra_ref in extra_template_refs or []:
            protected_refs.append(
                template_contract.ProtectedTemplateRef(
                    ref=extra_ref,
                    template_version=extra_ref.removeprefix("reponomics-dashboard-v"),
                    source_commit=_ensure_git_ref(extra_ref),
                    status="required",
                )
            )

        for protected_ref in protected_refs:
            work_root = Path(tempfile.mkdtemp(prefix="template-", dir=compat_root))
            try:
                generated_template = _build_template_from_ref(
                    protected_ref,
                    base_python=base_python,
                    work_root=work_root,
                )
                if isolated_action_python is None:
                    raise TemplateCompatibilityError(
                        "candidate action runtime environment was not created"
                    )
                _run_generated_template(
                    generated_template,
                    action_repo=action_repo,
                    action_python=isolated_action_python,
                    action_inputs=action_inputs,
                    compat_root=compat_root,
                    keep_temp=keep_temp,
                )
                checked += 1
                if keep_temp:
                    print(f"Kept compatibility work tree: {work_root}")
            except Exception as exc:
                failures.append(f"{protected_ref.ref}: {exc}")
            finally:
                if not keep_temp:
                    _remove_worktree(work_root / "source")
                    shutil.rmtree(work_root, ignore_errors=True)

        if failures:
            raise TemplateCompatibilityError("\n".join(failures))
        print(f"Template compatibility checks passed: {checked} template(s)")
    finally:
        if keep_temp:
            print(f"Kept compatibility temp root: {compat_root}")
        else:
            shutil.rmtree(compat_root, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--current-template-dir",
        type=Path,
        default=DEFAULT_CURRENT_TEMPLATE,
        help="Current generated template directory, usually dist/template.",
    )
    parser.add_argument(
        "--template-ref",
        action="append",
        dest="template_refs",
        help="Additional template release ref to test; may be passed multiple times.",
    )
    parser.add_argument("--action-repo", type=Path, default=DEFAULT_ACTION_REPO)
    parser.add_argument("--action-python", type=Path, default=DEFAULT_ACTION_PYTHON)
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()
    run_compatibility_checks(
        current_template_dir=args.current_template_dir,
        action_repo=args.action_repo,
        action_python=args.action_python,
        extra_template_refs=args.template_refs,
        keep_temp=args.keep_temp,
    )


if __name__ == "__main__":
    try:
        main()
    except TemplateCompatibilityError as exc:
        print(f"Template compatibility failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
