"""Tests for generated Reponomics dashboard repository outputs."""
# ruff: noqa: ISC002

import io
import hashlib
import json
import re
import urllib.error
from email.message import Message
from pathlib import Path

import pytest
import yaml

from scripts import build_template
from scripts import publish_generated_repo
from scripts import sync_action_release
from scripts import template_consumer_e2e
from scripts import verify_workflow_classification


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


def test_template_manifest_includes_thin_template_surface(tmp_path):
    output = tmp_path / "template"

    build_template.build_template(output)

    required = [
        ".github/scripts/resolve-reponomics-config.py",
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
        "config.yaml",
        "config.example.yaml",
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


def test_template_includes_initial_managed_docs_snapshot(tmp_path):
    output = tmp_path / "template"

    build_template.build_template(output)
    release = sync_action_release.load_manifest()

    docs_root = output / "docs" / "reponomics"
    readme = (docs_root / "README.md").read_text(encoding="utf-8")
    manifest = json.loads((docs_root / ".manifest.json").read_text(encoding="utf-8"))

    assert "{{ACTION_VERSION}}" not in readme
    assert f"Generated for Reponomics Dashboard Action {release.version}." in readme
    assert manifest["managed_namespace"] == "docs/reponomics"
    assert manifest["action_repository"] == release.repository
    assert manifest["action_version"] == release.version
    assert manifest["updated_at"] == release.published_at
    expected_files = {
        path.relative_to(docs_root).as_posix(): hashlib.sha256(
            path.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
        for path in docs_root.rglob("*")
        if path.is_file() and path.name != ".manifest.json"
    }
    assert "README.md" in expected_files
    assert manifest["files"] == expected_files


def test_template_community_docs_are_placeholders(tmp_path):
    output = tmp_path / "template"

    build_template.build_template(output)

    generated_docs = [
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
    ]
    for relative_path in generated_docs:
        text = (output / relative_path).read_text(encoding="utf-8")
        assert "This is a placeholder document." in text
        assert "not intended for public use" in text

    for relative_path in ("CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "SECURITY.md"):
        assert (output / relative_path).read_text(encoding="utf-8") != Path(
            relative_path
        ).read_text(encoding="utf-8")


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
    release = sync_action_release.load_manifest()

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
    collect_publish_workflow = yaml.safe_load(collect_publish)
    incident_reset_workflow = yaml.safe_load(incident_reset)
    doctor_workflow = yaml.safe_load(doctor)

    action_ref = f"uses: {release.repository}@{release.major_tag}"
    html_env = 'GENERATE_HTML_DASHBOARD: "false"'
    assert "skip_collect:" in collect_publish
    assert "docs-sync:" in collect_publish
    assert "resolve-reponomics-config.py --require-setup" in collect_publish
    assert "REPONOMICS_SETUP_COMPLETE == 'true'" in collect_publish
    assert "mode: docs-sync" in collect_publish
    assert "github-token: ${{ github.token }}" in collect_publish
    assert "allow-docs-sync" not in collect_publish
    assert action_ref in collect_publish
    assert action_ref in doctor
    assert action_ref in incident_reset
    assert 'REPONOMICS_ACTION_REF: "' not in collect_publish
    assert 'REPONOMICS_ACTION_SHA: "' not in collect_publish
    assert html_env in collect_publish
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
    assert action_ref not in setup
    assert action_ref in rotate
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
    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in doctor
    assert "run-id: ${{ inputs.artifact_run_id }}" in doctor
    assert "name: html-dashboard-encrypted" in doctor
    assert "name: html-dashboard-plain" in doctor
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
    assert 'USE_GITHUB_APP: "false"' in collect_publish
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
    assert "workflow_run:" not in collect_publish
    assert "COLLECTION_TOKEN" not in keepalive
    assert "DASHBOARD_SECRET_DO_NOT_REPLACE" not in keepalive
    assert "resolve-reponomics-config.py --require-setup" in keepalive
    assert "60 days without repository activity" in keepalive
    assert ".reponomics/setup-complete" in resolver
    assert '"generate_readme": "GENERATE_README"' in resolver


def test_setup_workflow_resolves_privacy_modes():
    setup = Path("template/.github/workflows/setup.yml").read_text(encoding="utf-8")

    for mode in ("strong", "casual", "plain"):
        assert re.search(rf"^\s+- {mode}$", setup, flags=re.MULTILINE)

    assert "generate_html_dashboard:" in setup
    assert 'description: "Publish hosted HTML dashboard after collection"' in setup
    assert "generate_readme:" in setup
    assert 'description: "Generate README after collection (private repositories only)"' in setup
    assert "use_github_app:" in setup
    assert 'description: "Advanced collection auth: use a user-owned GitHub App installation token"' in setup
    assert "publish_dashboard:" not in setup
    assert "commit_readme:" not in setup
    assert "commit_readme_snapshot:" not in setup
    assert "PUBLISH_TO_PAGES" not in setup
    assert "PUBLISH_README" not in setup
    assert "COMMIT_README_SNAPSHOT" not in setup
    assert 'echo "PRIVACY_MODE=$resolved_privacy_mode"' in setup
    assert 'echo "GENERATE_HTML_DASHBOARD=$GENERATE_HTML_DASHBOARD"' in setup
    assert 'echo "GENERATE_README=$GENERATE_README"' in setup
    assert '"generate_html_dashboard": os.environ["GENERATE_HTML_DASHBOARD"].lower()' in setup
    assert '"generate_readme": os.environ["GENERATE_README"].lower()' in setup
    assert 'echo "USE_GITHUB_APP=$USE_GITHUB_APP"' in setup
    assert "README dashboard generation is only supported for private repositories." in setup
    assert "cp README.md README.backup.md" in setup
    assert "cat > README.md <<'MD'" in setup
    assert setup.index("cp README.md README.backup.md") < setup.index(
        "cat > README.md <<'MD'"
    )
    assert "This repository was generated from the [Reponomics Dashboard template repo]" in setup
    assert "allow_docs_sync: false" in setup
    assert "Managed docs sync" in setup
    assert ": > .reponomics/setup-complete" in setup
    assert "git add README.md README.backup.md config.yaml .reponomics/setup-complete" in setup
    assert '"privacy_mode": os.environ["PRIVACY_MODE"]' in setup
    assert '"retention_days": os.environ["RETENTION_DAYS"]' in setup
    assert "privacy_mode=plain" in setup
    assert "is only supported for private repositories." in setup
    assert "privacy_mode=strong" in setup
    assert "privacy_mode=casual" in setup
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
    assert '"use_github_app": os.environ["USE_GITHUB_APP"].lower()' in setup
    assert "docs/reponomics/secure-dashboard-key.md" in setup
    assert "docs/reponomics/privacy-configuration-matrix.md" in setup
    assert "not strong enough for \\`privacy_mode=strong\\`" in setup
    assert "Casual privacy mode selected" not in setup
    casual_length_check = (
        '${#DASHBOARD_SECRET_DO_NOT_REPLACE}" -lt 40 ] && [ "$PRIVACY_MODE" = "casual"'
    )
    assert casual_length_check not in setup
    assert "Manual GitHub Pages step" in setup
    assert '[ "$GENERATE_HTML_DASHBOARD" = "true" ] && [ "$PRIVACY_MODE" != "plain" ]' in setup
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


def test_docs_explain_multi_owner_token_fallback():
    template_readme = Path("template/README.template.md").read_text(encoding="utf-8")
    managed_docs = Path("dashboard_action/runtime/managed_docs/repository-guide.md").read_text(
        encoding="utf-8"
    )

    assert "Token Scope And Repository Owners" in template_readme
    assert "Repository entries use full `owner/repo` names" in template_readme

    for text in (template_readme, managed_docs):
        assert "supports one collection credential" in text
        assert "Fine-grained personal access tokens are scoped to one GitHub resource owner" in text
        assert re.search(r"multiple users or\s+organizations", text)
        assert "classic PAT" in text
        assert re.search(r"`repo`\s+scope", text)


def test_config_documents_managed_docs_opt_out():
    config_example = Path("template/config.example.yaml").read_text(encoding="utf-8")
    config = Path("template/config.yaml").read_text(encoding="utf-8")

    for text in (config_example, config):
        assert "allow_docs_sync: true" in text
        assert "docs/reponomics/" in text


def test_action_release_manifest_and_metadata_contract():
    release = sync_action_release.load_manifest()

    assert release.repository == sync_action_release.ACTION_REPOSITORY
    assert re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", release.tag)
    assert re.fullmatch(r"[0-9a-f]{40}", release.target_commitish)
    sync_action_release.validate_action_metadata(ACTION_YML_FIXTURE)


def test_action_release_sync_does_not_manage_decision_records():
    adr_path = "docs/adr/008-template-and-generated-output-assurance.md"
    adr_text = Path(adr_path).read_text(encoding="utf-8")

    assert adr_path not in sync_action_release.MANAGED_TEXT_PATHS
    assert "reponomics/reponomics-dashboard-action@v" not in adr_text


def test_action_repo_has_template_publication_targets():
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "build-template:" in makefile
    assert "verify-template:" in makefile
    assert "template-smoke:" in makefile
    assert "template-consumer-e2e:" in makefile
    assert "publish-template:" in makefile
    assert "scripts/publish_generated_repo.py" in makefile


def test_template_consumer_e2e_defaults_to_local_action_repo():
    assert template_consumer_e2e.DEFAULT_ACTION_REPO == Path.cwd()



def test_action_release_requests_use_github_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_primary")
    monkeypatch.setenv("GH_TOKEN", "ghs_fallback")

    headers = sync_action_release._request_headers(accept="application/vnd.github+json")

    assert headers["Authorization"] == "Bearer ghs_primary"
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"


def test_action_release_requests_fall_back_to_gh_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GH_TOKEN", "ghs_fallback")

    headers = sync_action_release._request_headers()

    assert headers["Authorization"] == "Bearer ghs_fallback"


def test_action_release_http_errors_include_rate_limit_headers():
    headers = Message()
    headers["x-ratelimit-resource"] = "core"
    headers["x-ratelimit-limit"] = "60"
    headers["x-ratelimit-remaining"] = "0"
    headers["x-ratelimit-reset"] = "1781029999"
    headers["x-github-request-id"] = "ABC1:DEF2:12345"
    error = urllib.error.HTTPError(
        "https://api.github.com/repos/example/repo/git/trees/deadbeef?recursive=1",
        403,
        "rate limit exceeded",
        headers,
        io.BytesIO(b'{"message":"API rate limit exceeded"}'),
    )

    message = sync_action_release._format_http_error(error.url, error)

    assert "HTTP 403 rate limit exceeded" in message
    assert "resource=core" in message
    assert "remaining=0" in message
    assert "request_id=ABC1:DEF2:12345" in message
    assert "API rate limit exceeded" in message


def test_action_release_sync_rewrites_refs_and_status(tmp_path):
    release = sync_action_release.ActionRelease(
        repository=sync_action_release.ACTION_REPOSITORY,
        tag="v0.16.0",
        target_commitish="a" * 40,
        release_url="https://github.com/reponomics/reponomics-dashboard-action/releases/tag/v0.16.0",
        published_at="2026-05-31T05:19:33Z",
    )
    old_tag = "v0." + "15.0"
    readme = tmp_path / "README.md"
    readme.write_text(
        f"Status: current for action `{old_tag}`.\n"
        f"uses: reponomics/reponomics-dashboard-action@{old_tag}\n"
        f'  REPONOMICS_ACTION_REF: "{old_tag}"\n'
        f'  REPONOMICS_ACTION_SHA: "{"b" * 40}"\n',
        encoding="utf-8",
    )

    sync_action_release.sync_release(tmp_path, release, ACTION_YML_FIXTURE)

    assert old_tag not in readme.read_text(encoding="utf-8")
    assert "reponomics-dashboard-action@v0" in readme.read_text(encoding="utf-8")
    assert "reponomics-dashboard-action@v0.16.0" not in readme.read_text(encoding="utf-8")
    assert 'REPONOMICS_ACTION_REF: "v0.16.0"' in readme.read_text(encoding="utf-8")
    assert f'REPONOMICS_ACTION_SHA: "{release.target_commitish}"' in readme.read_text(
        encoding="utf-8"
    )
    assert sync_action_release.load_manifest(tmp_path).tag == "v0.16.0"


def test_action_release_sync_writes_managed_docs_snapshot(tmp_path):
    release = sync_action_release.ActionRelease(
        repository=sync_action_release.ACTION_REPOSITORY,
        tag="v0.16.0",
        target_commitish="a" * 40,
        release_url="https://github.com/reponomics/reponomics-dashboard-action/releases/tag/v0.16.0",
        published_at="2026-05-31T05:19:33Z",
    )
    bundle = {
        "README.md": "Generated for {{ACTION_VERSION}}.\n",
        "nested/topic.md": "Action {{ACTION_VERSION}}\n",
    }

    sync_action_release.sync_release(
        tmp_path,
        release,
        ACTION_YML_FIXTURE,
        managed_docs_bundle=bundle,
    )

    docs_root = tmp_path / "template" / "docs" / "reponomics"
    manifest = json.loads((docs_root / ".manifest.json").read_text(encoding="utf-8"))
    assert (docs_root / "README.md").read_text(encoding="utf-8") == (
        "Generated for 0.16.0.\n"
    )
    assert (docs_root / "nested" / "topic.md").read_text(encoding="utf-8") == (
        "Action 0.16.0\n"
    )
    assert manifest["managed_namespace"] == "docs/reponomics"
    assert manifest["action_version"] == "0.16.0"
    assert manifest["updated_at"] == release.published_at
    assert sorted(manifest["files"]) == ["README.md", "nested/topic.md"]

    sync_action_release.verify_release(
        tmp_path,
        release,
        ACTION_YML_FIXTURE,
        managed_docs_bundle=bundle,
    )
    (docs_root / "README.md").write_text("stale\n", encoding="utf-8")
    with pytest.raises(sync_action_release.ActionReleaseError, match="Managed docs snapshot"):
        sync_action_release.verify_release(
            tmp_path,
            release,
            ACTION_YML_FIXTURE,
            managed_docs_bundle=bundle,
        )


def test_action_release_verify_rejects_stale_refs(tmp_path):
    release = sync_action_release.ActionRelease(
        repository=sync_action_release.ACTION_REPOSITORY,
        tag="v0.16.0",
        target_commitish="a" * 40,
        release_url="https://github.com/reponomics/reponomics-dashboard-action/releases/tag/v0.16.0",
        published_at="2026-05-31T05:19:33Z",
    )
    sync_action_release.write_manifest(release, tmp_path)
    old_tag = "v0." + "15.0"
    (tmp_path / "README.md").write_text(
        f"uses: reponomics/reponomics-dashboard-action@{old_tag}\n"
        f'  REPONOMICS_ACTION_REF: "{old_tag}"\n'
        f'  REPONOMICS_ACTION_SHA: "{"b" * 40}"\n',
        encoding="utf-8",
    )

    with pytest.raises(sync_action_release.ActionReleaseError):
        sync_action_release.verify_release(tmp_path, release, ACTION_YML_FIXTURE)


def test_workflow_classification_contract():
    verify_workflow_classification.verify()


def test_template_consumer_e2e_absolutizes_cwd_relative_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    action_python = Path("action-runtime/venv/bin/python")

    assert template_consumer_e2e._absolute_path(action_python) == tmp_path / action_python


def test_template_consumer_e2e_accepts_chunked_encrypted_dashboard_marker(tmp_path):
    (tmp_path / ".e2e-github-output").write_text(
        "artifact-mode=encrypted\npublish-pages=true\n",
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
        privacy_mode="strong",
        repo_is_public=False,
        generate_readme=False,
        dashboard_secret="DASHBOARD_SECRET_DO_NOT_REPLACE_0123456789",
        expected_artifact_mode="encrypted",
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


def test_publish_remote_safety_accepts_expected_repo():
    publish_generated_repo._assert_expected_repo(
        "git@github.com:reponomics/reponomics-dashboard.git",
        "reponomics/reponomics-dashboard",
    )
    publish_generated_repo._assert_expected_repo(
        "https://github.com/reponomics/reponomics-dashboard-demo.git",
        "reponomics/reponomics-dashboard-demo",
    )


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
