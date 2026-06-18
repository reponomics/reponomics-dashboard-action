"""Verify maintainer and generated-template workflow classification boundaries."""
# ruff: noqa: ISC002

from __future__ import annotations

import sys
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

from scripts import build_template  # noqa: E402
from scripts.template_workflows import (  # noqa: E402
    TEMPLATE_WORKFLOW_NAMES,
    TEMPLATE_WORKFLOW_OUTPUTS,
)

WORKFLOW_DIR = ROOT / ".github" / "workflows"
TEMPLATE_WORKFLOW_DIR = ROOT / "template" / ".github" / "workflows"
MANIFEST_PATH = ROOT / "template-manifest.yml"
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


def _verify_template_workflow_names(template_workflow_files: list[str]) -> None:
    mismatches: list[str] = []
    for source in template_workflow_files:
        expected = TEMPLATE_WORKFLOW_NAMES[source]
        payload = yaml.safe_load((ROOT / source).read_text(encoding="utf-8")) or {}
        actual = payload.get("name")
        if actual != expected:
            mismatches.append(f"  - {source}: expected {expected!r}, got {actual!r}")

    if mismatches:
        raise WorkflowClassificationError(
            "Template workflow display names must match the canonical command "
            "surface.\n" + "\n".join(mismatches)
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
    _verify_template_workflow_names(template_workflow_files)
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
