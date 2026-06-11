from pathlib import Path
import re
import tomllib

import yaml

from dashboard_action.run_modules.core import VERSION


ACTION_EXPRESSION = re.compile(r"\$\{\{.*?\}\}")
PAGES_DEPLOYMENT_IF = (
    "${{ (inputs.mode == 'publish' || inputs.mode == 'rotate-key') && " +
    "steps.runtime.outputs.publish-pages == 'true' }}"
)
PLAIN_DASHBOARD_ARTIFACT_IF = (
    "${{ inputs.mode == 'publish' && steps.runtime.outputs.publish-pages == " +
    "'false' && steps.runtime.outputs.artifact-mode == 'plain' }}"
)
ENCRYPTED_DASHBOARD_ARTIFACT_IF = (
    "${{ (inputs.mode == 'publish' || inputs.mode == 'rotate-key') && " +
    "steps.runtime.outputs.publish-pages == 'false' && " +
    "steps.runtime.outputs.artifact-mode == 'encrypted' }}"
)
DATA_ARTIFACT_MODE_EXCLUSION = "inputs.mode != 'docs-sync'"


def _action() -> dict:
    return yaml.safe_load(Path("action.yml").read_text(encoding="utf-8"))


def _steps() -> list[dict]:
    return _action()["runs"]["steps"]


def _step_by_uses(prefix: str) -> dict:
    for step in _steps():
        if str(step.get("uses", "")).startswith(prefix):
            return step
    raise AssertionError(f"missing action step using {prefix}")


def _step_by_name(name: str) -> dict:
    for step in _steps():
        if step.get("name") == name:
            return step
    raise AssertionError(f"missing action step named {name}")


def _step_index(name: str) -> int:
    for index, step in enumerate(_steps()):
        if step.get("name") == name:
            return index
    raise AssertionError(f"missing action step named {name}")


def _description_fields(value: object, path: str = "action.yml") -> list[tuple[str, str]]:
    descriptions: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "description" and isinstance(child, str):
                descriptions.append((child_path, child))
            descriptions.extend(_description_fields(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            descriptions.extend(_description_fields(child, f"{path}[{index}]"))
    return descriptions


def test_action_descriptions_do_not_contain_actions_expressions() -> None:
    descriptions = _description_fields(_action())
    offenders = [
        path
        for path, description in descriptions
        if ACTION_EXPRESSION.search(description)
    ]

    assert offenders == []


def test_runtime_version_matches_release_metadata() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    release_manifest = yaml.safe_load(
        Path(".github/.release-please-manifest.json").read_text(encoding="utf-8")
    )
    release_config = yaml.safe_load(
        Path(".github/release-please-config.json").read_text(encoding="utf-8")
    )
    extra_files = {
        file["path"]
        for file in release_config["packages"]["."]["extra-files"]
    }

    assert VERSION == project["project"]["version"]
    assert release_manifest["."] == VERSION
    assert "dashboard_action/run_modules/core.py" in extra_files
    assert "dashboard_action/run.py" not in extra_files


def test_runtime_steps_execute_dashboard_action_as_module() -> None:
    runtime_steps = [
        _step_by_name("Run Reponomics runtime"),
        _step_by_name("Clean up superseded dashboard data artifacts"),
        _step_by_name("Purge incident reset history"),
    ]

    for step in runtime_steps:
        command = step["run"]
        assert command == (
            'PYTHONPATH="$GITHUB_ACTION_PATH" python -m dashboard_action.run'
        )
        assert "dashboard_action/run.py" not in command


def test_release_workflow_does_not_dispatch_dashboard_dev() -> None:
    workflow = Path(".github/workflows/release-please.yml").read_text(encoding="utf-8")

    assert "reponomics-dashboard-dev" not in workflow
    assert "repository_dispatch" not in workflow


def test_configure_pages_verifies_existing_pages_setup_without_enablement() -> None:
    step = _step_by_uses("actions/configure-pages@")

    assert step["name"] == "Verify GitHub Pages configuration"
    assert step["if"] == PAGES_DEPLOYMENT_IF
    assert step["with"]["enablement"] == "false"
    assert "token" not in step.get("with", {})

    serialized = yaml.safe_dump(step)
    assert "collection-token" not in serialized
    assert "COLLECTION_TOKEN" not in serialized


def test_pages_deployment_steps_follow_publish_pages_contract() -> None:
    upload_pages = _step_by_uses("actions/upload-pages-artifact@")
    deploy_pages = _step_by_uses("actions/deploy-pages@")
    plain_dashboard = _step_by_name("Upload plain dashboard artifact")
    encrypted_dashboard = _step_by_name("Upload encrypted dashboard artifact")
    encrypted_data = _step_by_name("Upload encrypted dashboard data artifact")
    plain_data = _step_by_name("Upload dashboard data artifact")
    provenance = _step_by_name("Upload collect provenance artifact")

    assert upload_pages["if"] == PAGES_DEPLOYMENT_IF
    assert upload_pages["with"]["name"] == "html-dashboard-encrypted"
    assert deploy_pages["if"] == PAGES_DEPLOYMENT_IF
    assert deploy_pages["with"]["artifact_name"] == "html-dashboard-encrypted"
    assert plain_dashboard["if"] == PLAIN_DASHBOARD_ARTIFACT_IF
    assert plain_dashboard["with"]["name"] == "html-dashboard-plain"
    assert encrypted_dashboard["if"] == ENCRYPTED_DASHBOARD_ARTIFACT_IF
    assert encrypted_dashboard["with"]["name"] == "html-dashboard-encrypted"
    assert DATA_ARTIFACT_MODE_EXCLUSION in encrypted_data["if"]
    assert DATA_ARTIFACT_MODE_EXCLUSION in plain_data["if"]
    assert provenance["if"] == "${{ inputs.mode == 'collect' }}"
    assert provenance["with"]["name"] == "reponomics-collect-provenance"
    assert provenance["with"]["path"] == ".reponomics/collect-provenance/collect-provenance.json"


def test_publish_pages_replaces_dashboard_mode_output() -> None:
    outputs = _action()["outputs"]
    description = outputs["publish-pages"]["description"]

    assert "dashboard-mode" not in outputs
    assert "publishes" in description
    assert "GitHub Pages" in description


def test_allow_docs_sync_metadata_contract() -> None:
    action = _action()
    inputs = action["inputs"]
    outputs = action["outputs"]
    runtime_env = _step_by_name("Run Reponomics runtime")["env"]

    assert "docs-sync" in inputs["mode"]["description"]
    assert inputs["allow-docs-sync"]["default"] == ""
    assert runtime_env["REPONOMICS_ALLOW_DOCS_SYNC"] == "${{ inputs.allow-docs-sync }}"
    assert outputs["docs-sync-state"]["value"] == "${{ steps.runtime.outputs.docs-sync-state }}"
    assert "docs-sync-reason" not in outputs
    assert outputs["docs-action-version"]["value"] == "${{ steps.runtime.outputs.docs-action-version }}"
    assert outputs["docs-updated-at"]["value"] == "${{ steps.runtime.outputs.docs-updated-at }}"


def test_doctor_mode_metadata_contract() -> None:
    action = _action()
    inputs = action["inputs"]
    outputs = action["outputs"]
    runtime_env = _step_by_name("Run Reponomics runtime")["env"]
    upload_report = _step_by_name("Upload doctor diagnostic report")

    assert "doctor" in inputs["mode"]["description"]
    assert inputs["comparison-secret"]["default"] == ""
    assert "workflow input" in inputs["comparison-secret"]["description"]
    assert runtime_env["REPONOMICS_COMPARISON_SECRET"] == "${{ inputs.comparison-secret }}"
    assert outputs["doctor-report-path"]["value"] == "${{ steps.runtime.outputs.doctor-report-path }}"
    assert upload_report["if"] == "${{ always() && inputs.mode == 'doctor' && steps.runtime.outputs.doctor-report-path != '' }}"
    assert upload_report["with"]["name"] == "reponomics-doctor-report"
    assert upload_report["with"]["path"] == "${{ steps.runtime.outputs.doctor-report-path }}"


def test_incident_reset_purge_runs_after_data_upload() -> None:
    action = _action()
    inputs = action["inputs"]
    runtime_env = _step_by_name("Run Reponomics runtime")["env"]
    purge = _step_by_name("Purge incident reset history")

    assert "incident-reset" in inputs["mode"]["description"]
    assert "incident-purge-max-runs" not in inputs
    assert "REPONOMICS_INCIDENT_PURGE_MAX_RUNS" not in runtime_env
    assert purge["if"] == "${{ inputs.mode == 'incident-reset' }}"
    assert purge["env"]["REPONOMICS_INCIDENT_RESET_PURGE_ONLY"] == "true"
    assert "REPONOMICS_INCIDENT_PURGE_MAX_RUNS" not in purge["env"]
    assert _step_index("Purge incident reset history") > _step_index(
        "Upload encrypted dashboard data artifact"
    )


def test_collect_cleanup_runs_after_data_upload_before_incident_purge() -> None:
    cleanup = _step_by_name("Clean up superseded dashboard data artifacts")

    assert cleanup["if"] == "${{ inputs.mode == 'collect' }}"
    assert cleanup["env"]["REPONOMICS_COLLECT_RETENTION_CLEANUP_ONLY"] == "true"
    assert cleanup["env"]["REPONOMICS_GITHUB_TOKEN"] == "${{ inputs.github-token }}"
    assert _step_index("Clean up superseded dashboard data artifacts") > _step_index(
        "Upload encrypted dashboard data artifact"
    )
    assert _step_index("Clean up superseded dashboard data artifacts") > _step_index(
        "Upload dashboard data artifact"
    )
    assert _step_index("Clean up superseded dashboard data artifacts") > _step_index(
        "Upload collect provenance artifact"
    )
    assert _step_index("Clean up superseded dashboard data artifacts") < _step_index(
        "Purge incident reset history"
    )


def test_publish_pages_input_metadata_contract() -> None:
    action = _action()
    runtime_env = _step_by_name("Run Reponomics runtime")["env"]

    assert action["inputs"]["publish-pages"]["default"] == "true"
    assert runtime_env["REPONOMICS_PUBLISH_PAGES"] == "${{ inputs.publish-pages }}"
    assert action["inputs"]["require-collect-provenance"]["default"] == "false"
    assert runtime_env["REPONOMICS_REQUIRE_COLLECT_PROVENANCE"] == (
        "${{ inputs.require-collect-provenance }}"
    )


def test_use_github_app_input_metadata_contract() -> None:
    action = _action()
    runtime_env = _step_by_name("Run Reponomics runtime")["env"]

    assert action["inputs"]["use-github-app"]["default"] == "false"
    assert runtime_env["REPONOMICS_USE_GITHUB_APP"] == "${{ inputs.use-github-app }}"
