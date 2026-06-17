from pathlib import Path

import yaml

from scripts import accept_action_release
from scripts import template_contract
from scripts import template_release_notes


def _write_root(tmp_path: Path, *, template_version: str = "0.10.0") -> Path:
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
    assert "Action tag: `v0.23.6`" in notes.read_text(encoding="utf-8")
    assert f"Action SHA: `{'b' * 40}`" in notes.read_text(encoding="utf-8")


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
    assert "# reponomics-dashboard v0.10.1" in notes_text
    assert f"Action SHA: `{'b' * 40}`" in notes_text
