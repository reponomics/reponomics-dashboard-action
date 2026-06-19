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
DATA_MODE_EXCLUSION = "inputs.mode != 'update-docs'"


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


def _assert_release_app_token_permissions_are_implicit(step: dict) -> None:
    explicit_permissions = sorted(
        key for key in step.get("with", {}) if str(key).startswith("permission-")
    )
    message = (
        "release app token permissions are intentionally implicit right now so the "
        + "token inherits the app installation's configured scopes, including any "
        + "Release Please permissions such as issues. If the policy changes to "
        + "explicit token permissions, update this test with the complete required "
        + f"permission list. Found explicit permission inputs: {explicit_permissions}"
    )
    assert explicit_permissions == [], (
        message
    )


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
    exclude_paths = set(release_config["packages"]["."]["exclude-paths"])
    assert ".github/workflows/template-release.yml" in exclude_paths
    assert ".github/workflows/prepare-template-release.yml" in exclude_paths
    assert ".github/workflows/publish-template.yml" not in exclude_paths
    assert "scripts/prepare_template_release.py" in exclude_paths
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", contract.template_version)


def test_no_manual_production_template_publication_workflow() -> None:
    workflow_path = Path(".github/workflows/publish-template.yml")

    assert not workflow_path.exists()


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
    checkout_step = next(step for step in steps if step["name"] == "Checkout")

    assert "reponomics-dashboard-dev" not in workflow_text
    assert "repository_dispatch" not in workflow_text
    assert workflow["permissions"] == {"contents": "read"}
    app_token_step = next(step for step in steps if step["name"] == "Create release app token")
    app_user_step = next(step for step in steps if step["name"] == "Get release app bot user ID")
    _assert_release_app_token_permissions_are_implicit(app_token_step)
    assert app_user_step["env"]["GH_TOKEN"] == "${{ steps.app-token.outputs.token }}"
    assert app_user_step["env"]["APP_SLUG"] == "${{ steps.app-token.outputs.app-slug }}"
    assert checkout_step["with"]["fetch-depth"] == 0
    assert "/users/${APP_SLUG}[bot]" in app_user_step["run"]
    assert "python3 scripts/enforce_release_policy.py" in commands
    assert "make template-compat-e2e" in commands
    assert "make publish-template-dry-run" in commands
    assert "make package-template-release" in commands
    assert "scripts/accept_action_release.py" in workflow_text
    assert "make validate-template-accepted-action" in commands
    assert "gh release create" not in commands
    assert "gh pr create" in commands
    assert "gh pr edit" in commands
    assert "## Template release notes" in commands
    assert "publish the generated template repository" in commands
    assert "create ${template_tag} in reponomics/reponomics-dashboard" in commands
    assert "automation/template-accept-${action_tag}" in commands
    assert 'git push origin "HEAD:${GITHUB_REF_NAME}"' not in commands
    assert 'git push --force-with-lease origin "HEAD:${branch}"' in commands
    assert 'git config user.name "${{ steps.app-token.outputs.app-slug }}[bot]"' in commands
    assert (
        'git config user.email "${{ steps.app-user.outputs.user-id }}+${{ '
        + 'steps.app-token.outputs.app-slug }}[bot]@users.noreply.github.com"'
        in commands
    )
    assert "template_tag=" in workflow_text
    assert step_names.index("Enforce release policy") < (
        step_names.index("Verify action compatibility with generated templates")
    )
    assert step_names.index("Verify action compatibility with generated templates") < (
        step_names.index("Verify generated template publication readiness")
    )
    assert step_names.index("Verify generated template publication readiness") < (
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
    trigger_paths = set(workflow[True]["push"]["paths"])
    gates_job = workflow["jobs"]["template-release-gates"]
    publish_job = workflow["jobs"]["publish-template-release"]
    gates_steps = gates_job["steps"]
    publish_steps = publish_job["steps"]
    gates_step_names = [step["name"] for step in gates_steps]
    publish_step_names = [step["name"] for step in publish_steps]
    gates_commands = "\n".join(step["run"] for step in gates_steps if "run" in step)
    publish_commands = "\n".join(step["run"] for step in publish_steps if "run" in step)
    source_tag_step = next(
        step for step in gates_steps if step["name"] == "Check source template tag status"
    )
    read_token_step = next(
        step for step in gates_steps if step["name"] == "Create generated template read token"
    )
    stop_other_source_step = next(
        step
        for step in gates_steps
        if step["name"] == "Stop if source tag belongs to another commit"
    )
    publication_step = next(
        step for step in gates_steps if step["name"] == "Record publication decision"
    )
    handoff_step = next(
        step for step in gates_steps if step["name"] == "Prepare publication handoff"
    )
    download_handoff_step = next(
        step for step in publish_steps if step["name"] == "Download publication handoff"
    )
    handoff_artifact_name = (
        "reponomics-dashboard-template-publication-"
        + "${{ needs.template-release-gates.outputs.template_tag }}"
    )
    app_token_step = next(
        step for step in publish_steps if step["name"] == "Create publication app token"
    )

    assert "workflow_dispatch" not in workflow_text
    assert "source_ref:" not in workflow_text
    assert "release_notes:" not in workflow_text
    assert workflow["permissions"] == {"contents": "read", "pull-requests": "read"}
    assert workflow["concurrency"]["group"] == "generated-template-publication-reponomics-dashboard"
    assert workflow["concurrency"]["queue"] == "max"
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert "environment" not in gates_job
    assert gates_job["permissions"] == {"contents": "read", "pull-requests": "read"}
    assert gates_job["env"]["TEMPLATE_EXPECTED_REPO"] == "reponomics/reponomics-dashboard"
    assert gates_job["outputs"]["should_publish"] == "${{ steps.publication.outputs.should_publish }}"
    assert gates_job["outputs"]["template_tag"] == "${{ steps.metadata.outputs.template_tag }}"
    assert (
        gates_job["outputs"]["accepted_action_tag"]
        == "${{ steps.metadata.outputs.accepted_action_tag }}"
    )
    assert publish_job["needs"] == "template-release-gates"
    assert publish_job["if"] == "${{ needs.template-release-gates.outputs.should_publish == 'true' }}"
    assert publish_job["environment"] == "template-publication"
    assert publish_job["permissions"] == {
        "attestations": "write",
        "contents": "write",
        "id-token": "write",
    }
    assert publish_job["env"]["TEMPLATE_EXPECTED_REPO"] == "reponomics/reponomics-dashboard"
    assert trigger_paths == {"template-contract.yml"}
    assert "scripts/publish_generated_repo.py" not in trigger_paths
    assert "/repos/${GITHUB_REPOSITORY}/commits/${GITHUB_SHA}/pulls" in workflow_text
    assert "--pr-body .tmp/template-release-pr-body.md" in workflow_text
    assert 'echo "status=other" >> "$GITHUB_OUTPUT"' in source_tag_step["run"]
    assert "Generated-template publication will continue only if" in source_tag_step["run"]
    assert "Rerun or repair publication from the source-tag commit" in stop_other_source_step["run"]
    assert stop_other_source_step["if"] == "${{ steps.source-tag.outputs.status == 'other' }}"
    assert "git fetch --quiet --no-tags origin" in source_tag_step["run"]
    assert "make template-release-gates" in gates_commands
    assert "curl -sS -L" in gates_commands
    assert "Generated template release lookup failed with HTTP ${http_status}." in gates_commands
    assert "--verify-ref \"refs/tags/${TEMPLATE_TAG}\"" in gates_commands
    assert 'echo "should_publish=true" >> "$GITHUB_OUTPUT"' in publication_step["run"]
    assert "tar -C dist -czf dist/publication-handoff/template-publication.tgz" in handoff_step["run"]
    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in workflow_text
    assert download_handoff_step["with"]["name"] == handoff_artifact_name
    assert "tar -C dist -xzf .tmp/publication-handoff/template-publication.tgz" in publish_commands
    assert "gh release create" in publish_commands
    assert "${{ steps.metadata.outputs.template_tag }}" in workflow_text
    assert "${{ needs.template-release-gates.outputs.template_tag }}" in workflow_text
    assert "--repo \"${TEMPLATE_EXPECTED_REPO}\"" in workflow_text
    assert "--target \"${PUBLISHED_COMMIT}\"" not in workflow_text
    assert "--verify-tag" in workflow_text
    assert "git -c tag.gpgSign=false tag \"${TEMPLATE_TAG}\" \"${current}\"" in workflow_text
    assert "git push origin \"refs/tags/${TEMPLATE_TAG}\"" in workflow_text
    assert "--release-tag \"${TEMPLATE_TAG}\"" in workflow_text
    assert "--github-output \"$GITHUB_OUTPUT\"" in workflow_text
    assert "## New-copy template changes" in workflow_text
    assert "## Accepted action metadata" in workflow_text
    assert "Source workflow run:" in workflow_text
    assert "Template provenance:" in workflow_text
    assert "if" not in read_token_step
    assert read_token_step["with"]["repositories"] == "reponomics-dashboard"
    assert read_token_step["with"]["permission-contents"] == "read"
    assert app_token_step["with"]["repositories"] == "reponomics-dashboard"
    assert app_token_step["with"]["permission-contents"] == "write"
    assert app_token_step["with"]["permission-workflows"] == "write"
    gates_guarded_steps = [
        "Validate template release gates",
        "Verify existing generated template release",
        "Upload template release artifacts",
        "Prepare publication handoff",
        "Upload publication handoff",
    ]
    for step in gates_steps:
        if step["name"] in gates_guarded_steps:
            assert "if" in step
    assert (
        "steps.source-tag.outputs.status != 'other'"
        in next(
            step
            for step in gates_steps
            if step["name"] == "Validate template release gates"
        )["if"]
    )
    for step in publish_steps:
        assert "steps.source-tag.outputs.status" not in str(step.get("if", ""))
    assert gates_step_names.index("Prepare template release metadata") < gates_step_names.index(
        "Check source template tag status"
    )
    assert gates_step_names.index("Check source template tag status") < gates_step_names.index(
        "Create generated template read token"
    )
    assert gates_step_names.index("Create generated template read token") < gates_step_names.index(
        "Check generated template release status"
    )
    assert gates_step_names.index("Check generated template release status") < gates_step_names.index(
        "Stop if source tag belongs to another commit"
    )
    assert gates_step_names.index("Stop if source tag belongs to another commit") < gates_step_names.index(
        "Validate template release gates"
    )
    assert gates_step_names.index("Validate template release gates") < gates_step_names.index(
        "Verify existing generated template release"
    )
    assert gates_step_names.index("Verify existing generated template release") < gates_step_names.index(
        "Upload template release artifacts"
    )
    assert gates_step_names.index("Upload template release artifacts") < gates_step_names.index(
        "Prepare publication handoff"
    )
    assert gates_step_names.index("Prepare publication handoff") < gates_step_names.index(
        "Upload publication handoff"
    )
    assert publish_step_names.index("Download publication handoff") < publish_step_names.index(
        "Restore publication handoff"
    )
    assert publish_step_names.index("Restore publication handoff") < publish_step_names.index(
        "Attest template release artifacts"
    )
    assert publish_step_names.index("Attest template release artifacts") < publish_step_names.index(
        "Create source template tag"
    )
    assert publish_step_names.index("Create source template tag") < publish_step_names.index(
        "Create publication app token"
    )
    assert publish_step_names.index("Create publication app token") < publish_step_names.index(
        "Publish generated template repository"
    )
    assert publish_step_names.index("Publish generated template repository") < publish_step_names.index(
        "Create generated template release"
    )


def test_prepare_template_release_workflow_opens_release_pr() -> None:
    workflow_text = Path(".github/workflows/prepare-template-release.yml").read_text(
        encoding="utf-8"
    )
    workflow = yaml.safe_load(workflow_text)
    job = workflow["jobs"]["prepare-template-release"]
    steps = job["steps"]
    commands = "\n".join(step["run"] for step in steps if "run" in step)
    app_token_step = next(step for step in steps if step["name"] == "Create release app token")
    checkout_step = next(step for step in steps if step["name"] == "Checkout release source")
    prepare_step = next(
        step for step in steps if step["name"] == "Prepare template release contract"
    )

    assert workflow["name"] == "Prepare Template Release"
    assert "workflow_dispatch" in workflow[True]
    assert workflow_text.index("release_type:") < workflow_text.index("base_ref:")
    assert workflow[True]["workflow_dispatch"]["inputs"]["base_ref"]["default"] == "main"
    assert (
        "use main for normal template-only releases, not an action tag"
        in workflow[True]["workflow_dispatch"]["inputs"]["base_ref"]["description"]
    )
    assert "options:" in workflow_text
    assert "- patch" in workflow_text
    assert "- minor" in workflow_text
    assert "- major" in workflow_text
    assert "release_notes:" not in workflow_text
    assert workflow["permissions"] == {"contents": "read"}
    assert "permissions" not in job
    assert app_token_step["with"]["permission-contents"] == "write"
    assert app_token_step["with"]["permission-pull-requests"] == "write"
    assert checkout_step["with"]["fetch-depth"] == 0
    assert prepare_step["env"]["GH_TOKEN"] == "${{ steps.app-token.outputs.token }}"
    assert "scripts/prepare_template_release.py" in commands
    assert "--release-type \"${{ inputs.release_type }}\"" in commands
    assert "--release-notes-source .tmp/template-release-prs.json" in commands
    assert "/repos/${GITHUB_REPOSITORY}/commits/${commit}/pulls" in commands
    assert "unique_by(.number)" in commands
    assert "git add template-contract.yml" in commands
    assert 'git push --force-with-lease origin "HEAD:${BRANCH}"' in commands
    assert "gh pr create" in commands
    assert "gh pr edit" in commands
    assert '--base "${BASE_REF#refs/heads/}"' in commands


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
    assert "Upload collect provenance artifact" not in [
        step.get("name") for step in _steps()
    ]


def test_publish_pages_replaces_dashboard_mode_output() -> None:
    outputs = _action()["outputs"]
    description = outputs["publish-pages"]["description"]

    assert "dashboard-mode" not in outputs
    assert "publishes" in description
    assert "GitHub Pages" in description


def test_update_docs_metadata_contract() -> None:
    action = _action()
    inputs = action["inputs"]
    outputs = action["outputs"]

    assert "update-docs" in inputs["mode"]["description"]
    assert outputs["update-docs-state"]["value"] == "${{ steps.runtime.outputs.update-docs-state }}"
    assert "update-docs-reason" not in outputs
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
    assert inputs["incident-confirm-next-secret"]["default"] == ""
    assert (
        runtime_env["REPONOMICS_INCIDENT_CONFIRM_NEXT_SECRET"]
        == "${{ inputs.incident-confirm-next-secret }}"
    )
    assert purge["if"] == "${{ inputs.mode == 'incident-reset' }}"
    assert purge["env"]["REPONOMICS_INCIDENT_RESET_PURGE_ONLY"] == "true"
    assert (
        purge["env"]["REPONOMICS_INCIDENT_CONFIRM_NEXT_SECRET"]
        == "${{ inputs.incident-confirm-next-secret }}"
    )
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
    assert _step_index("Clean up superseded dashboard data artifacts") < _step_index(
        "Purge incident reset history"
    )


def test_publish_pages_input_metadata_contract() -> None:
    action = _action()
    runtime_env = _step_by_name("Run Reponomics runtime")["env"]

    assert action["inputs"]["publish-pages"]["default"] == ""
    assert runtime_env["REPONOMICS_PUBLISH_PAGES"] == "${{ inputs.publish-pages }}"
    assert action["inputs"]["require-collect-provenance"]["default"] == "false"
    assert "REPONOMICS_REQUIRE_COLLECT_PROVENANCE" not in runtime_env


def test_use_github_app_input_metadata_contract() -> None:
    action = _action()
    runtime_env = _step_by_name("Run Reponomics runtime")["env"]

    assert action["inputs"]["use-github-app"]["default"] == ""
    assert runtime_env["REPONOMICS_USE_GITHUB_APP"] == "${{ inputs.use-github-app }}"
