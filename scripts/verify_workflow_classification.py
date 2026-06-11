"""Verify workflow classification boundaries for dashboard-dev vs template."""
# ruff: noqa: ISC002

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

from scripts import build_template


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
TEMPLATE_WORKFLOW_DIR = ROOT / "template" / ".github" / "workflows"
MANIFEST_PATH = ROOT / "template-manifest.yml"

TEMPLATE_WORKFLOW_OUTPUTS = {
    "template/.github/workflows/collect-and-publish.yml": ".github/workflows/collect-and-publish.yml",
    "template/.github/workflows/doctor.yml": ".github/workflows/doctor.yml",
    "template/.github/workflows/incident-reset.yml": ".github/workflows/incident-reset.yml",
    "template/.github/workflows/keepalive.yml": ".github/workflows/keepalive.yml",
    "template/.github/workflows/rotate-key.yml": ".github/workflows/rotate-key.yml",
    "template/.github/workflows/setup.yml": ".github/workflows/setup.yml",
}
DEV_WORKFLOW_GLOB = ".github/workflows/dev-*.yml"


class WorkflowClassificationError(RuntimeError):
    """Raised when workflow boundaries are violated."""


def _load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        manifest = yaml.safe_load(handle) or {}
    if manifest.get("version") != 1:
        raise WorkflowClassificationError(f"{path} must declare version: 1")
    return manifest


def _iter_workflow_files() -> list[str]:
    if not WORKFLOW_DIR.exists():
        raise WorkflowClassificationError(f"Missing workflow directory: {WORKFLOW_DIR}")
    return sorted(path.name for path in WORKFLOW_DIR.iterdir() if path.is_file())


def _iter_template_workflow_files() -> list[str]:
    if not TEMPLATE_WORKFLOW_DIR.exists():
        raise WorkflowClassificationError(
            f"Missing template workflow directory: {TEMPLATE_WORKFLOW_DIR}"
        )
    return sorted(
        f"template/.github/workflows/{path.name}"
        for path in TEMPLATE_WORKFLOW_DIR.iterdir()
        if path.is_file()
    )


def _verify_template_workflow_sources(template_workflow_files: list[str]) -> None:
    expected = sorted(TEMPLATE_WORKFLOW_OUTPUTS)
    if template_workflow_files != expected:
        expected_text = "\n".join(f"  - {entry}" for entry in expected)
        actual_text = "\n".join(f"  - {entry}" for entry in template_workflow_files)
        raise WorkflowClassificationError(
            "Template workflow source set must match the canonical workflow "
            f"surface exactly.\nExpected:\n{expected_text}\nActual:\n{actual_text}"
        )


def _verify_manifest_includes(manifest: dict[str, Any]) -> None:
    workflow_entries: dict[str, str] = {}
    for source, target in build_template.iter_include_file_entries(manifest):
        source_text = source.as_posix()
        target_text = target.as_posix()
        if target_text.startswith(".github/workflows/"):
            workflow_entries[source_text] = target_text

    if workflow_entries != TEMPLATE_WORKFLOW_OUTPUTS:
        expected = "\n".join(
            f"  - {source} -> {target}"
            for source, target in sorted(TEMPLATE_WORKFLOW_OUTPUTS.items())
        )
        actual = "\n".join(
            f"  - {source} -> {target}"
            for source, target in sorted(workflow_entries.items())
        )
        raise WorkflowClassificationError(
            "Template manifest workflow include set must match template workflow "
            f"surface exactly.\nExpected:\n{expected}\nActual:\n{actual}"
        )


def _verify_manifest_forbidden(manifest: dict[str, Any]) -> None:
    forbidden = manifest.get("forbidden", [])
    if DEV_WORKFLOW_GLOB not in forbidden:
        raise WorkflowClassificationError(
            f"template-manifest forbidden list must include `{DEV_WORKFLOW_GLOB}`"
        )
    if "template" not in forbidden:
        raise WorkflowClassificationError(
            "template-manifest forbidden list must include `template`"
        )


def verify() -> None:
    workflow_files = _iter_workflow_files()
    template_workflow_files = _iter_template_workflow_files()
    manifest = _load_manifest()
    _verify_template_workflow_sources(template_workflow_files)
    _verify_manifest_includes(manifest)
    _verify_manifest_forbidden(manifest)
    print(
        f"Verified workflow classification "
        f"({len(workflow_files)} maintainer workflow files, "
        f"{len(template_workflow_files)} template workflow source files)"
    )


if __name__ == "__main__":
    try:
        verify()
    except WorkflowClassificationError as exc:
        print(f"Workflow classification error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
