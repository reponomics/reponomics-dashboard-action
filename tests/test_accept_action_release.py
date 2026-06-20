from dataclasses import replace
from pathlib import Path

import yaml

from scripts import accept_action_release
from scripts import prepare_template_release
from scripts import template_contract
from scripts import template_release_notes


def _bump_version(version: str, release_type: str) -> str:
    return prepare_template_release.bump_version(version, release_type)


def _write_root(tmp_path: Path, *, template_version: str | None = None) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "action.yml").write_text(
        Path("action.yml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    payload = yaml.safe_load(Path("template-contract.yml").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    if template_version is not None:
        payload["template_version"] = template_version
    (tmp_path / "template-contract.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    return tmp_path


def _contract_payload(root: Path) -> dict:
    payload = yaml.safe_load((root / "template-contract.yml").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _accepted_action_version(root: Path) -> str:
    return str(_contract_payload(root)["accepted_action"]["version"])


def _contract_for_notes(
    *,
    template_version: str = "0.10.1",
    accepted_action_version: str = "0.23.6",
    accepted_action_sha: str = "b" * 40,
) -> template_contract.TemplateContract:
    contract = template_contract.load_contract()
    accepted_action = replace(
        contract.accepted_action,
        version=accepted_action_version,
        tag=f"v{accepted_action_version}",
        sha=accepted_action_sha,
    )
    return replace(
        contract,
        template_version=template_version,
        accepted_action=accepted_action,
    )


def test_accept_action_release_bumps_template_patch_and_records_action(tmp_path):
    root = _write_root(tmp_path)
    previous_template = _contract_payload(root)["template_version"]
    action_version = _bump_version(_accepted_action_version(root), "patch")
    expected_template = _bump_version(previous_template, "patch")

    payload, changed = accept_action_release.accept_action_release(
        root=root,
        action_version=action_version,
        action_sha="b" * 40,
    )

    assert changed is True
    assert payload["template_version"] == expected_template
    written = _contract_payload(root)
    assert written["template_version"] == expected_template
    assert written["accepted_action"] == {
        "repository": "reponomics/reponomics-dashboard-action",
        "version": action_version,
        "tag": f"v{action_version}",
        "sha": "b" * 40,
        "default_ref": "v0",
    }


def test_accept_action_release_bumps_template_minor_for_action_minor(tmp_path):
    root = _write_root(tmp_path)
    action_version = _bump_version(_accepted_action_version(root), "minor")
    expected_template = _bump_version(_contract_payload(root)["template_version"], "minor")

    payload, changed = accept_action_release.accept_action_release(
        root=root,
        action_version=action_version,
        action_sha="b" * 40,
    )

    assert changed is True
    assert payload["template_version"] == expected_template


def test_accept_action_release_bumps_template_major_for_action_major(tmp_path, monkeypatch):
    root = _write_root(tmp_path, template_version="0.11.0")
    monkeypatch.setattr(template_contract, "VERSION", "1.0.0")
    expected_template = _bump_version(_contract_payload(root)["template_version"], "major")

    payload, changed = accept_action_release.accept_action_release(
        root=root,
        action_version="1.0.0",
        action_sha="b" * 40,
    )

    assert changed is True
    assert payload["template_version"] == expected_template
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
    assert written["template_version"] == expected_template
    assert written["compatible_action_major"] == 1
    assert written["default_action_ref"] == "v1"


def test_accept_action_release_is_idempotent_when_action_already_accepted(tmp_path):
    root = _write_root(tmp_path)
    action_version = _bump_version(_accepted_action_version(root), "patch")
    expected_template = _bump_version(_contract_payload(root)["template_version"], "patch")
    accept_action_release.accept_action_release(
        root=root,
        action_version=action_version,
        action_sha="b" * 40,
    )

    payload, changed = accept_action_release.accept_action_release(
        root=root,
        action_version=action_version,
        action_sha="b" * 40,
    )

    assert changed is False
    assert payload["template_version"] == expected_template


def test_accept_action_release_writes_workflow_outputs_and_notes(tmp_path):
    root = _write_root(tmp_path)
    output = tmp_path / "github-output.txt"
    notes = tmp_path / "notes.md"
    action_version = _bump_version(_accepted_action_version(root), "patch")
    expected_template = _bump_version(_contract_payload(root)["template_version"], "patch")
    payload, changed = accept_action_release.accept_action_release(
        root=root,
        action_version=action_version,
        action_sha="b" * 40,
    )

    accept_action_release._write_outputs(output, payload, changed=changed)
    accept_action_release._write_release_notes(notes, payload)

    assert "changed=true" in output.read_text(encoding="utf-8")
    assert (
        f"template_tag=reponomics-dashboard-v{expected_template}"
        in output.read_text(encoding="utf-8")
    )
    assert (
        f"Updated `reponomics/reponomics-dashboard-action` to `v{action_version}` (`bbbbbbb`)."
        in notes.read_text(encoding="utf-8")
    )


def test_prepare_template_release_bumps_template_patch_only(tmp_path):
    root = _write_root(tmp_path)
    previous = _contract_payload(root)["template_version"]
    expected = _bump_version(previous, "patch")
    accepted_action_version = _accepted_action_version(root)

    payload, returned_previous, current = prepare_template_release.prepare_template_release(
        root=root,
        release_type="patch",
    )

    assert returned_previous == previous
    assert current == expected
    assert payload["template_version"] == expected
    assert payload["accepted_action"]["version"] == accepted_action_version
    assert _contract_payload(root)["template_version"] == expected


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
    contract = _contract_for_notes()

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
    contract = _contract_for_notes()
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
