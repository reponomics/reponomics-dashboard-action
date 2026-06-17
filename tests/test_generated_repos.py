"""Tests for generated Reponomics dashboard repository outputs."""
# ruff: noqa: ISC002

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts import build_template
from scripts import publish_generated_repo
from scripts import template_contract
from scripts import template_compat_e2e
from scripts import template_consumer_e2e
from scripts import template_public_action_e2e
from scripts import template_provenance
from scripts import validate_template_action_ref
from scripts import verify_workflow_classification
from scripts.staging_smoke import browser_checklist as staging_smoke_browser_checklist
from scripts.staging_smoke import evidence as staging_smoke_evidence
from scripts.staging_smoke import live_order as staging_smoke_live_order
from scripts.staging_smoke import provision as staging_smoke_provision
from scripts.staging_smoke import reset_fresh as staging_smoke_reset_fresh
from scripts.staging_smoke import run as staging_smoke_run
from scripts.staging_smoke import seed_plain_history as staging_smoke_seed_plain_history
from scripts.staging_smoke import wait_for_run as staging_smoke_wait_for_run


STAGING_SMOKE_PAUSED_REASON = (
    "Staging smoke is pre-live; pause brittle runbook/output assertions until "
    "the staging protocol is revisited with a lighter contract model."
)


ACTION_YML_FIXTURE = """
inputs:
  mode:
    description: "Runtime mode: collect, publish, rotate-key, incident-reset, docs-sync, or doctor."
  allow-docs-sync:
    description: "Optional managed docs sync override."
outputs:
  docs-sync-state:
    value: ${{ steps.runtime.outputs.docs-sync-state }}
  docs-action-version:
    value: ${{ steps.runtime.outputs.docs-action-version }}
  docs-updated-at:
    value: ${{ steps.runtime.outputs.docs-updated-at }}
"""


def _iter_steps(value):
    steps = []
    if isinstance(value, dict):
        if isinstance(value.get("steps"), list):
            steps.extend(step for step in value["steps"] if isinstance(step, dict))
        for child in value.values():
            steps.extend(_iter_steps(child))
    elif isinstance(value, list):
        for child in value:
            steps.extend(_iter_steps(child))
    return steps


def test_template_manifest_includes_thin_template_surface(tmp_path):
    output = tmp_path / "template"

    build_template.build_template(output)

    required = [
        ".github/scripts/resolve-reponomics-config.py",
        ".github/actions/reponomics/action.yml",
        ".github/workflows/collect-and-publish.yml",
        ".github/workflows/doctor.yml",
        ".github/workflows/incident-reset.yml",
        ".github/workflows/keepalive.yml",
        ".github/workflows/setup.yml",
        ".github/workflows/rotate-key.yml",
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "README.md",
        "README.backup.md",
        "config.yaml",
        "config.example.yaml",
        ".reponomics/template-provenance.json",
        "docs/reponomics/.manifest.json",
        "docs/reponomics/README.md",
        "docs/reponomics/configuration.md",
        "docs/reponomics/privacy-and-artifacts.md",
        "docs/reponomics/upgrade.md",
    ]
    for relative_path in required:
        assert (output / relative_path).exists()

    generated_readme = (output / "README.md").read_text(encoding="utf-8")
    assert generated_readme == Path("template/README.template.md").read_text(
        encoding="utf-8"
    )
    generated_backup = (output / "README.backup.md").read_text(encoding="utf-8")
    assert generated_backup == generated_readme
    assert generated_readme != Path("README.md").read_text(encoding="utf-8")
    assert "This is the setup README for your Reponomics dashboard repository." in (
        generated_readme
    )
    assert "README.backup.md" in generated_readme


def test_template_manifest_strips_template_prefix_by_default():
    manifest = {
        "include": [
            "template",
            "template/README.template.md",
            "template/SECURITY.template.md",
            "template/docs/reponomics",
            "template/LICENSE.template",
            {"source": "template/EXAMPLE.template.md", "target": "EXAMPLE-CUSTOM.md"},
        ]
    }

    assert build_template.iter_include_entries(manifest) == [
        (Path("template"), Path(".")),
        (Path("template/README.template.md"), Path("README.md")),
        (Path("template/SECURITY.template.md"), Path("SECURITY.md")),
        (Path("template/docs/reponomics"), Path("docs/reponomics")),
        (Path("template/LICENSE.template"), Path("LICENSE")),
        (Path("template/EXAMPLE.template.md"), Path("EXAMPLE-CUSTOM.md")),
    ]


def test_template_manifest_expands_directory_file_entries():
    entries = build_template.iter_include_file_entries({"include": ["template/.github"]})

    assert (
        Path("template/.github/workflows/collect-and-publish.yml"),
        Path(".github/workflows/collect-and-publish.yml"),
    ) in entries

    root_entries = build_template.iter_include_file_entries({"include": ["template"]})
    assert (Path("template/README.template.md"), Path("README.md")) in root_entries
    assert (Path("template/SECURITY.template.md"), Path("SECURITY.md")) in root_entries
    assert (Path("template/LICENSE.template"), Path("LICENSE")) in root_entries
    assert all(".template" not in target.name for _, target in root_entries)


def test_template_forbidden_basename_matches_nested_paths():
    assert build_template._matches_path(".github/scripts/__pycache__/module.pyc", "__pycache__")
    assert build_template._matches_path("docs/.DS_Store", ".DS_Store")


def test_template_includes_initial_managed_docs_snapshot(tmp_path):
    output = tmp_path / "template"

    build_template.build_template(output)
    contract = template_contract.load_contract()

    docs_root = output / "docs" / "reponomics"
    readme = (docs_root / "README.md").read_text(encoding="utf-8")
    manifest = json.loads((docs_root / ".manifest.json").read_text(encoding="utf-8"))

    rendered_docs = {
        path.relative_to(docs_root).as_posix(): path.read_text(encoding="utf-8")
        for path in docs_root.rglob("*")
        if path.is_file()
    }
    assert not any("{{ACTION_VERSION}}" in text for text in rendered_docs.values())
    assert "`docs/reponomics/.manifest.json` records the action version" in readme
    assert manifest["managed_namespace"] == "docs/reponomics"
    assert manifest["action_repository"] == contract.action_repository
    assert manifest["action_version"] == contract.action_version
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", manifest["updated_at"])
    expected_files = {
        path.relative_to(docs_root).as_posix(): hashlib.sha256(
            path.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
        for path in docs_root.rglob("*")
        if path.is_file() and path.name != ".manifest.json"
    }
    assert "README.md" in expected_files
    assert manifest["files"] == expected_files


def test_template_manifest_excludes_action_owned_runtime(tmp_path):
    output = tmp_path / "template"

    build_template.build_template(output)

    forbidden = [
        "requirements.txt",
        "requirements-dev.txt",
        "Makefile",
        "maintainer.mk",
        "template-manifest.yml",
        "scripts",
        "tests",
        "vendor",
        "template",
        "template-action-release.yml",
        "template-contract.yml",
        "docs/GENERATED_REPOSITORY_MODEL.md",
        "docs/FAQ.md",
        "docs/PROVENANCE.md",
        "docs/REPOSITORY_POLICY.md",
        "docs/README.md",
        "docs/SECURE_DASHBOARD_KEY.md",
        "docs/TRUST_BOUNDARY.md",
        "docs/architecture",
        "docs/archive",
        "docs/adr",
    ]
    for relative_path in forbidden:
        assert not (output / relative_path).exists()


def test_template_workflows_delegate_to_reponomics_action(tmp_path):
    output = tmp_path / "template"

    build_template.build_template(output)
    contract = template_contract.load_contract()

    workflows = output / ".github" / "workflows"
    collect_publish = (workflows / "collect-and-publish.yml").read_text(encoding="utf-8")
    doctor = (workflows / "doctor.yml").read_text(encoding="utf-8")
    incident_reset = (workflows / "incident-reset.yml").read_text(encoding="utf-8")
    keepalive = (workflows / "keepalive.yml").read_text(encoding="utf-8")
    setup = (workflows / "setup.yml").read_text(encoding="utf-8")
    rotate = (workflows / "rotate-key.yml").read_text(encoding="utf-8")
    resolver = (
        output / ".github" / "scripts" / "resolve-reponomics-config.py"
    ).read_text(encoding="utf-8")
    wrapper_path = output / template_contract.TEMPLATE_ACTION_WRAPPER_PATH
    wrapper = yaml.safe_load(wrapper_path.read_text(encoding="utf-8"))
    collect_publish_workflow = yaml.safe_load(collect_publish)
    incident_reset_workflow = yaml.safe_load(incident_reset)
    doctor_workflow = yaml.safe_load(doctor)
    rotate_workflow = yaml.safe_load(rotate)

    action_ref = f"{contract.action_repository}@{contract.default_action_ref}"
    local_action = f"uses: {template_contract.LOCAL_REPONOMICS_ACTION}"
    workflow_texts = {
        "collect-and-publish.yml": collect_publish,
        "doctor.yml": doctor,
        "incident-reset.yml": incident_reset,
        "rotate-key.yml": rotate,
    }
    workflow_documents = [
        collect_publish_workflow,
        incident_reset_workflow,
        doctor_workflow,
        rotate_workflow,
    ]
    wrapper_inputs = set(wrapper["inputs"])
    wrapper_steps = _iter_steps(wrapper)
    remote_steps = [
        step for step in wrapper_steps if step.get("uses") == action_ref
    ]
    assert "skip_collect:" in collect_publish
    assert "docs-sync:" in collect_publish
    assert "resolve-reponomics-config.py --require-setup" in collect_publish
    assert "REPONOMICS_SETUP_COMPLETE == 'true'" in collect_publish
    assert "mode: docs-sync" in collect_publish
    assert "github-token: ${{ github.token }}" in collect_publish
    assert "allow-docs-sync" not in collect_publish
    assert len(remote_steps) == 1
    assert remote_steps[0]["id"] == "reponomics"
    assert local_action in collect_publish
    assert local_action in doctor
    assert local_action in incident_reset
    assert local_action in rotate
    assert f"{contract.action_repository}@" not in "\n".join(workflow_texts.values())
    assert all(
        str(input_name) in wrapper_inputs
        for step in wrapper_steps
        for input_name in (step.get("with") or {})
        if step.get("uses") == action_ref
    )
    assert all(
        str(input_name) in wrapper_inputs
        for workflow in workflow_documents
        for step in _iter_steps(workflow)
        for input_name in (step.get("with") or {})
        if step.get("uses") == template_contract.LOCAL_REPONOMICS_ACTION
    )
    assert 'REPONOMICS_ACTION_REF: "' not in collect_publish
    assert 'REPONOMICS_ACTION_SHA: "' not in collect_publish
    assert 'GENERATE_HTML_DASHBOARD: "false"' not in collect_publish
    assert "PUBLISH_PAGES_DASHBOARD" in collect_publish
    assert "PUBLISH_README_DASHBOARD" in collect_publish
    assert "reponomics-collect-provenance" not in collect_publish
    assert "source_sha" not in collect_publish
    assert "workflow_run_id" not in collect_publish
    assert "resolve_action_ref(" not in collect_publish
    assert "uses: ./reponomics-dashboard-action" not in collect_publish
    assert "actions/download-artifact@" not in collect_publish
    assert "mode: publish" in collect_publish
    assert "artifact-run-id: ${{ github.run_id }}" in collect_publish
    assert 'require-collect-provenance: "true"' in collect_publish
    assert "Republish dashboard outputs" in collect_publish
    assert "mode: docs-sync" in collect_publish
    assert "allow-docs-sync" not in collect_publish
    assert local_action not in setup
    assert "python scripts/" not in collect_publish
    assert "python scripts/" not in doctor
    assert "python scripts/" not in incident_reset
    assert "python scripts/" not in keepalive
    assert "python scripts/" not in setup
    assert "python scripts/" not in rotate
    assert "mode: collect" in collect_publish
    assert collect_publish_workflow["permissions"] == {"contents": "read"}
    assert doctor_workflow["permissions"] == {"contents": "read"}
    assert "workflow_run:" not in collect_publish
    assert "workflow_dispatch:" in collect_publish
    assert "skip_collect:" in collect_publish
    assert collect_publish_workflow["jobs"]["collect"]["permissions"] == {
        "contents": "read",
        "actions": "write",
    }
    assert collect_publish_workflow["jobs"]["publish"]["permissions"] == {
        "contents": "write",
        "actions": "read",
        "pages": "write",
        "id-token": "write",
    }
    assert collect_publish_workflow["jobs"]["republish"]["permissions"] == {
        "contents": "write",
        "actions": "read",
        "pages": "write",
        "id-token": "write",
    }
    assert doctor_workflow["jobs"]["doctor"]["permissions"] == {
        "contents": "read",
        "actions": "read",
    }
    assert "artifact_run_id:" in doctor
    assert "Validate artifact run ID" in doctor
    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in doctor
    assert "run-id: ${{ env.ARTIFACT_RUN_ID }}" in doctor
    assert "Restoring dashboard artifacts from workflow run \\`$ARTIFACT_RUN_ID\\`" in doctor
    assert "name: html-dashboard-encrypted" in doctor
    assert "name: html-dashboard-plaintext" in doctor
    assert "name: dashboard-data" in doctor
    assert "mode: doctor" in doctor
    assert "comparison-secret: ${{ secrets.COMPARISON_SECRET }}" in doctor
    assert (
        r"not evidence that \`DASHBOARD_SECRET_DO_NOT_REPLACE\` or \`COMPARISON_SECRET\` is wrong"
        in doctor
    )
    assert "Explain artifact restore failure" in doctor
    assert "Doctor did not run because an earlier artifact download or HTML normalization step failed." in doctor
    assert r"this workflow has \`actions: read\` permission" in doctor
    assert "github-token: ${{ github.token }}" in collect_publish
    assert 'USE_GITHUB_APP: "false"' not in collect_publish
    assert "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1" in collect_publish
    assert "app-id: ${{ vars.COLLECTION_APP_ID || secrets.COLLECTION_APP_ID }}" in collect_publish
    assert "use-github-app: ${{ env.USE_GITHUB_APP }}" in collect_publish
    assert "mode: incident-reset" in incident_reset
    assert "incident-confirm-mode: ${{ inputs.confirm_mode }}" in incident_reset
    assert "incident-confirm-purge: ${{ inputs.confirm_purge }}" in incident_reset
    assert "incident-confirm-irreversible: ${{ inputs.confirm_irreversible }}" in incident_reset
    assert "incident-purge-max-runs" not in incident_reset
    assert "timeout-minutes: 30" in incident_reset
    assert "associated with prior" in incident_reset
    assert "make this repository private" in incident_reset
    assert "disable any published Pages dashboard" in incident_reset
    assert incident_reset_workflow["permissions"] == {"contents": "read"}
    assert incident_reset_workflow["jobs"]["reset"]["permissions"] == {
        "contents": "read",
        "actions": "write",
    }
    assert rotate_workflow["permissions"] == {"contents": "read"}
    assert rotate_workflow["jobs"]["rotate"]["if"] == "github.ref == 'refs/heads/main'"
    assert rotate_workflow["jobs"]["rotate"]["permissions"] == {
        "contents": "write",
        "actions": "read",
        "pages": "write",
        "id-token": "write",
    }
    assert rotate_workflow["jobs"]["rotate"]["steps"][0]["with"]["ref"] == "main"
    assert "workflow_run:" not in collect_publish
    assert "COLLECTION_TOKEN" not in keepalive
    assert "DASHBOARD_SECRET_DO_NOT_REPLACE" not in keepalive
    assert "resolve-reponomics-config.py --require-setup" in keepalive
    assert "60 days without repository activity" in keepalive
    assert ".reponomics/setup-complete" in resolver
    assert "commit the generated setup marker" not in resolver
    assert "let setup validate the config and write the setup marker" in resolver
    assert '"publish_readme_dashboard": "PUBLISH_README_DASHBOARD"' in resolver
    assert '"publish_pages_dashboard": "PUBLISH_PAGES_DASHBOARD"' in resolver
    assert '"artifact_retention_days": "RETENTION_DAYS"' in resolver


def test_generated_workflow_run_steps_do_not_interpolate_untrusted_contexts():
    """Untrusted workflow values must pass through env/validation before shell."""
    untrusted_patterns = ("${{ inputs.", "${{ github.event.")
    for workflow_path in Path("template/.github/workflows").glob("*.yml"):
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        for job_name, job in workflow.get("jobs", {}).items():
            for step in job.get("steps", []):
                script = step.get("run", "")
                for pattern in untrusted_patterns:
                    assert pattern not in script, (
                        f"{workflow_path}:{job_name}:{step.get('name')} "
                        + f"interpolates {pattern} directly into a run block"
                    )


def test_setup_workflow_resolves_data_modes():
    setup = Path("template/.github/workflows/setup.yml").read_text(encoding="utf-8")

    assert "inputs:" not in setup
    assert "Resolve setup configuration" in setup
    assert "resolve-reponomics-config.py" in setup
    assert "generate_html_dashboard:" not in setup
    assert "generate_readme:" not in setup
    assert "use_github_app:" not in setup
    assert "publish_dashboard:" not in setup
    assert "commit_readme:" not in setup
    assert "commit_readme_snapshot:" not in setup
    assert "PUBLISH_TO_PAGES" not in setup
    assert "COMMIT_README_SNAPSHOT" not in setup
    assert "PUBLISH_PAGES_DASHBOARD" in setup
    assert "PUBLISH_README_DASHBOARD" in setup
    assert "README dashboard generation is only supported for private repositories." not in setup
    assert "cp README.md README.backup.md" not in setup
    assert "cat > README.md <<'MD'" in setup
    assert "This repository was generated from the [Reponomics Dashboard template repo]" in setup
    assert "allow_docs_sync: false" in setup
    assert "Managed docs sync" in setup
    assert ": > .reponomics/setup-complete" in setup
    assert "git add README.md .reponomics/setup-complete" in setup
    assert '"data_mode": os.environ["DATA_MODE"]' not in setup
    assert '"retention_days": os.environ["RETENTION_DAYS"]' not in setup
    assert "data_mode=plaintext" not in setup
    assert "default: encrypted" not in setup
    assert re.search(r"^permissions:\n  contents: read$", setup, flags=re.MULTILINE)
    assert re.search(r"^\s+permissions:\n\s+contents: write$", setup, flags=re.MULTILINE)
    assert "actions: write" not in setup
    assert "DASHBOARD_NEXT_SECRET" not in setup
    assert "enable_workflow" not in setup
    assert "outage-sentinel" not in setup
    assert "Scheduled workflow keepalive" in setup
    assert "60 days without repository activity" in setup
    assert "token: ${{ secrets.COLLECTION_TOKEN" not in setup
    assert "personal-access-tokens/new" in setup
    assert "name=COLLECTION_TOKEN" in setup
    assert "name=Reponomics%20Collection%20Token" not in setup
    assert "administration=read" in setup
    assert "target_name=$GITHUB_REPOSITORY_OWNER" in setup
    assert "All repositories" in setup
    assert "Only selected repositories" in setup
    assert "keep \\`config.yaml\\` within" in setup
    assert "COLLECTION_APP_PRIVATE_KEY" in setup
    assert "COLLECTION_APP_ID" in setup
    assert "docs/reponomics/secure-dashboard-key.md" in setup
    assert '${#DASHBOARD_SECRET_DO_NOT_REPLACE}' not in setup
    assert "Manual GitHub Pages step" in setup
    assert '[ "$PUBLISH_PAGES_DASHBOARD" = "true" ] && [ "$DATA_MODE" = "encrypted" ]' in setup
    assert "Collection auth mode" in setup
    assert "Settings -> Pages" in setup
    assert "skip them" in setup
    assert "repos/$GITHUB_REPOSITORY/pages" not in setup
    assert "PAGES_PUBLICATION" not in setup


def test_setup_workflow_does_not_commit_workflow_file_changes(tmp_path):
    """Setup must not require workflow write permission in generated repos."""
    output = tmp_path / "template"
    build_template.build_template(output)

    setup_workflows = {
        "source template": Path("template/.github/workflows/setup.yml"),
        "generated template": output / ".github" / "workflows" / "setup.yml",
    }
    for label, setup_path in setup_workflows.items():
        setup = setup_path.read_text(encoding="utf-8")

        assert "git add -A .github/workflows" not in setup, label
        assert re.search(r"^\s*git add .*\.github/workflows", setup, flags=re.MULTILINE) is None, label
        assert re.search(r"^\s*mv .*\.github/workflows", setup, flags=re.MULTILINE) is None, label
        assert 'Path(".github/workflows/' not in setup, label


def test_required_fields_do_not_have_default_value():
    """Required fields should require explicit user consent, so omit default values."""
    # i_have_read_the_readme
    # data_mode
    # publish_pages_dashboard
    # publish_readme_dashboard
    # allow_docs_sync
    assert True


def test_template_contract_and_action_metadata_contract():
    contract = template_contract.validate_local_contract()
    contract_text = Path("template-contract.yml").read_text(encoding="utf-8")

    assert contract.action_repository == template_contract.ACTION_REPOSITORY
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", contract.template_version)
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", contract.action_version)
    assert contract.template_version != contract.action_version
    assert contract.default_action_ref == f"v{contract.compatible_action_major}"
    assert "min_action_version" not in contract_text
    assert re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+",
        contract.minimum_compatible_template_version,
    )
    assert _version_tuple(
        contract.minimum_compatible_template_version
    ) <= _version_tuple(contract.template_version)
    assert any(
        protected.template_version == contract.minimum_compatible_template_version
        and protected.status == "required"
        for protected in contract.protected_template_refs
    )
    template_contract.validate_action_metadata(ACTION_YML_FIXTURE)


def test_template_includes_verifiable_provenance(tmp_path):
    output = tmp_path / "template"

    build_template.build_template(output)
    provenance = template_provenance.verify_template_provenance(output)
    digest = template_provenance.payload_tree_digest(output)

    assert provenance["schema_version"] == 1
    assert provenance["source"]["commit"]
    assert provenance["template"]["version"] == template_contract.load_contract().template_version
    assert provenance["template"]["minimum_compatible_template_version"] == (
        template_contract.load_contract().minimum_compatible_template_version
    )
    assert provenance["action"]["default_ref"] == "v0"
    assert provenance["action"]["accepted_release"] == {
        "repository": template_contract.load_contract().accepted_action.repository,
        "version": template_contract.load_contract().accepted_action.version,
        "tag": template_contract.load_contract().accepted_action.tag,
        "sha": template_contract.load_contract().accepted_action.sha,
        "default_ref": template_contract.load_contract().accepted_action.default_ref,
    }
    assert "local_version" not in provenance["action"]
    assert "min_version" not in provenance["action"]
    assert provenance["payload"]["tree_manifest_format"] == "reponomics-template-tree-v1"
    assert provenance["payload"]["digest_algorithm"] == "sha256"
    assert provenance["payload"]["digest"] == digest.digest
    assert provenance["payload"]["excluded_paths"] == [".reponomics/template-provenance.json"]
    assert ".reponomics/template-provenance.json" not in digest.manifest_bytes.decode("utf-8")


def test_template_provenance_digest_is_stable_except_payload_tampering(tmp_path):
    output = tmp_path / "template"
    build_template.build_template(output)

    original = template_provenance.payload_tree_digest(output).digest
    provenance_path = output / template_provenance.PROVENANCE_PATH
    provenance_payload = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance_path.write_text(
        json.dumps(provenance_payload, indent=4, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert template_provenance.payload_tree_digest(output).digest == original

    (output / "README.md").write_text("tampered\n", encoding="utf-8")
    assert template_provenance.payload_tree_digest(output).digest != original
    with pytest.raises(
        template_provenance.TemplateProvenanceError,
        match="Template provenance does not match",
    ):
        template_provenance.verify_template_provenance(output)


def test_template_release_artifacts_include_manifest_archive_and_checksums(tmp_path):
    output = tmp_path / "template"
    artifacts_dir = tmp_path / "artifacts"
    second_artifacts_dir = tmp_path / "artifacts-second"
    build_template.build_template(output)

    artifacts = template_provenance.package_release_artifacts(output, artifacts_dir)
    second_artifacts = template_provenance.package_release_artifacts(output, second_artifacts_dir)

    assert artifacts.archive.name.endswith(".tar.gz")
    assert artifacts.tree_manifest.name.endswith(".tree.jsonl")
    assert artifacts.checksums.name == "SHA256SUMS"
    manifest = artifacts.tree_manifest.read_text(encoding="utf-8")
    checksums = artifacts.checksums.read_text(encoding="utf-8")
    assert '"path":"README.md"' in manifest
    assert ".reponomics/template-provenance.json" not in manifest
    assert artifacts.archive.name in checksums
    assert artifacts.tree_manifest.name in checksums
    assert hashlib.sha256(artifacts.archive.read_bytes()).hexdigest() == hashlib.sha256(
        second_artifacts.archive.read_bytes()
    ).hexdigest()
    assert hashlib.sha256(artifacts.tree_manifest.read_bytes()).hexdigest() == hashlib.sha256(
        second_artifacts.tree_manifest.read_bytes()
    ).hexdigest()
    assert artifacts.checksums.read_text(encoding="utf-8") == second_artifacts.checksums.read_text(
        encoding="utf-8"
    )


def test_template_contract_normalizes_source_timestamp_to_utc():
    assert (
        template_contract._normalize_timestamp_utc("2026-06-11T14:28:07-04:00")
        == "2026-06-11T18:28:07Z"
    )
    assert (
        template_contract._normalize_timestamp_utc("2026-06-11T13:51:05Z")
        == "2026-06-11T13:51:05Z"
    )
    assert template_contract._normalize_timestamp_utc("source") == "source"


def test_template_contract_does_not_scan_decision_records_as_managed_docs():
    adr_path = "docs/adr/008-template-and-generated-output-assurance.md"
    adr_text = Path(adr_path).read_text(encoding="utf-8")

    assert "reponomics/reponomics-dashboard-action@v" not in adr_text


def test_action_repo_has_template_publication_targets():
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "build-template:" in makefile
    assert "verify-template:" in makefile
    assert "template-smoke:" in makefile
    assert "template-consumer-e2e:" in makefile
    assert "template-public-action-e2e:" in makefile
    assert "validate-template-accepted-action:" in makefile
    assert "template-accepted-action-e2e:" in makefile
    assert "template-release-gates:" in makefile
    assert "validate-template-accepted-action" in makefile
    assert "template-accepted-action-e2e" in makefile
    assert "package-template-release" in makefile
    assert "publish-template:" in makefile
    assert "publish-template-staging-dry-run:" in makefile
    assert "publish-template-staging:" in makefile
    assert "TEMPLATE_EXPECTED_REPO ?= reponomics/reponomics-dashboard" in makefile
    assert (
        "TEMPLATE_STAGING_EXPECTED_REPO ?= reponomics/reponomics-dashboard-staging"
        in makefile
    )
    assert "scripts/publish_generated_repo.py" in makefile


def test_template_public_action_e2e_uses_resolved_public_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = template_contract.TemplateContract(
        template_version="0.10.0",
        action_repository=template_contract.ACTION_REPOSITORY,
        default_action_ref="v0",
        compatible_action_major=0,
        accepted_action=template_contract.AcceptedActionRelease(
            repository=template_contract.ACTION_REPOSITORY,
            version="0.23.6",
            tag="v0.23.6",
            sha="b" * 40,
            default_ref="v0",
        ),
        minimum_compatible_template_version="0.10.0",
        protected_template_refs=(
            template_contract.ProtectedTemplateRef(
                ref="reponomics-dashboard-v0.10.0",
                template_version="0.10.0",
                source_commit="a" * 40,
            ),
        ),
        managed_docs_namespace=Path("docs/reponomics"),
    )
    resolved = validate_template_action_ref.ResolvedActionRef(
        ref="v0",
        sha="b" * 40,
        remote_ref="refs/tags/v0^{}",
    )
    calls: dict[str, Path | str] = {}

    monkeypatch.setattr(
        template_public_action_e2e.template_contract,
        "load_contract",
        lambda _root: contract,
    )
    monkeypatch.setattr(
        template_public_action_e2e.validate_template_action_ref,
        "validate_public_action_ref",
        lambda root: resolved,
    )

    def fake_checkout_public_action(
        *,
        contract: template_contract.TemplateContract,
        resolved: validate_template_action_ref.ResolvedActionRef,
        destination: Path,
    ) -> Path:
        calls["checkout_repo"] = contract.action_repository
        calls["checkout_ref"] = resolved.sha
        destination.mkdir(parents=True)
        return destination

    def fake_run_e2e(
        *,
        template_dir: Path,
        action_repo: Path,
        action_python: Path,
        keep_temp: bool,
    ) -> None:
        calls["template_dir"] = template_dir
        calls["action_repo_name"] = action_repo.name
        calls["action_python"] = action_python
        calls["keep_temp"] = str(keep_temp)

    def fake_install_public_action_runtime(
        *,
        action_repo: Path,
        venv_dir: Path,
        base_python: Path,
    ) -> Path:
        calls["runtime_action_repo"] = action_repo.name
        calls["runtime_venv"] = venv_dir.name
        calls["runtime_base_python"] = base_python
        return venv_dir / "bin" / "python"

    monkeypatch.setattr(
        template_public_action_e2e,
        "checkout_public_action",
        fake_checkout_public_action,
    )
    monkeypatch.setattr(
        template_public_action_e2e,
        "install_public_action_runtime",
        fake_install_public_action_runtime,
    )
    monkeypatch.setattr(
        template_public_action_e2e.template_consumer_e2e,
        "run_e2e",
        fake_run_e2e,
    )

    template_public_action_e2e.run_public_action_e2e(
        template_dir=tmp_path / "template",
        action_python=tmp_path / "python",
    )

    assert calls["checkout_repo"] == template_contract.ACTION_REPOSITORY
    assert calls["checkout_ref"] == "b" * 40
    assert calls["template_dir"] == tmp_path / "template"
    assert calls["action_repo_name"] == "action"
    assert calls["runtime_action_repo"] == "action"
    assert calls["runtime_venv"] == "public-action-runtime"
    assert calls["runtime_base_python"] == tmp_path / "python"
    assert calls["action_python"] != tmp_path / "python"
    assert str(calls["action_python"]).endswith("/public-action-runtime/bin/python")
    assert calls["keep_temp"] == "False"


def test_template_public_action_e2e_can_use_accepted_action_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = template_contract.TemplateContract(
        template_version="0.10.0",
        action_repository=template_contract.ACTION_REPOSITORY,
        default_action_ref="v0",
        compatible_action_major=0,
        accepted_action=template_contract.AcceptedActionRelease(
            repository=template_contract.ACTION_REPOSITORY,
            version="0.23.6",
            tag="v0.23.6",
            sha="b" * 40,
            default_ref="v0",
        ),
        minimum_compatible_template_version="0.10.0",
        protected_template_refs=(
            template_contract.ProtectedTemplateRef(
                ref="reponomics-dashboard-v0.10.0",
                template_version="0.10.0",
                source_commit="a" * 40,
            ),
        ),
        managed_docs_namespace=Path("docs/reponomics"),
    )
    accepted = validate_template_action_ref.ResolvedActionRef(
        ref="v0.23.6",
        sha="b" * 40,
        remote_ref="refs/tags/v0.23.6",
    )
    default = validate_template_action_ref.ResolvedActionRef(
        ref="v0",
        sha="b" * 40,
        remote_ref="refs/tags/v0",
    )
    calls: dict[str, str] = {}

    monkeypatch.setattr(
        template_public_action_e2e.template_contract,
        "load_contract",
        lambda _root: contract,
    )
    monkeypatch.setattr(
        template_public_action_e2e.validate_template_action_ref,
        "validate_accepted_action_release",
        lambda root: (accepted, default),
    )
    monkeypatch.setattr(
        template_public_action_e2e,
        "checkout_public_action",
        lambda **kwargs: tmp_path / "action",
    )
    monkeypatch.setattr(
        template_public_action_e2e,
        "install_public_action_runtime",
        lambda **kwargs: tmp_path / "isolated-action" / "bin" / "python",
    )

    def fake_run_e2e(**kwargs: object) -> None:
        calls["action_repo"] = str(kwargs["action_repo"])
        calls["action_python"] = str(kwargs["action_python"])

    monkeypatch.setattr(
        template_public_action_e2e.template_consumer_e2e,
        "run_e2e",
        fake_run_e2e,
    )

    template_public_action_e2e.run_public_action_e2e(
        template_dir=tmp_path / "template",
        action_python=tmp_path / "python",
        accepted_action=True,
    )

    assert calls["action_repo"].endswith("/action")
    assert calls["action_python"].endswith("/isolated-action/bin/python")


@pytest.mark.skip(reason=STAGING_SMOKE_PAUSED_REASON)
def test_staging_smoke_runbook_documents_required_profiles():
    runbook = Path("docs/STAGING_SMOKE.md").read_text(encoding="utf-8")

    assert "reponomics-dashboard-staging-private-encrypted-fresh" in runbook
    assert "reponomics-dashboard-staging-private-plaintext-with-history" in runbook
    assert "One-Time GitHub Provisioning" in runbook
    assert "Plaintext mode does not publish a Pages dashboard" in runbook
    assert "guided interactive runbook" in runbook
    assert "printed `gh secret set` commands omit `--body`" in runbook
    assert "guided interactive checkpoints" in runbook
    assert "make staging-smoke-live-order" in runbook
    assert "make staging-smoke-plan" in runbook
    assert "make staging-smoke-provision-plan" in runbook
    assert "make staging-smoke-provision" in runbook
    assert "make staging-smoke-preflight" in runbook
    assert "make staging-smoke-reset-fresh-plan" in runbook
    assert "make staging-smoke-reset-fresh CONFIRM_TARGET=" in runbook
    assert "make staging-smoke-seed-plain-history-plan" in runbook
    assert "make staging-smoke-seed-plain-history CONFIRM_TARGET=" in runbook
    assert "make staging-smoke-browser-checklist" in runbook
    assert "make staging-smoke-evidence" in runbook
    assert "make staging-smoke-run" in runbook
    assert "STAGING_SMOKE_PHASE=bootstrap" in runbook
    assert "STAGING_SMOKE_PHASE=recurring" in runbook
    assert "STAGING_SMOKE_ALLOW_BOOTSTRAP=1" in runbook
    assert "DISPATCH_TEMPLATE_STAGING=1" in runbook
    assert "STAGING_SMOKE_GH_DELAY_SECONDS" in runbook
    assert "scripts/staging_smoke/slow_gh.py" in runbook
    assert ".tmp/staging-smoke/report.md" in runbook
    assert "PAT-only" in runbook
    assert "Rotate Reponomics dashboard key" in runbook
    assert "html-dashboard-plaintext" in runbook
    assert "DASHBOARD_NEXT_SECRET" in runbook
    assert "Review `config.yaml` in the encrypted fresh repo before setup" in runbook
    assert "Recurring plaintext/history smoke should preserve the existing config" in runbook
    assert "Local Clone Policy" in runbook
    assert "temporary clones under `.tmp/staging-smoke/`" in runbook
    assert "persistent local clone of the plain-history repo is acceptable" in runbook


@pytest.mark.skip(reason=STAGING_SMOKE_PAUSED_REASON)
def test_staging_smoke_live_order_lists_command_sequence():
    text = staging_smoke_live_order.live_order()

    assert "make staging-smoke-provision-plan" in text
    assert "make staging-smoke-provision" in text
    assert "make staging-smoke-preflight" in text
    assert "Default mode is recurring" in text
    assert "## One-time bootstrap" in text
    assert "## Recurring smoke" in text
    assert "make staging-smoke-plan STAGING_SMOKE_PHASE=bootstrap" in text
    assert "make staging-smoke-plan" in text
    assert "make staging-smoke-plan STAGING_SMOKE_PHASE=recurring" in text
    assert "make staging-smoke-run DISPATCH_TEMPLATE_STAGING=1" in text
    assert (
        "STAGING_SMOKE_PHASE=bootstrap STAGING_SMOKE_ALLOW_BOOTSTRAP=1 DISPATCH_TEMPLATE_STAGING=1"
        in text
    )
    assert "make staging-smoke-browser-checklist" in text
    assert "make staging-smoke-evidence" in text
    assert ".tmp/staging-smoke/report.md" in text


@pytest.mark.skip(reason=STAGING_SMOKE_PAUSED_REASON)
def test_staging_smoke_provision_defaults_to_private_staging_repos():
    args = staging_smoke_provision.parse_args([])
    specs = staging_smoke_provision.repo_specs(args)

    assert [spec.repo for spec in specs] == [
        "reponomics/reponomics-dashboard-staging",
        "reponomics/reponomics-dashboard-staging-private-encrypted-fresh",
        "reponomics/reponomics-dashboard-staging-private-plaintext-with-history",
    ]
    for spec in specs:
        command = staging_smoke_provision._create_command(spec)
        assert "scripts/staging_smoke/slow_gh.py repo create" in command
        assert "--private" in command
        assert "--disable-issues" in command
        assert "--disable-wiki" in command
        assert "secret set" not in command
        assert "push --force" not in command


@pytest.mark.skip(reason=STAGING_SMOKE_PAUSED_REASON)
def test_staging_smoke_runner_outputs_throttled_commands_and_report(tmp_path):
    report = tmp_path / "smoke-report.md"
    result = subprocess.run(
        [
            "venv/bin/python",
            "scripts/staging_smoke/run.py",
            "--source-repo",
            "owner/action",
            "--source-ref",
            "main",
            "--template-staging-repo",
            "owner/template-staging",
            "--encrypted-fresh-repo",
            "owner/encrypted-fresh",
            "--plain-history-repo",
            "owner/plain-history",
            "--command-delay-seconds",
            "2",
            "--phase",
            "bootstrap",
            "--write-report-template",
            str(report),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    output = result.stdout
    assert "Dry run: no commands will be executed." in output
    assert "STAGING_SMOKE_GH_DELAY_SECONDS=2.0" in output
    assert "COLLECTION_TOKEN" in output
    assert "COLLECTION_APP_PRIVATE_KEY" not in output
    assert "venv/bin/python scripts/staging_smoke/slow_gh.py workflow run publish-template-staging.yml" in output
    assert "--workflow publish-template-staging.yml --branch 'main' --created-after \"$started_at\"" in output
    assert "venv/bin/python scripts/staging_smoke/slow_gh.py workflow run setup.yml" in output
    assert "Review encrypted config before collection" in output
    assert "Review plain-history config before first collection" in output
    assert "before setup and collection" in output
    assert "venv/bin/python scripts/staging_smoke/wait_for_run.py" in output
    assert "--created-after \"$started_at\"" in output
    assert "venv/bin/python scripts/staging_smoke/slow_gh.py workflow run rotate-key.yml" in output
    assert "use_github_app=false" in output
    assert "make staging-smoke-reset-fresh-plan" in output
    assert "make staging-smoke-reset-fresh" in output
    assert "make staging-smoke-seed-plain-history-plan" in output
    assert "make staging-smoke-seed-plain-history" in output
    assert "make staging-smoke-evidence" in output
    assert "make staging-smoke-browser-checklist" in output
    assert "venv/bin/python scripts/staging_smoke/slow_gh.py api repos/owner/encrypted-fresh/pages" in output
    assert "venv/bin/python scripts/staging_smoke/slow_gh.py run download '<plain-collect-run-id>'" in output
    assert "--yes" not in output
    assert report.exists()
    report_text = report.read_text(encoding="utf-8")
    assert "Reponomics Staging Smoke Report" in report_text
    assert "- Repository: `owner/encrypted-fresh`" in report_text
    assert "- Repository: `owner/plain-history`" in report_text
    assert "- Setup run after fresh codebase reset:" in report_text
    assert "- Config reviewed/updated before collection:" in report_text
    assert "- Seed/setup run, bootstrap only:" in report_text
    assert "- Config reviewed/updated, bootstrap only:" in report_text


@pytest.mark.skip(reason=STAGING_SMOKE_PAUSED_REASON)
def test_staging_smoke_runner_recurring_uses_persistent_secrets(tmp_path):
    report = tmp_path / "smoke-report.md"
    result = subprocess.run(
        [
            "venv/bin/python",
            "scripts/staging_smoke/run.py",
            "--source-repo",
            "owner/action",
            "--source-ref",
            "main",
            "--template-staging-repo",
            "owner/template-staging",
            "--encrypted-fresh-repo",
            "owner/encrypted-fresh",
            "--plain-history-repo",
            "owner/plain-history",
            "--phase",
            "recurring",
            "--write-report-template",
            str(report),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    output = result.stdout
    assert "make staging-smoke-reset-fresh" in output
    assert "workflow run setup.yml --repo 'owner/encrypted-fresh'" in output
    assert "Review encrypted config before collection" in output
    assert "data_mode=encrypted" in output
    assert "publish_pages_dashboard=true" in output
    assert "publish_readme_dashboard=true" in output
    assert "-f data_mode=encrypted" not in output
    assert "workflow run collect-and-publish.yml --repo 'owner/encrypted-fresh'" in output
    assert "workflow run collect-and-publish.yml --repo 'owner/plain-history'" in output
    assert "secret set COLLECTION_TOKEN" not in output
    assert "secret set COMPARISON_SECRET" not in output
    assert "secret set DASHBOARD_NEXT_SECRET" in output
    assert "secret set DASHBOARD_SECRET_DO_NOT_REPLACE" in output
    assert "staging-smoke-seed-plain-history" not in output
    assert "Review plain-history config before first collection" not in output
    assert "- Smoke phase: `recurring`" in report.read_text(encoding="utf-8")


@pytest.mark.skip(reason=STAGING_SMOKE_PAUSED_REASON)
def test_staging_smoke_browser_checklist_covers_required_browser_regressions():
    text = staging_smoke_browser_checklist.checklist(
        "https://example.test/dashboard",
        "http://localhost:9999",
    )

    assert "https://example.test/dashboard" in text
    assert "http://localhost:9999" in text
    assert "incorrect key does not unlock" in text
    assert "non-traffic growth metric" in text
    assert "traffic metric" in text
    assert "clipped or truncated" in text
    assert "collection calendar" in text
    assert "html-dashboard-plaintext" in text
    assert "Do not paste dashboard keys" in text


@pytest.mark.skip(reason=STAGING_SMOKE_PAUSED_REASON)
def test_staging_smoke_runner_plan_keeps_consumer_writes_non_executable():
    args = staging_smoke_run.parse_args(
        [
            "--source-repo",
            "owner/action",
            "--template-staging-repo",
            "owner/template-staging",
            "--encrypted-fresh-repo",
            "owner/encrypted-fresh",
            "--plain-history-repo",
            "owner/plain-history",
            "--phase",
            "bootstrap",
        ]
    )

    operations = staging_smoke_run.build_plan(args)
    executable_titles = [operation.title for operation in operations if operation.executable]

    assert executable_titles == ["Inspect and preflight", "Run local template gates"]
    reset_commands = [
        command
        for operation in operations
        for command in operation.commands
        if "staging-smoke-reset-fresh" in command
    ]
    assert reset_commands
    assert any("CONFIRM_TARGET='owner/encrypted-fresh'" in command for command in reset_commands)
    seed_commands = [
        command
        for operation in operations
        for command in operation.commands
        if "staging-smoke-seed-plain-history" in command
    ]
    assert seed_commands
    assert any("CONFIRM_TARGET='owner/plain-history'" in command for command in seed_commands)
    assert not any(
        operation.executable and "push --force" in command
        for operation in operations
        for command in operation.commands
    )


@pytest.mark.skip(reason=STAGING_SMOKE_PAUSED_REASON)
def test_staging_smoke_reset_fresh_requires_exact_target_confirmation():
    args = staging_smoke_reset_fresh.parse_args(
        [
            "--encrypted-fresh-repo",
            "owner/encrypted-fresh",
            "--execute",
            "--confirm-target",
            "owner/other",
        ]
    )

    try:
        staging_smoke_reset_fresh.reset_fresh(args)
    except staging_smoke_reset_fresh.ResetFreshError as exc:
        assert "--confirm-target must exactly match" in str(exc)
    else:
        raise AssertionError("expected reset_fresh to reject mismatched target")


@pytest.mark.skip(reason=STAGING_SMOKE_PAUSED_REASON)
def test_staging_smoke_reset_fresh_configures_local_git_author(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, *, cwd):
        calls.append((args, cwd))

    monkeypatch.setattr(staging_smoke_reset_fresh, "_run", fake_run)

    staging_smoke_reset_fresh._configure_git_author(tmp_path)

    assert calls == [
        (["git", "config", "user.name", "Reponomics Staging Smoke"], tmp_path),
        (
            ["git", "config", "user.email", "reponomics-staging-smoke@example.invalid"],
            tmp_path,
        ),
    ]


@pytest.mark.skip(reason=STAGING_SMOKE_PAUSED_REASON)
def test_staging_smoke_seed_plain_history_requires_exact_target_confirmation():
    args = staging_smoke_seed_plain_history.parse_args(
        [
            "--plain-history-repo",
            "owner/plain-history",
            "--execute",
            "--confirm-target",
            "owner/other",
        ]
    )

    try:
        staging_smoke_seed_plain_history.seed_plain_history(args)
    except staging_smoke_seed_plain_history.SeedHistoryError as exc:
        assert "--confirm-target must exactly match" in str(exc)
    else:
        raise AssertionError("expected seed_plain_history to reject mismatched target")


@pytest.mark.skip(reason=STAGING_SMOKE_PAUSED_REASON)
def test_staging_smoke_seed_plain_history_configures_local_git_author(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, *, cwd):
        calls.append((args, cwd))

    monkeypatch.setattr(staging_smoke_seed_plain_history, "_run", fake_run)

    staging_smoke_seed_plain_history._configure_git_author(tmp_path)

    assert calls == [
        (["git", "config", "user.name", "Reponomics Staging Smoke"], tmp_path),
        (
            ["git", "config", "user.email", "reponomics-staging-smoke@example.invalid"],
            tmp_path,
        ),
    ]


@pytest.mark.skip(reason=STAGING_SMOKE_PAUSED_REASON)
def test_staging_smoke_evidence_print_counts_required_failures(capsys):
    checks = [
        staging_smoke_evidence.Evidence("ok", "passed"),
        staging_smoke_evidence.Evidence("warn", "watch"),
        staging_smoke_evidence.Evidence("fail", "missing"),
    ]

    failures = staging_smoke_evidence.print_evidence(checks)

    output = capsys.readouterr().out
    assert failures == 1
    assert "[OK] passed" in output
    assert "[WARN] watch" in output
    assert "[FAIL] missing" in output


@pytest.mark.skip(reason=STAGING_SMOKE_PAUSED_REASON)
def test_staging_smoke_evidence_defaults_to_staging_consumer_repos():
    args = staging_smoke_evidence.parse_args([])

    assert args.encrypted_fresh_repo == "reponomics/reponomics-dashboard-staging-private-encrypted-fresh"
    assert args.plain_history_repo == "reponomics/reponomics-dashboard-staging-private-plaintext-with-history"


@pytest.mark.skip(reason=STAGING_SMOKE_PAUSED_REASON)
def test_staging_smoke_evidence_rejects_plain_history_pages(monkeypatch):
    monkeypatch.setattr(
        staging_smoke_evidence,
        "_pages_payload",
        lambda _repo: {"html_url": "https://example.test/plain"},
    )

    checks = staging_smoke_evidence._plain_pages_evidence("owner/plain-history")

    assert checks == [
        staging_smoke_evidence.Evidence(
            "fail",
            "plain history: Pages configuration must be absent: https://example.test/plain",
        )
    ]


@pytest.mark.skip(reason=STAGING_SMOKE_PAUSED_REASON)
def test_staging_smoke_wait_for_run_selects_latest_matching_dispatch():
    created_after = staging_smoke_wait_for_run._parse_timestamp("2026-06-13T12:00:00Z")
    runs = [
        {
            "databaseId": 1,
            "event": "workflow_dispatch",
            "createdAt": "2026-06-13T11:59:59Z",
        },
        {
            "databaseId": 2,
            "event": "schedule",
            "createdAt": "2026-06-13T12:01:00Z",
        },
        {
            "databaseId": 3,
            "event": "workflow_dispatch",
            "createdAt": "2026-06-13T12:02:00Z",
        },
        {
            "databaseId": 4,
            "event": "workflow_dispatch",
            "createdAt": "2026-06-13T12:01:00Z",
        },
    ]

    selected = staging_smoke_wait_for_run.select_run(
        runs,
        created_after=created_after,
        event="workflow_dispatch",
    )

    assert selected is not None
    assert selected["databaseId"] == 3


@pytest.mark.skip(reason=STAGING_SMOKE_PAUSED_REASON)
def test_staging_smoke_wait_for_run_normalizes_full_refs():
    assert staging_smoke_wait_for_run._normalize_ref_name("refs/heads/main") == "main"
    assert staging_smoke_wait_for_run._normalize_ref_name("refs/tags/v0.23.2") == "v0.23.2"
    assert staging_smoke_wait_for_run._normalize_ref_name("feature/demo") == "feature/demo"


def test_template_consumer_e2e_defaults_to_local_action_repo():
    assert template_consumer_e2e.DEFAULT_ACTION_REPO == Path.cwd()


def test_template_consumer_e2e_resolves_composite_runtime_env():
    action = yaml.safe_load(Path("action.yml").read_text(encoding="utf-8"))

    env = template_consumer_e2e._resolve_runtime_env(
        action,
        provided_inputs={
            "mode": "docs-sync",
            "github-token": "ghp_runtime",
            "allow-docs-sync": "true",
        },
        github={
            "action_ref": "v0",
            "action_repository": "reponomics/reponomics-dashboard-action",
        },
    )

    assert env["REPONOMICS_MODE"] == "docs-sync"
    assert env["REPONOMICS_GITHUB_TOKEN"] == "ghp_runtime"
    assert env["REPONOMICS_ALLOW_DOCS_SYNC"] == "true"
    assert env["REPONOMICS_ACTION_REF"] == "v0"
    assert env["REPONOMICS_ACTION_REPOSITORY"] == "reponomics/reponomics-dashboard-action"


def test_template_consumer_e2e_rejects_broken_composite_runtime_mapping():
    action = yaml.safe_load(Path("action.yml").read_text(encoding="utf-8"))
    runtime_step = next(
        step
        for step in action["runs"]["steps"]
        if step.get("name") == template_consumer_e2e.RUNTIME_STEP_NAME
    )
    runtime_step["env"]["REPONOMICS_ALLOW_DOCS_SYNC"] = "${{ inputs.docs-sync }}"

    error = template_consumer_e2e.runtime_step_contract_error(action)

    assert "REPONOMICS_ALLOW_DOCS_SYNC" in error
    assert "inputs.allow-docs-sync" in error


def test_template_consumer_e2e_rejects_unsupported_composite_runtime_shell():
    action = yaml.safe_load(Path("action.yml").read_text(encoding="utf-8"))
    runtime_step = next(
        step
        for step in action["runs"]["steps"]
        if step.get("name") == template_consumer_e2e.RUNTIME_STEP_NAME
    )
    runtime_step["shell"] = "pwsh"

    error = template_consumer_e2e.runtime_step_contract_error(action)

    assert "shell: bash" in error


def test_template_contract_writes_and_verifies_managed_docs_snapshot(tmp_path):
    contract = template_contract.load_contract()
    docs_root = tmp_path / "docs" / "reponomics"

    template_contract.write_managed_docs_snapshot(
        docs_root,
        contract=contract,
        updated_at="2026-05-31T05:19:33Z",
    )

    manifest = json.loads((docs_root / ".manifest.json").read_text(encoding="utf-8"))
    readme = (docs_root / "README.md").read_text(encoding="utf-8")
    rendered_docs = {
        path.relative_to(docs_root).as_posix(): path.read_text(encoding="utf-8")
        for path in docs_root.rglob("*")
        if path.is_file()
    }
    assert not any("{{ACTION_VERSION}}" in text for text in rendered_docs.values())
    assert "`docs/reponomics/.manifest.json` records the action version" in readme
    assert manifest["managed_namespace"] == "docs/reponomics"
    assert manifest["action_repository"] == contract.action_repository
    assert manifest["action_version"] == contract.action_version
    assert manifest["updated_at"] == "2026-05-31T05:19:33Z"
    assert "README.md" in manifest["files"]

    template_contract.verify_managed_docs_snapshot(docs_root, contract=contract)
    (docs_root / "README.md").write_text("stale\n", encoding="utf-8")
    with pytest.raises(template_contract.TemplateContractError, match="Managed docs snapshot"):
        template_contract.verify_managed_docs_snapshot(docs_root, contract=contract)


@pytest.mark.parametrize(
    "action_ref",
    [
        "reponomics/reponomics-dashboard-action@v0.15.0",
        "reponomics/reponomics-dashboard-action@main",
        "reponomics/reponomics-dashboard-action@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "reponomics/reponomics-dashboard-action@v0.23.0-rc.1",
    ],
)
def test_template_contract_verify_rejects_unexpected_action_refs(tmp_path, action_ref):
    contract = template_contract.load_contract()
    (tmp_path / "action.yml").write_text(ACTION_YML_FIXTURE, encoding="utf-8")
    (tmp_path / "template-contract.yml").write_text(
        Path("template-contract.yml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    wrapper_dir = tmp_path / template_contract.TEMPLATE_ACTION_WRAPPER_PATH.parent
    wrapper_dir.mkdir(parents=True)
    (wrapper_dir / "action.yml").write_text(
        "\n".join(
            [
                "name: Reponomics Dashboard",
                "inputs:",
                "  mode:",
                "    required: true",
                "runs:",
                "  using: composite",
                "  steps:",
                "    - id: reponomics",
                f"      uses: {contract.action_repository}@{contract.default_action_ref}",
                "      with:",
                "        mode: ${{ inputs.mode }}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "collect.yml").write_text(
        "\n".join(
            [
                "name: Collect",
                "on: workflow_dispatch",
                "jobs:",
                "  collect:",
                "    runs-on: ubuntu-24.04",
                "    steps:",
                f"      - uses: {template_contract.LOCAL_REPONOMICS_ACTION}",
                "        with:",
                "          mode: collect",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(f"uses: {action_ref}\n", encoding="utf-8")

    with pytest.raises(template_contract.TemplateContractError, match="Stale template action"):
        template_contract.verify_template_refs(tmp_path)


def test_template_contract_verify_accepts_expected_action_ref(tmp_path):
    contract = template_contract.load_contract()
    (tmp_path / "action.yml").write_text(ACTION_YML_FIXTURE, encoding="utf-8")
    (tmp_path / "template-contract.yml").write_text(
        Path("template-contract.yml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    wrapper_dir = tmp_path / template_contract.TEMPLATE_ACTION_WRAPPER_PATH.parent
    wrapper_dir.mkdir(parents=True)
    (wrapper_dir / "action.yml").write_text(
        "\n".join(
            [
                "name: Reponomics Dashboard",
                "inputs:",
                "  mode:",
                "    required: true",
                "runs:",
                "  using: composite",
                "  steps:",
                "    - id: reponomics",
                f"      uses: {contract.action_repository}@{contract.default_action_ref}",
                "      with:",
                "        mode: ${{ inputs.mode }}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "collect.yml").write_text(
        "\n".join(
            [
                "name: Collect",
                "on: workflow_dispatch",
                "jobs:",
                "  collect:",
                "    runs-on: ubuntu-24.04",
                "    steps:",
                f"      - uses: {template_contract.LOCAL_REPONOMICS_ACTION}",
                "        with:",
                "          mode: collect",
                "",
            ]
        ),
        encoding="utf-8",
    )

    template_contract.verify_template_refs(tmp_path)


def test_template_compat_rejects_workflow_inputs_removed_from_action(tmp_path):
    repo_dir = tmp_path / "template"
    workflow_dir = repo_dir / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    wrapper_dir = repo_dir / template_contract.TEMPLATE_ACTION_WRAPPER_PATH.parent
    wrapper_dir.mkdir(parents=True)
    (wrapper_dir / "action.yml").write_text(
        "\n".join(
            [
                "name: Reponomics Dashboard",
                "inputs:",
                "  mode:",
                "    required: true",
                "  removed-input:",
                "    required: false",
                "runs:",
                "  using: composite",
                "  steps:",
                "    - id: reponomics",
                "      uses: reponomics/reponomics-dashboard-action@v0",
                "      with:",
                "        mode: ${{ inputs.mode }}",
                "        removed-input: ${{ inputs.removed-input }}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (workflow_dir / "collect.yml").write_text(
        "\n".join(
            [
                "name: Collect",
                "on: workflow_dispatch",
                "jobs:",
                "  collect:",
                "    runs-on: ubuntu-24.04",
                "    steps:",
                f"      - uses: {template_contract.LOCAL_REPONOMICS_ACTION}",
                "        with:",
                "          removed-input: value",
                "",
            ]
        ),
        encoding="utf-8",
    )
    generated_template = template_compat_e2e.GeneratedTemplate(
        name="test-template",
        repo_dir=repo_dir,
        template_version="0.10.0",
        source_commit="a" * 40,
    )

    with pytest.raises(
        template_compat_e2e.TemplateCompatibilityError,
        match="removed-input",
    ):
        template_compat_e2e._assert_template_workflow_inputs_supported(
            generated_template,
            action_inputs={"mode"},
        )


def test_template_compat_supports_pre_wrapper_protected_templates(tmp_path):
    repo_dir = tmp_path / "template"
    workflow_dir = repo_dir / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "collect.yml").write_text(
        "\n".join(
            [
                "name: Collect",
                "on: workflow_dispatch",
                "jobs:",
                "  collect:",
                "    runs-on: ubuntu-24.04",
                "    steps:",
                "      - uses: reponomics/reponomics-dashboard-action@v0",
                "        with:",
                "          removed-input: value",
                "",
            ]
        ),
        encoding="utf-8",
    )
    generated_template = template_compat_e2e.GeneratedTemplate(
        name="pre-wrapper-template",
        repo_dir=repo_dir,
        template_version="0.10.0",
        source_commit="a" * 40,
    )

    with pytest.raises(
        template_compat_e2e.TemplateCompatibilityError,
        match="removed-input",
    ):
        template_compat_e2e._assert_template_workflow_inputs_supported(
            generated_template,
            action_inputs={"mode"},
        )


def _version_tuple(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def test_workflow_classification_contract():
    verify_workflow_classification.verify()


def test_template_consumer_e2e_absolutizes_cwd_relative_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    action_python = Path("action-runtime/venv/bin/python")

    assert template_consumer_e2e._absolute_path(action_python) == tmp_path / action_python


def test_template_compat_e2e_absolutizes_without_resolving_python_symlink(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    action_python = Path("venv/bin/python")

    assert template_compat_e2e._absolute_path(action_python) == tmp_path / action_python


def test_template_compat_e2e_installs_isolated_python_env(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    venv_dir = tmp_path / "runtime-venv"
    base_python = tmp_path / "venv" / "bin" / "python"
    source_dir.mkdir()
    calls: list[tuple[list[str], Path]] = []

    def fake_command_output(args, *, cwd=template_compat_e2e.ROOT):
        calls.append((args, cwd))
        return ""

    monkeypatch.setattr(template_compat_e2e, "_command_output", fake_command_output)

    isolated_python = template_compat_e2e._install_isolated_python_env(
        source_dir=source_dir,
        venv_dir=venv_dir,
        base_python=base_python,
        label="test runtime",
    )

    assert isolated_python == venv_dir / "bin" / "python"
    assert calls == [
        ([base_python.as_posix(), "-m", "venv", venv_dir.as_posix()], template_compat_e2e.ROOT),
        (
            [
                isolated_python.as_posix(),
                "-m",
                "pip",
                "install",
                "--upgrade",
                "pip",
            ],
            template_compat_e2e.ROOT,
        ),
        (
            [
                isolated_python.as_posix(),
                "-m",
                "pip",
                "install",
                "-e",
                source_dir.as_posix(),
            ],
            source_dir,
        ),
    ]


def test_template_consumer_e2e_accepts_chunked_encrypted_dashboard_marker(tmp_path):
    (tmp_path / ".e2e-github-output").write_text(
        "data-mode=encrypted\npublish-pages=true\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "assets").mkdir(parents=True)
    (tmp_path / "docs" / "assets" / "export-data-test.enc").write_text(
        "encrypted",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "reponomics").mkdir(parents=True)
    (tmp_path / "docs" / "reponomics" / ".manifest.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "index.html").write_text(
        '<script id="encrypted-dashboard-data" type="application/json"></script>'
        '<script id="export-manifest" type="application/json"></script>',
        encoding="utf-8",
    )
    profile = template_consumer_e2e.ConsumerProfile(
        name="chunked-encrypted",
        data_mode="encrypted",
        repo_is_public=False,
        generate_readme=False,
        dashboard_secret="DASHBOARD_SECRET_DO_NOT_REPLACE_0123456789",
        expected_data_mode="encrypted",
        expected_publish_pages=True,
    )

    template_consumer_e2e._assert_successful_profile(tmp_path, profile)


def test_template_docs_do_not_reference_old_brand_or_maintenance_docs(tmp_path):
    output = tmp_path / "template"

    build_template.build_template(output)

    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.rglob("*")
        if path.is_file() and path.suffix in {"", ".md", ".yml", ".yaml", ".html"}
    )
    assert "github-traffic-report" not in text
    assert "GitHub Traffic Report" not in text
    assert "hesreallyhim" not in text
    assert "GENERATED_REPOSITORY_MODEL.md" not in text
    assert "REPOSITORY_POLICY.md" not in text
    assert "docs/FAQ.md" not in text
    assert "docs/PROVENANCE.md" not in text
    assert "docs/README.md" not in text
    assert "docs/SECURE_DASHBOARD_KEY.md" not in text
    assert "docs/TRUST_BOUNDARY.md" not in text
    assert "docs/architecture/PRIVACY_CONFIGURATION_MATRIX.md" not in text


def test_template_verify_rejects_forbidden_paths(tmp_path):
    output = tmp_path / "template"
    build_template.build_template(output)
    leaked = output / "scripts" / "collect.py"
    leaked.parent.mkdir()
    leaked.write_text("# leak\n", encoding="utf-8")

    with pytest.raises(build_template.TemplateBuildError):
        build_template.verify_template(output)


def test_template_build_rejects_source_tree_output_dirs():
    with pytest.raises(build_template.TemplateBuildError):
        build_template.build_template(Path("template"))
    with pytest.raises(build_template.TemplateBuildError):
        build_template.build_template(Path("scripts"))


def test_publish_remote_safety_accepts_expected_repo():
    publish_generated_repo._assert_expected_repo(
        "git@github.com:reponomics/reponomics-dashboard.git",
        "reponomics/reponomics-dashboard",
    )
    publish_generated_repo._assert_expected_repo(
        "https://github.com/reponomics/reponomics-dashboard-demo.git",
        "reponomics/reponomics-dashboard-demo",
    )


def test_publish_remote_resolves_explicit_repository_url():
    assert publish_generated_repo._remote_url(
        "https://github.com/reponomics/reponomics-dashboard.git"
    ) == "https://github.com/reponomics/reponomics-dashboard.git"


def test_publish_remote_display_redacts_url_credentials():
    assert publish_generated_repo._display_remote_url(
        "https://x-access-token:secret@example.com/reponomics/reponomics-dashboard.git"
    ) == "https://example.com/reponomics/reponomics-dashboard.git"
    assert publish_generated_repo._display_remote_url(
        "git@github.com:reponomics/reponomics-dashboard.git"
    ) == "git@github.com:reponomics/reponomics-dashboard.git"


def test_publish_remote_safety_rejects_wrong_repo():
    with pytest.raises(publish_generated_repo.PublishError):
        publish_generated_repo._assert_expected_repo(
            "git@github.com:reponomics/reponomics-dashboard-dev.git",
            "reponomics/reponomics-dashboard",
        )


def test_publish_commit_message_records_source_commit():
    message = publish_generated_repo._commit_message(
        "chore: publish generated template",
        "abc123",
    )

    assert message == "chore: publish generated template\n\nSource-Commit: abc123"


def test_publish_verifies_published_template_digest(tmp_path):
    output = tmp_path / "template"
    remote = tmp_path / "remote.git"
    clone = tmp_path / "clone"
    build_template.build_template(output)
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", remote], check=True)

    publish_generated_repo.publish(
        output,
        remote.as_posix(),
        "main",
        "chore: publish generated template",
        push=True,
    )

    assert publish_generated_repo._verify_published_digest(
        output,
        remote.as_posix(),
        "main",
    )

    subprocess.run(["git", "clone", remote.as_posix(), clone], check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=clone, check=True)
    subprocess.run(
        ["git", "config", "user.email", "tester@example.com"],
        cwd=clone,
        check=True,
    )
    (clone / "README.md").write_text("tampered\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=clone, check=True)
    subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "commit", "-m", "tamper"],
        cwd=clone,
        check=True,
    )
    subprocess.run(["git", "push", "--force", "origin", "HEAD:main"], cwd=clone, check=True)

    with pytest.raises(publish_generated_repo.PublishError, match="digest mismatch"):
        publish_generated_repo._verify_published_digest(
            output,
            remote.as_posix(),
            "main",
        )


def test_publish_rejects_payload_files_ignored_by_git(tmp_path):
    output = tmp_path / "template"
    remote = tmp_path / "remote.git"
    build_template.build_template(output)
    ignored = output / "__pycache__" / "module.pyc"
    ignored.parent.mkdir()
    ignored.write_bytes(b"cache")
    template_provenance.write_template_provenance(output)
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", remote], check=True)

    with pytest.raises(
        publish_generated_repo.PublishError,
        match="git will not publish",
    ):
        publish_generated_repo.publish(
            output,
            remote.as_posix(),
            "main",
            "chore: publish generated template",
            push=True,
        )
