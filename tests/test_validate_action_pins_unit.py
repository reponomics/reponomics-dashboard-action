from pathlib import Path

from scripts import validate_action_pins


FULL_SHA = "a" * 40


def _write_workflow(path: Path, uses: str) -> None:
    path.write_text(
        "\n".join(
            [
                "jobs:",
                "  scan:",
                f"    uses: {uses}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_remote_reusable_workflows_are_rejected_even_when_sha_pinned(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.yml"
    uses = f"google/osv-scanner-action/.github/workflows/osv-scanner-reusable.yml@{FULL_SHA}"
    _write_workflow(workflow, uses)

    assert validate_action_pins.collect_failures([workflow]) == [
        f"{workflow}: {uses}: third-party remote reusable workflows are not allowed; "
        + "inline pinned steps locally"
    ]


def test_organization_owned_remote_reusable_workflows_are_allowed_when_sha_pinned(
    tmp_path: Path,
) -> None:
    workflow = tmp_path / "workflow.yml"
    uses = f"reponomics/shared-workflows/.github/workflows/ci.yml@{FULL_SHA}"
    _write_workflow(workflow, uses)

    assert validate_action_pins.collect_failures([workflow]) == []


def test_local_reusable_workflows_are_allowed(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.yml"
    _write_workflow(workflow, "./.github/workflows/validate-action-pins.yml")

    assert validate_action_pins.collect_failures([workflow]) == []
