from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import scan_action_refs


def test_classify_ref_uses_specific_version_pin_categories() -> None:
    assert scan_action_refs.classify_ref("v0") == "major-tag"
    assert scan_action_refs.classify_ref("v12") == "major-tag"
    assert scan_action_refs.classify_ref("v0.23") == "minor-tag"
    assert scan_action_refs.classify_ref("v0.23.5") == "exact-tag"
    assert scan_action_refs.classify_ref("v0.23.5-rc.1") == "exact-tag"
    assert scan_action_refs.classify_ref("a" * 40) == "sha"
    assert scan_action_refs.classify_ref("main") == "other"


def test_summarize_refs_reports_mixed_when_refs_differ() -> None:
    assert scan_action_refs.summarize_refs([]) == "none"
    assert scan_action_refs.summarize_refs(["v0", "v0"]) == "major-tag"
    assert scan_action_refs.summarize_refs(["v0.23.5"]) == "exact-tag"
    assert scan_action_refs.summarize_refs(["v0", "v0.23.5"]) == "mixed"
    assert scan_action_refs.summarize_refs(["v0", "v1"]) == "mixed"


def test_scan_workflows_classifies_refs_by_workflow(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    _write_workflow(
        workflow_dir / "collect-and-publish.yml",
        """
        name: Collect And Publish
        jobs:
          collect:
            runs-on: ubuntu-latest
            steps:
              - name: Checkout
                uses: actions/checkout@v6
              - name: Collect
                uses: reponomics/reponomics-dashboard-action@v0
          publish:
            runs-on: ubuntu-latest
            steps:
              - name: Publish
                uses: reponomics/reponomics-dashboard-action@v0
        """,
    )
    _write_workflow(
        workflow_dir / "doctor.yml",
        """
        name: Doctor
        jobs:
          doctor:
            runs-on: ubuntu-latest
            steps:
              - name: Diagnose
                uses: reponomics/reponomics-dashboard-action@v0.23.5
        """,
    )
    _write_workflow(
        workflow_dir / "rotate-key.yml",
        """
        name: Rotate Key
        jobs:
          rotate:
            runs-on: ubuntu-latest
            steps:
              - uses: reponomics/reponomics-dashboard-action@v0
              - uses: reponomics/reponomics-dashboard-action@v0.23.5
        """,
    )
    _write_workflow(
        workflow_dir / "keepalive.yml",
        """
        name: Keepalive
        jobs:
          keepalive:
            runs-on: ubuntu-latest
            steps:
              - run: date
        """,
    )

    report = scan_action_refs.scan_workflows(workflow_dir)

    assert report.classification == "mixed"
    assert report.refs == ("v0", "v0.23.5")
    summaries = {workflow.workflow_path: workflow for workflow in report.workflows}
    assert set(summaries) == {
        "collect-and-publish.yml",
        "doctor.yml",
        "rotate-key.yml",
    }
    assert summaries["collect-and-publish.yml"].classification == "major-tag"
    assert summaries["collect-and-publish.yml"].refs == ("v0",)
    assert len(summaries["collect-and-publish.yml"].action_uses) == 2
    assert summaries["doctor.yml"].classification == "exact-tag"
    assert summaries["doctor.yml"].refs == ("v0.23.5",)
    assert summaries["doctor.yml"].action_uses[0].step_name == "Diagnose"
    assert summaries["rotate-key.yml"].classification == "mixed"
    assert summaries["rotate-key.yml"].refs == ("v0", "v0.23.5")


def test_scan_workflows_handles_full_sha_and_job_level_uses(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    action_sha = "0123456789abcdef0123456789abcdef01234567"
    _write_workflow(
        workflow_dir / "workflow-call.yml",
        f"""
        name: Reusable
        jobs:
          action-job:
            uses: reponomics/reponomics-dashboard-action@{action_sha}
        """,
    )

    report = scan_action_refs.scan_workflows(workflow_dir)

    assert report.classification == "sha"
    assert report.refs == (action_sha,)
    assert report.workflows[0].classification == "sha"
    action_use = report.workflows[0].action_uses[0]
    assert action_use.location == "jobs.action-job.uses"
    assert action_use.ref_kind == "sha"


def test_scan_workflows_is_case_insensitive_for_repository_name(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    _write_workflow(
        workflow_dir / "doctor.yml",
        """
        name: Doctor
        jobs:
          doctor:
            runs-on: ubuntu-latest
            steps:
              - uses: Reponomics/Reponomics-Dashboard-Action@v0.23
        """,
    )

    report = scan_action_refs.scan_workflows(workflow_dir)

    assert report.classification == "minor-tag"
    assert report.refs == ("v0.23",)


def test_scan_workflows_rejects_missing_workflow_dir(tmp_path: Path) -> None:
    with pytest.raises(scan_action_refs.ActionRefScanError, match="does not exist"):
        scan_action_refs.scan_workflows(tmp_path / "missing")


def test_report_to_dict_is_json_serializable(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    _write_workflow(
        workflow_dir / "doctor.yml",
        """
        name: Doctor
        jobs:
          doctor:
            runs-on: ubuntu-latest
            steps:
              - uses: reponomics/reponomics-dashboard-action@v0
        """,
    )

    payload = scan_action_refs.report_to_dict(scan_action_refs.scan_workflows(workflow_dir))

    assert json.loads(json.dumps(payload))["workflows"][0]["classification"] == "major-tag"


def _write_workflow(path: Path, text: str) -> None:
    path.write_text(_dedent(text), encoding="utf-8")


def _dedent(text: str) -> str:
    lines = text.strip("\n").splitlines()
    indent = min(len(line) - len(line.lstrip(" ")) for line in lines if line.strip())
    return "\n".join(line[indent:] for line in lines) + "\n"
