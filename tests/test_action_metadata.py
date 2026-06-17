from pathlib import Path
import re
import tomllib

import yaml

from dashboard_action.run_modules.core import VERSION
from scripts import template_contract


ACTION_EXPRESSION = re.compile(r"\$\{\{.*?\}\}")
PAGES_DEPLOYMENT_IF = (
    "${{ (inputs.mode == 'publish' || inputs.mode == 'rotate-key') && " +
    "steps.runtime.outputs.publish-pages == 'true' }}"
)
PLAINTEXT_DASHBOARD_ARTIFACT_IF = (
    "${{ inputs.mode == 'publish' && steps.runtime.outputs.publish-pages == " +
    "'false' && steps.runtime.outputs.data-mode == 'plaintext' }}"
)
ENCRYPTED_DASHBOARD_ARTIFACT_IF = (
    "${{ (inputs.mode == 'publish' || inputs.mode == 'rotate-key') && " +
    "steps.runtime.outputs.publish-pages == 'false' && " +
    "steps.runtime.outputs.data-mode == 'encrypted' }}"
)
DATA_MODE_EXCLUSION = "inputs.mode != 'docs-sync'"


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


def test_release_please_remains_action_only() -> None:
    contract = template_contract.load_contract()
    release_manifest = yaml.safe_load(
        Path(".github/.release-please-manifest.json").read_text(encoding="utf-8")
    )
    release_config = yaml.safe_load(
        Path(".github/release-please-config.json").read_text(encoding="utf-8")
    )

    assert release_manifest["."] == VERSION
    assert "template" not in release_manifest
    assert "template" not in release_config["packages"]
    assert release_config["packages"]["."]["include-component-in-tag"] is False
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", contract.template_version)


def test_publish_template_workflow_requires_release_tag_or_manual_confirmation() -> None:
    workflow_text = Path(".github/workflows/publish-template.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    publish_job = workflow["jobs"]["publish-template"]
    steps = publish_job["steps"]
    step_names = [step["name"] for step in steps]
    commands = "\n".join(step["run"] for step in steps if "run" in step)
    checkout_step = next(step for step in steps if step["name"] == "Checkout release source")
    app_token_step = next(step for step in steps if step["name"] == "Create release app token")

    assert publish_job["if"] == (
        "${{ (github.event_name == 'release' && "
        + "startsWith(github.event.release.tag_name, 'reponomics-dashboard-v')) || "
        + "(github.event_name == 'workflow_dispatch' && "
        + "inputs.confirm_unreleased_template_publish) }}"
    )
    assert publish_job["environment"] == "template-publication"
    assert publish_job["permissions"] == {
        "attestations": "write",
        "contents": "read",
        "id-token": "write",
    }
    assert "source_ref:" in workflow_text
    assert "confirm_unreleased_template_publish:" in workflow_text
    assert "expected_tag=\"reponomics-dashboard-v${template_version}\"" in workflow_text
    assert "Manual template publication" in workflow_text
    assert "Manual template publication is restricted to main or reponomics-dashboard-v* tags" in workflow_text
    assert "token" not in checkout_step["with"]
    assert app_token_step["with"]["repositories"] == "reponomics-dashboard"
    assert "make template-release-gates" in commands
    assert "make build-template" not in commands
    assert "make validate-template-accepted-action" not in commands
    assert "make template-consumer-e2e" not in commands
    assert "make publish-template-dry-run" not in commands
    assert "make template-release-gates" in workflow_text
    assert "gh release upload" not in workflow_text
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow_text
    assert "reponomics-dashboard-template-release-${{ github.event.release.tag_name }}" in workflow_text
    assert "actions/attest@59d89421af93a897026c735860bf21b6eb4f7b26" in workflow_text
    assert "dist/template-release/SHA256SUMS" in workflow_text
    assert step_names.index("Validate generated template release gates") < step_names.index(
        "Upload template release artifacts"
    )
    assert step_names.index("Upload template release artifacts") < step_names.index(
        "Attest template release artifacts"
    )
    assert step_names.index("Attest template release artifacts") < step_names.index(
        "Create release app token"
    )
    assert step_names.index("Create release app token") < step_names.index(
        "Publish generated template repository"
    )


def test_publish_template_staging_workflow_targets_staging_repo_only() -> None:
    workflow_text = Path(".github/workflows/publish-template-staging.yml").read_text(
        encoding="utf-8"
    )
    workflow = yaml.safe_load(workflow_text)
    publish_job = workflow["jobs"]["publish-template-staging"]
    steps = publish_job["steps"]
    commands = "\n".join(step["run"] for step in steps if "run" in step)
    step_names = [step["name"] for step in steps]
    app_token_step = next(
        step for step in steps if step["name"] == "Create staging publication app token"
    )

    assert workflow["permissions"] == {}
    assert "workflow_dispatch" in workflow[True]
    assert publish_job["if"] == (
        "${{ github.event_name == 'workflow_dispatch' && "
        + "inputs.confirm_staging_template_publish }}"
    )
    assert "environment" not in publish_job
    assert publish_job["permissions"] == {"contents": "read"}
    assert publish_job["env"]["TEMPLATE_STAGING_EXPECTED_REPO"] == (
        "reponomics/reponomics-dashboard-staging"
    )
    assert (
        "Template staging publication is restricted to main or release tags" in workflow_text
    )
    assert "make verify-workflow-classification" in commands
    assert "make build-template" not in commands
    assert "make verify-template" in commands
    assert "make validate-template-action-ref" in commands
    assert "make template-smoke" in commands
    assert "make template-consumer-e2e" in commands
    assert "make publish-template-staging-dry-run" in commands
    assert "make package-template-release" not in workflow_text
    assert "actions/attest@" not in workflow_text
    assert app_token_step["with"]["client-id"] == (
        "${{ vars.TEMPLATE_STAGING_PUBLISH_APP_CLIENT_ID }}"
    )
    assert app_token_step["with"]["private-key"] == (
        "${{ secrets.TEMPLATE_STAGING_PUBLISH_APP_PRIVATE_KEY }}"
    )
    assert app_token_step["with"]["repositories"] == "reponomics-dashboard-staging"
    assert app_token_step["with"]["permission-contents"] == "write"
    assert app_token_step["with"]["permission-workflows"] == "write"
    assert step_names.index("Validate generated template staging gates") < step_names.index(
        "Create staging publication app token"
    )
    assert step_names.index("Create staging publication app token") < step_names.index(
        "Publish generated staging template repository"
    )


def test_ci_runs_generated_template_gates() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["template"]["steps"]
    commands = [step["run"] for step in steps if "run" in step]

    assert "make verify-workflow-classification" in commands
    assert "make build-and-verify-generated" in commands
    assert "make template-smoke" in commands
    assert "make template-consumer-e2e" in commands
    assert "make publish-template-dry-run" in commands


def test_pre_release_validation_runs_action_template_candidate_gates() -> None:
    workflow_text = Path(".github/workflows/pre-release-validation.yml").read_text(
        encoding="utf-8"
    )
    workflow = yaml.safe_load(workflow_text)
    steps = workflow["jobs"]["action-template"]["steps"]
    commands = "\n".join(step["run"] for step in steps if "run" in step)

    assert "workflow_dispatch:" in workflow_text
    assert "source_ref:" in workflow_text
    assert workflow["permissions"] == {"contents": "read"}
    assert "make validate" in commands
    assert "make validate-action-pins" not in commands
    assert "make verify-workflow-classification" in commands
    assert "make validate-template-action-ref" in commands
    assert "make template-smoke" in commands
    assert "make template-compat-e2e" in commands
    assert "make publish-template-dry-run" in commands
    assert "scripts/publish_generated_repo.py" not in workflow_text
    assert "--push" not in workflow_text
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow_text


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
    workflow_text = Path(".github/workflows/release-please.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    steps = workflow["jobs"]["release"]["steps"]
    step_names = [step["name"] for step in steps]
    commands = "\n".join(step["run"] for step in steps if "run" in step)

    assert "reponomics-dashboard-dev" not in workflow_text
    assert "repository_dispatch" not in workflow_text
    assert workflow["permissions"] == {"contents": "read"}
    app_token_step = next(step for step in steps if step["name"] == "Create release app token")
    assert not any(
        key.startswith("permission-") for key in app_token_step["with"]
    )
    assert "make template-compat-e2e" in commands
    assert "scripts/accept_action_release.py" in workflow_text
    assert "make validate-template-accepted-action" in commands
    assert "gh release create" not in commands
    assert "gh pr create" in commands
    assert "gh pr edit" in commands
    assert "## Template release notes" in commands
    assert "automation/template-accept-${action_tag}" in commands
    assert 'git push origin "HEAD:${GITHUB_REF_NAME}"' not in commands
    assert 'git push --force-with-lease origin "HEAD:${branch}"' in commands
    assert "template_tag=" in workflow_text
    assert step_names.index("Verify action compatibility with generated templates") < (
        step_names.index("Create release PR or GitHub release")
    )
    assert step_names.index("Create release PR or GitHub release") < (
        step_names.index("Move floating action tags")
    )
    assert step_names.index("Move floating action tags") < (
        step_names.index("Accept action release for template")
    )
    assert step_names.index("Accept action release for template") < (
        step_names.index("Open template acceptance PR")
    )


def test_template_release_workflow_cuts_template_releases_after_main_acceptance() -> None:
    workflow_text = Path(".github/workflows/template-release.yml").read_text(
        encoding="utf-8"
    )
    workflow = yaml.safe_load(workflow_text)
    job = workflow["jobs"]["release-template"]
    steps = job["steps"]
    step_names = [step["name"] for step in steps]
    commands = "\n".join(step["run"] for step in steps if "run" in step)
    app_token_step = next(step for step in steps if step["name"] == "Create release app token")

    assert "workflow_dispatch" not in workflow_text
    assert "source_ref:" not in workflow_text
    assert "release_notes:" not in workflow_text
    assert workflow["permissions"] == {"contents": "read", "pull-requests": "read"}
    assert "template-contract.yml" in workflow_text
    assert "template/**" in workflow_text
    assert "dashboard_action/runtime/managed_docs/**" in workflow_text
    assert "scripts/template_release_notes.py" in workflow_text
    assert "/repos/${GITHUB_REPOSITORY}/commits/${GITHUB_SHA}/pulls" in workflow_text
    assert "--pr-body .tmp/template-release-pr-body.md" in workflow_text
    assert "make template-release-gates" in commands
    assert "gh release view" in commands
    assert "gh release create" in commands
    assert "${{ steps.metadata.outputs.template_tag }}" in workflow_text
    assert not any(
        key.startswith("permission-") for key in app_token_step["with"]
    )
    assert step_names.index("Prepare template release metadata") < step_names.index(
        "Check template release status"
    )
    assert step_names.index("Check template release status") < step_names.index(
        "Validate template release gates"
    )
    assert step_names.index("Validate template release gates") < step_names.index(
        "Create template release"
    )


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
    plaintext_dashboard = _step_by_name("Upload plaintext dashboard artifact")
    encrypted_dashboard = _step_by_name("Upload encrypted dashboard artifact")
    encrypted_data = _step_by_name("Upload encrypted dashboard data artifact")
    plaintext_data = _step_by_name("Upload dashboard data artifact")
    provenance = _step_by_name("Upload collect provenance artifact")

    assert upload_pages["if"] == PAGES_DEPLOYMENT_IF
    assert upload_pages["with"]["name"] == "html-dashboard-encrypted"
    assert deploy_pages["if"] == PAGES_DEPLOYMENT_IF
    assert deploy_pages["with"]["artifact_name"] == "html-dashboard-encrypted"
    assert plaintext_dashboard["if"] == PLAINTEXT_DASHBOARD_ARTIFACT_IF
    assert plaintext_dashboard["with"]["name"] == "html-dashboard-plaintext"
    assert encrypted_dashboard["if"] == ENCRYPTED_DASHBOARD_ARTIFACT_IF
    assert encrypted_dashboard["with"]["name"] == "html-dashboard-encrypted"
    assert DATA_MODE_EXCLUSION in encrypted_data["if"]
    assert DATA_MODE_EXCLUSION in plaintext_data["if"]
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
