"""Run candidate action compatibility checks against generated template releases."""

from __future__ import annotations

import argparse
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


DEFAULT_ACTION_REPO = ROOT
DEFAULT_ACTION_PYTHON = DEFAULT_ACTION_REPO / "venv" / "bin" / "python"
DEFAULT_CONTRACT_PATH = ROOT / "template-contract.yml"
ACTION_REPOSITORY = "reponomics/reponomics-dashboard-action"


class TemplateCompatibilityError(RuntimeError):
    """Raised when a generated template release is incompatible with the candidate action."""


@dataclass(frozen=True)
class GeneratedTemplateRelease:
    template_ref: str
    source_commit: str
    repo_dir: Path
    template_version: str
    compatibility_line: str

    @property
    def name(self) -> str:
        return self.template_ref


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise TemplateCompatibilityError(f"{path} must contain a YAML mapping")
    return payload


def default_template_ref(contract_path: Path = DEFAULT_CONTRACT_PATH) -> str:
    contract = _load_yaml(contract_path)
    template_version = str(contract.get("template_version") or "")
    if not template_version:
        raise TemplateCompatibilityError(f"{contract_path}: missing template_version")
    return f"reponomics-dashboard-v{template_version}"


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _ensure_git_ref(template_ref: str) -> str:
    rev_parse = _git("rev-parse", "--verify", f"{template_ref}^{{commit}}", check=False)
    if rev_parse.returncode != 0:
        subprocess.run(
            ["git", "-C", str(ROOT), "fetch", "--tags", "--force", "origin"],
            check=True,
        )
        rev_parse = _git("rev-parse", "--verify", f"{template_ref}^{{commit}}", check=False)
    if rev_parse.returncode != 0:
        raise TemplateCompatibilityError(
            f"Could not resolve template ref {template_ref!r}: {rev_parse.stderr.strip()}"
        )
    return rev_parse.stdout.strip()


def _checkout_ref(template_ref: str, destination: Path) -> str:
    source_commit = _ensure_git_ref(template_ref)
    subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "worktree",
            "add",
            "--detach",
            "--force",
            str(destination),
            template_ref,
        ],
        check=True,
    )
    return source_commit


def _remove_worktree(path: Path) -> None:
    if not path.exists():
        return
    subprocess.run(
        ["git", "-C", str(ROOT), "worktree", "remove", "--force", str(path)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _build_template_from_ref(
    template_ref: str,
    *,
    action_python: Path,
    work_root: Path,
) -> GeneratedTemplateRelease:
    source_dir = work_root / "source"
    output_dir = work_root / "generated-template"
    source_commit = _checkout_ref(template_ref, source_dir)
    source_contract = _load_yaml(source_dir / "template-contract.yml")
    subprocess.run(
        [
            str(action_python),
            str(source_dir / "scripts" / "build_template.py"),
            "--output",
            str(output_dir),
        ],
        cwd=source_dir,
        check=True,
    )
    provenance = _load_yaml(output_dir / ".reponomics" / "template-provenance.json")
    template_version = str(source_contract.get("template_version") or "")
    compatibility_major = str(source_contract.get("compatible_action_major"))
    if str(provenance.get("template", {}).get("version") or "") != template_version:
        raise TemplateCompatibilityError(
            f"{template_ref}: generated provenance does not match source template version"
        )
    if str(provenance.get("source", {}).get("commit") or "") != source_commit:
        raise TemplateCompatibilityError(
            f"{template_ref}: generated provenance does not match source commit"
        )
    return GeneratedTemplateRelease(
        template_ref=template_ref,
        source_commit=source_commit,
        repo_dir=output_dir,
        template_version=template_version,
        compatibility_line=f"v{compatibility_major}",
    )


def _current_action_inputs(action_repo: Path) -> set[str]:
    action_path = action_repo / "action.yml"
    action = yaml.safe_load(action_path.read_text(encoding="utf-8")) or {}
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
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(payload, dict):
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
    template: GeneratedTemplateRelease,
    *,
    action_inputs: set[str],
) -> None:
    missing: dict[str, set[str]] = {}
    seen_reponomics_step = False
    for path, workflow in _workflow_documents(template.repo_dir):
        for step in _iter_steps(workflow):
            uses = str(step.get("uses") or "")
            if not uses.startswith(f"{ACTION_REPOSITORY}@"):
                continue
            seen_reponomics_step = True
            with_payload = step.get("with") or {}
            if not isinstance(with_payload, dict):
                continue
            unsupported = {str(name) for name in with_payload if str(name) not in action_inputs}
            if unsupported:
                missing[path.relative_to(template.repo_dir).as_posix()] = unsupported
    if not seen_reponomics_step:
        raise TemplateCompatibilityError(
            f"{template.name}: no generated workflow invokes {ACTION_REPOSITORY}"
        )
    if missing:
        details = "; ".join(
            f"{path}: {', '.join(sorted(inputs))}" for path, inputs in sorted(missing.items())
        )
        raise TemplateCompatibilityError(
            f"{template.name}: generated workflows pass inputs no longer declared by action.yml: {details}"
        )


def run_template_ref(
    template_ref: str,
    *,
    action_repo: Path,
    action_python: Path,
    keep_temp: bool = False,
) -> None:
    work_root = Path(tempfile.mkdtemp(prefix="reponomics-template-compat-"))
    try:
        template = _build_template_from_ref(
            template_ref,
            action_python=action_python,
            work_root=work_root,
        )
        message = "Checking template compatibility: {ref} ({version}, {commit})".format(
            ref=template.template_ref,
            version=template.template_version,
            commit=template.source_commit[:7],
        )
        print(message)
        _assert_template_workflow_inputs_supported(
            template,
            action_inputs=_current_action_inputs(action_repo),
        )
        template_consumer_e2e.run_e2e(
            template_dir=template.repo_dir,
            action_repo=action_repo,
            action_python=action_python,
            keep_temp=keep_temp,
        )
        if keep_temp:
            print(f"Kept compatibility work tree: {work_root}")
    finally:
        if keep_temp:
            return
        _remove_worktree(work_root / "source")
        shutil.rmtree(work_root, ignore_errors=True)


def run_compatibility_checks(
    *,
    template_refs: list[str],
    action_repo: Path,
    action_python: Path,
    keep_temp: bool = False,
) -> None:
    failures: list[str] = []
    for template_ref in template_refs:
        try:
            run_template_ref(
                template_ref,
                action_repo=action_repo.resolve(),
                action_python=action_python.resolve(),
                keep_temp=keep_temp,
            )
        except Exception as exc:
            failures.append(f"{template_ref}: {exc}")
    if failures:
        raise TemplateCompatibilityError("\n".join(failures))
    print(f"Template compatibility checks passed: {len(template_refs)} template ref(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template-ref",
        action="append",
        dest="template_refs",
        help="Template release ref to test; may be passed multiple times.",
    )
    parser.add_argument("--action-repo", type=Path, default=DEFAULT_ACTION_REPO)
    parser.add_argument("--action-python", type=Path, default=DEFAULT_ACTION_PYTHON)
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()
    template_refs = args.template_refs or [default_template_ref()]
    run_compatibility_checks(
        template_refs=template_refs,
        action_repo=args.action_repo,
        action_python=args.action_python,
        keep_temp=args.keep_temp,
    )


if __name__ == "__main__":
    main()
