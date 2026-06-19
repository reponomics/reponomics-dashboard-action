from pathlib import Path

import yaml

from scripts import accept_action_release
from scripts import prepare_template_release
from scripts import template_contract
from scripts import template_release_notes


def _write_root(tmp_path: Path, *, template_version: str = "0.10.0") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "action.yml").write_text(
        Path("action.yml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "template-contract.yml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                f"template_version: {template_version}",
                "action_repository: reponomics/reponomics-dashboard-action",
                "default_action_ref: v0",
                "compatible_action_major: 0",
                "accepted_action:",
                "  repository: reponomics/reponomics-dashboard-action",
                "  version: 0.23.5",
                "  tag: v0.23.5",
                "  sha: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "  default_ref: v0",
                "minimum_compatible_template_version: 0.10.0",
                "protected_template_refs:",
                "  - ref: reponomics-dashboard-v0.10.0",
                "    template_version: 0.10.0",
                "    source_commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "    status: required",
                "managed_docs_namespace: docs/reponomics",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return tmp_path


def _contract_payload(root: Path) -> dict:
    payload = yaml.safe_load((root / "template-contract.yml").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_accept_action_release_bumps_template_patch_and_records_action(tmp_path):
    root = _write_root(tmp_path)

    payload, changed = accept_action_release.accept_action_release(
        root=root,
        action_version="0.23.6",
        action_sha="b" * 40,
    )

    assert changed is True
    assert payload["template_version"] == "0.10.1"
    written = _contract_payload(root)
    assert written["template_version"] == "0.10.1"
    assert written["accepted_action"] == {
        "repository": "reponomics/reponomics-dashboard-action",
        "version": "0.23.6",
        "tag": "v0.23.6",
        "sha": "b" * 40,
        "default_ref": "v0",
    }


def test_accept_action_release_bumps_template_minor_for_action_minor(tmp_path):
    root = _write_root(tmp_path)

    payload, changed = accept_action_release.accept_action_release(
        root=root,
        action_version="0.24.0",
        action_sha="b" * 40,
    )

    assert changed is True
    assert payload["template_version"] == "0.11.0"


def test_accept_action_release_bumps_template_major_for_action_major(tmp_path, monkeypatch):
    root = _write_root(tmp_path, template_version="0.11.0")
    monkeypatch.setattr(template_contract, "VERSION", "1.0.0")

    payload, changed = accept_action_release.accept_action_release(
        root=root,
        action_version="1.0.0",
        action_sha="b" * 40,
    )

    assert changed is True
    assert payload["template_version"] == "1.0.0"
    assert payload["compatible_action_major"] == 1
    assert payload["default_action_ref"] == "v1"
    assert payload["accepted_action"] == {
        "repository": "reponomics/reponomics-dashboard-action",
        "version": "1.0.0",
        "tag": "v1.0.0",
        "sha": "b" * 40,
        "default_ref": "v1",
    }
    written = _contract_payload(root)
    assert written["template_version"] == "1.0.0"
    assert written["compatible_action_major"] == 1
    assert written["default_action_ref"] == "v1"


def test_accept_action_release_is_idempotent_when_action_already_accepted(tmp_path):
    root = _write_root(tmp_path)
    accept_action_release.accept_action_release(
        root=root,
        action_version="0.23.6",
        action_sha="b" * 40,
    )

    payload, changed = accept_action_release.accept_action_release(
        root=root,
        action_version="0.23.6",
        action_sha="b" * 40,
    )

    assert changed is False
    assert payload["template_version"] == "0.10.1"


def test_accept_action_release_writes_workflow_outputs_and_notes(tmp_path):
    root = _write_root(tmp_path)
    output = tmp_path / "github-output.txt"
    notes = tmp_path / "notes.md"
    payload, changed = accept_action_release.accept_action_release(
        root=root,
        action_version="0.23.6",
        action_sha="b" * 40,
    )

    accept_action_release._write_outputs(output, payload, changed=changed)
    accept_action_release._write_release_notes(notes, payload)

    assert "changed=true" in output.read_text(encoding="utf-8")
    assert "template_tag=reponomics-dashboard-v0.10.1" in output.read_text(encoding="utf-8")
    assert (
        "Updated `reponomics/reponomics-dashboard-action` to `v0.23.6` (`bbbbbbb`)."
        in notes.read_text(encoding="utf-8")
    )


def test_prepare_template_release_bumps_template_patch_only(tmp_path):
    root = _write_root(tmp_path)

    payload, previous, current = prepare_template_release.prepare_template_release(
        root=root,
        release_type="patch",
    )

    assert previous == "0.10.0"
    assert current == "0.10.1"
    assert payload["template_version"] == "0.10.1"
    assert payload["accepted_action"]["version"] == "0.23.5"
    assert _contract_payload(root)["template_version"] == "0.10.1"


def test_prepare_template_release_bumps_minor_and_major(tmp_path):
    minor_root = _write_root(tmp_path / "minor", template_version="0.10.9")
    major_root = _write_root(tmp_path / "major", template_version="0.10.9")

    _minor_payload, _minor_previous, minor_current = (
        prepare_template_release.prepare_template_release(
            root=minor_root,
            release_type="minor",
        )
    )
    _major_payload, _major_previous, major_current = (
        prepare_template_release.prepare_template_release(
            root=major_root,
            release_type="major",
        )
    )

    assert minor_current == "0.11.0"
    assert major_current == "1.0.0"


def test_prepare_template_release_writes_pr_outputs(tmp_path):
    output = tmp_path / "github-output.txt"

    prepare_template_release._write_outputs(
        output,
        previous_version="0.10.0",
        next_version="0.10.1",
        release_type="patch",
        release_notes_source=None,
    )

    output_text = output.read_text(encoding="utf-8")
    assert "previous_version=0.10.0" in output_text
    assert "template_version=0.10.1" in output_text
    assert "template_tag=reponomics-dashboard-v0.10.1" in output_text
    assert "branch=automation/template-release-reponomics-dashboard-v0.10.1" in output_text
    assert "title=chore: prepare template release reponomics-dashboard-v0.10.1" in output_text
    assert "body<<" in output_text
    assert "## Template release notes" in output_text
    assert "Prepared a patch template-only release" in output_text


def test_prepare_template_release_uses_merged_pr_notes_source(tmp_path):
    output = tmp_path / "github-output.txt"
    source = tmp_path / "prs.json"
    source.write_text(
        """
[
  {
    "number": 145,
    "title": "docs: tweak default template docs",
    "url": "https://github.com/reponomics/reponomics-dashboard-action/pull/145",
    "body": "## Template release notes\\n\\nClarified setup docs for new template copies."
  },
  {
    "number": 146,
    "title": "docs: tune template security copy",
    "url": "https://github.com/reponomics/reponomics-dashboard-action/pull/146",
    "body": ""
  }
]
""",
        encoding="utf-8",
    )

    prepare_template_release._write_outputs(
        output,
        previous_version="0.10.0",
        next_version="0.10.1",
        release_type="patch",
        release_notes_source=source,
    )

    output_text = output.read_text(encoding="utf-8")
    assert "Clarified setup docs for new template copies." in output_text
    assert (
        "- docs: tune template security copy "
        + "([#146](https://github.com/reponomics/reponomics-dashboard-action/pull/146))"
        in output_text
    )


def test_template_release_notes_writes_contract_metadata(tmp_path):
    output = tmp_path / "github-output.txt"
    notes = tmp_path / "notes.md"
    contract = template_contract.TemplateContract(
        template_version="0.10.1",
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

    template_release_notes.write_outputs(output, contract)
    template_release_notes.write_notes(notes, contract)

    output_text = output.read_text(encoding="utf-8")
    notes_text = notes.read_text(encoding="utf-8")
    assert "template_tag=reponomics-dashboard-v0.10.1" in output_text
    assert "accepted_action_tag=v0.23.6" in output_text
    assert (
        "Updated `reponomics/reponomics-dashboard-action` to `v0.23.6` (`bbbbbbb`)."
        in notes_text
    )


def test_template_release_notes_can_use_pr_body_section(tmp_path):
    notes = tmp_path / "notes.md"
    contract = template_contract.TemplateContract(
        template_version="0.10.1",
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
    body = "\n".join(
        [
            "Template PR overview.",
            "",
            "## Template release notes",
            "",
            "- Refresh generated setup defaults.",
            "- Clarify first-run configuration docs.",
            "",
            "## Validation",
            "",
            "- `make template-release-gates`",
        ]
    )

    template_release_notes.write_notes(notes, contract, pr_body=body)

    expected_notes = (
        "- Refresh generated setup defaults.\n"
        + "- Clarify first-run configuration docs.\n"
    )
    assert notes.read_text(encoding="utf-8") == expected_notes
