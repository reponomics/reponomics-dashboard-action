"""Scan GitHub workflows for Reponomics Dashboard action refs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

try:
    from scripts.repo_paths import find_repo_root
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_paths import find_repo_root  # type: ignore[import-not-found,no-redef]


ROOT = find_repo_root(Path(__file__))
DEFAULT_ACTION_REPOSITORY = "reponomics/reponomics-dashboard-action"
DEFAULT_WORKFLOW_DIR = Path(".github") / "workflows"
WORKFLOW_SUFFIXES = {".yml", ".yaml"}

RefKind = Literal["major-tag", "minor-tag", "exact-tag", "sha", "other"]
SummaryKind = Literal["major-tag", "minor-tag", "exact-tag", "sha", "other", "mixed", "none"]

MAJOR_TAG_RE = re.compile(r"^v(0|[1-9]\d*)$")
MINOR_TAG_RE = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)$")
EXACT_TAG_PATTERN = (
    r"^v(0|[1-9]\d*)\."
    + r"(0|[1-9]\d*)\."
    + r"(0|[1-9]\d*)"
    + r"(?:-[0-9A-Za-z.-]+)?"
    + r"(?:\+[0-9A-Za-z.-]+)?$"
)
EXACT_TAG_RE = re.compile(EXACT_TAG_PATTERN)
FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class ActionRefScanError(RuntimeError):
    """Raised when workflow action ref scanning fails."""


@dataclass(frozen=True)
class ActionUse:
    workflow_path: str
    workflow_name: str
    job_id: str
    location: str
    uses: str
    ref: str
    step_name: str = ""


@dataclass(frozen=True)
class ClassifiedActionUse:
    workflow_path: str
    workflow_name: str
    job_id: str
    location: str
    uses: str
    ref: str
    ref_kind: RefKind
    step_name: str = ""


@dataclass(frozen=True)
class WorkflowRefSummary:
    workflow_path: str
    workflow_name: str
    classification: SummaryKind
    refs: tuple[str, ...]
    action_uses: tuple[ClassifiedActionUse, ...]


@dataclass(frozen=True)
class ActionRefReport:
    action_repository: str
    workflow_dir: str
    classification: SummaryKind
    refs: tuple[str, ...]
    workflows: tuple[WorkflowRefSummary, ...]


def classify_ref(ref: str) -> RefKind:
    """Classify a single GitHub Actions ref."""
    value = ref.strip()
    if FULL_SHA_RE.fullmatch(value):
        return "sha"
    if MAJOR_TAG_RE.fullmatch(value):
        return "major-tag"
    if MINOR_TAG_RE.fullmatch(value):
        return "minor-tag"
    if EXACT_TAG_RE.fullmatch(value):
        return "exact-tag"
    return "other"


def summarize_refs(refs: list[str] | tuple[str, ...]) -> SummaryKind:
    """Summarize a group of refs without hiding inconsistencies."""
    unique_refs = sorted(set(refs))
    if not unique_refs:
        return "none"
    if len(unique_refs) > 1:
        return "mixed"
    return classify_ref(unique_refs[0])


def scan_workflow_file(
    workflow_path: Path,
    *,
    action_repository: str = DEFAULT_ACTION_REPOSITORY,
    root: Path | None = None,
) -> tuple[str, list[ActionUse]]:
    """Return the workflow name and matching action uses from one workflow file."""
    root = root or workflow_path.parent
    try:
        payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ActionRefScanError(f"Could not parse workflow {workflow_path}") from exc
    if not isinstance(payload, dict):
        raise ActionRefScanError(f"Workflow must contain a YAML mapping: {workflow_path}")

    workflow_name = str(payload.get("name") or workflow_path.stem)
    jobs = payload.get("jobs") or {}
    if not isinstance(jobs, dict):
        return workflow_name, []

    uses: list[ActionUse] = []
    relative_path = _relative_path(workflow_path, root)
    normalized_repository = action_repository.lower()
    for raw_job_id, raw_job in sorted(jobs.items(), key=lambda item: str(item[0])):
        job_id = str(raw_job_id)
        if not isinstance(raw_job, dict):
            continue
        job_use = raw_job.get("uses")
        if isinstance(job_use, str):
            parsed = parse_action_use(job_use, normalized_repository)
            if parsed:
                uses.append(
                    ActionUse(
                        workflow_path=relative_path,
                        workflow_name=workflow_name,
                        job_id=job_id,
                        location=f"jobs.{job_id}.uses",
                        uses=job_use,
                        ref=parsed,
                    )
                )
        steps = raw_job.get("steps") or []
        if not isinstance(steps, list):
            continue
        for index, raw_step in enumerate(steps):
            if not isinstance(raw_step, dict):
                continue
            step_use = raw_step.get("uses")
            if not isinstance(step_use, str):
                continue
            parsed = parse_action_use(step_use, normalized_repository)
            if not parsed:
                continue
            uses.append(
                ActionUse(
                    workflow_path=relative_path,
                    workflow_name=workflow_name,
                    job_id=job_id,
                    location=f"jobs.{job_id}.steps[{index}].uses",
                    step_name=str(raw_step.get("name") or ""),
                    uses=step_use,
                    ref=parsed,
                )
            )
    return workflow_name, uses


def parse_action_use(uses: str, normalized_repository: str) -> str | None:
    """Return the action ref if a uses string targets the configured repository."""
    repository, separator, ref = uses.strip().partition("@")
    if not separator or not ref.strip():
        return None
    if repository.lower() != normalized_repository:
        return None
    return ref.strip()


def scan_workflows(
    workflow_dir: Path,
    *,
    action_repository: str = DEFAULT_ACTION_REPOSITORY,
) -> ActionRefReport:
    """Scan a workflow directory and summarize Reponomics action refs per workflow."""
    workflow_dir = workflow_dir.resolve()
    if not workflow_dir.exists():
        raise ActionRefScanError(f"Workflow directory does not exist: {workflow_dir}")
    if not workflow_dir.is_dir():
        raise ActionRefScanError(f"Workflow path is not a directory: {workflow_dir}")

    workflow_summaries: list[WorkflowRefSummary] = []
    all_refs: list[str] = []
    for workflow_path in _iter_workflow_files(workflow_dir):
        workflow_name, action_uses = scan_workflow_file(
            workflow_path,
            action_repository=action_repository,
            root=workflow_dir,
        )
        if not action_uses:
            continue
        classified = tuple(classify_action_use(action_use) for action_use in action_uses)
        refs = tuple(sorted({action_use.ref for action_use in action_uses}))
        all_refs.extend(refs)
        workflow_summaries.append(
            WorkflowRefSummary(
                workflow_path=_relative_path(workflow_path, workflow_dir),
                workflow_name=workflow_name,
                classification=summarize_refs(refs),
                refs=refs,
                action_uses=classified,
            )
        )

    unique_refs = tuple(sorted(set(all_refs)))
    return ActionRefReport(
        action_repository=action_repository,
        workflow_dir=workflow_dir.as_posix(),
        classification=summarize_refs(unique_refs),
        refs=unique_refs,
        workflows=tuple(workflow_summaries),
    )


def classify_action_use(action_use: ActionUse) -> ClassifiedActionUse:
    return ClassifiedActionUse(
        workflow_path=action_use.workflow_path,
        workflow_name=action_use.workflow_name,
        job_id=action_use.job_id,
        location=action_use.location,
        step_name=action_use.step_name,
        uses=action_use.uses,
        ref=action_use.ref,
        ref_kind=classify_ref(action_use.ref),
    )


def report_to_dict(report: ActionRefReport) -> dict[str, Any]:
    return asdict(report)


def report_to_text(report: ActionRefReport) -> str:
    lines = [
        f"Action repository: {report.action_repository}",
        f"Workflow directory: {report.workflow_dir}",
        f"Overall classification: {report.classification}",
    ]
    if report.refs:
        lines.append(f"Overall refs: {', '.join(report.refs)}")
    if not report.workflows:
        lines.append("No matching workflow refs found.")
        return "\n".join(lines)

    lines.append("")
    for workflow in report.workflows:
        ref_text = ", ".join(workflow.refs) if workflow.refs else "none"
        lines.append(f"{workflow.workflow_path}: {workflow.classification} ({ref_text})")
        for action_use in workflow.action_uses:
            label = f" [{action_use.step_name}]" if action_use.step_name else ""
            lines.append(
                f"  - {action_use.location}{label}: {action_use.ref} ({action_use.ref_kind})"
            )
    return "\n".join(lines)


def _iter_workflow_files(workflow_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in workflow_dir.iterdir()
        if path.is_file() and path.suffix.lower() in WORKFLOW_SUFFIXES
    )


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workflow-dir",
        type=Path,
        default=ROOT / DEFAULT_WORKFLOW_DIR,
        help="Directory containing GitHub workflow YAML files.",
    )
    parser.add_argument(
        "--action-repository",
        default=DEFAULT_ACTION_REPOSITORY,
        help="Action repository to scan for in workflow uses entries.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Output format.",
    )
    args = parser.parse_args()

    report = scan_workflows(args.workflow_dir, action_repository=args.action_repository)
    if args.format == "json":
        print(json.dumps(report_to_dict(report), indent=2, sort_keys=True))
    else:
        print(report_to_text(report))


if __name__ == "__main__":
    try:
        main()
    except ActionRefScanError as exc:
        print(f"Action ref scan failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
