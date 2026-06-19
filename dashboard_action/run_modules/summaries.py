"""GitHub step summary and stdout reporting helpers."""

from __future__ import annotations

from pathlib import Path

from .config import _env
from .core import ActiveRetentionCleanupResult, IncidentPurgeResult, VERSION

import managed_docs  # noqa: E402


def _write_summary(lines: list[str]) -> None:
    summary_path = _env("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


def _summarize_rotation() -> None:
    _write_summary(
        [
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
    )


def _summarize_incident_reset_prepared() -> None:
    _write_summary(
        [
            "## Incident reset artifact prepared",
            "",
            "Retained dashboard data was restored, decrypted with",
            "`DASHBOARD_SECRET_DO_NOT_REPLACE`, and re-encrypted with",
            "`DASHBOARD_NEXT_SECRET`.",
            "",
            "The composite action uploads the re-encrypted `dashboard-data`",
            "artifact before the purge step starts. If this is a serious exposure,",
            "make the repository private and disable any published Pages dashboard",
            "before relying on the purge.",
        ]
    )


def _summarize_incident_reset_purge(result: IncidentPurgeResult) -> None:
    _write_summary(
        [
            "## Incident reset purge complete",
            "",
            f"- Prior dashboard-data artifacts found: {result.candidate_artifacts}",
            f"- Associated workflow runs found: {result.candidate_runs}",
            f"- Deleted workflow runs: {result.deleted_runs}",
            f"- Deleted fallback artifacts: {result.deleted_fallback_artifacts}",
            "",
            "Promote `DASHBOARD_NEXT_SECRET` into `DASHBOARD_SECRET_DO_NOT_REPLACE`",
            "before normal runs, then delete `DASHBOARD_NEXT_SECRET`.",
            "",
            "Forks do not preserve this repository's workflow runs, Actions",
            "artifacts, or secrets. The relevant exposure surfaces are current",
            "repository access, Actions artifacts/runs, Pages output, local",
            "downloads, browser/cache copies, and anyone who already had the",
            "dashboard key.",
        ]
    )


def _summarize_active_retention_cleanup(result: ActiveRetentionCleanupResult) -> None:
    _write_summary(
        [
            "## Dashboard data retention cleanup complete",
            "",
            f"- Prior dashboard-data artifacts found: {result.prior_artifacts}",
            f"- Prior artifacts retained for rollback: {result.retained_prior_artifacts}",
            f"- Superseded artifacts eligible this run: {result.delete_candidates}",
            f"- Deleted superseded artifacts: {result.deleted_artifacts}",
            "",
            "Routine cleanup deletes only old `dashboard-data` artifacts after a fresh collect artifact has been uploaded. It does not delete workflow runs.",
        ]
    )


def _summarize_update_docs(result: managed_docs.ManagedDocsResult) -> None:
    lines = [
        "## Managed Reponomics docs",
        "",
        f"- State: `{result.state}`",
        f"- Details: {result.reason}",
        f"- Action version: `{VERSION}`",
    ]
    if result.manifest_action_version:
        lines.append(f"- Docs action version: `{result.manifest_action_version}`")
    if result.docs_updated_at:
        lines.append(f"- Docs updated at: `{result.docs_updated_at}`")
    if result.state == managed_docs.STATE_PERMISSION_MISSING:
        lines.extend(
            [
                "",
                "Grant `contents: write` to the update-docs job or disable the update-docs workflow.",
            ]
        )
    elif result.state == managed_docs.STATE_MANIFEST_INCONSISTENT:
        lines.extend(
            [
                "",
                "Reponomics could not safely write the managed docs namespace. Avoid symlinks in `docs/reponomics/`, and check for invalid managed-docs metadata.",
            ]
        )
    elif result.state == managed_docs.STATE_PUSH_RACE:
        lines.extend(
            [
                "",
                "The docs update was prepared but could not be pushed after a bounded retry. Rerun the workflow after the branch settles.",
            ]
        )
    _write_summary(lines)
