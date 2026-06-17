from pathlib import Path

import pytest

from scripts import template_contract
from scripts import validate_template_action_ref


def _contract(
    *,
    compatible_action_major: int = 0,
    minimum_compatible_template_version: str = "0.9.1",
) -> template_contract.TemplateContract:
    return template_contract.TemplateContract(
        template_version="0.9.1",
        action_repository=template_contract.ACTION_REPOSITORY,
        default_action_ref=f"v{compatible_action_major}",
        compatible_action_major=compatible_action_major,
        accepted_action=template_contract.AcceptedActionRelease(
            repository=template_contract.ACTION_REPOSITORY,
            version="0.22.1",
            tag="v0.22.1",
            sha="b" * 40,
            default_ref=f"v{compatible_action_major}",
        ),
        minimum_compatible_template_version=minimum_compatible_template_version,
        protected_template_refs=(
            template_contract.ProtectedTemplateRef(
                ref=f"reponomics-dashboard-v{minimum_compatible_template_version}",
                template_version=minimum_compatible_template_version,
                source_commit="a" * 40,
            ),
        ),
        managed_docs_namespace=Path("docs/reponomics"),
    )


def _resolved(ref: str = "v0") -> validate_template_action_ref.ResolvedActionRef:
    return validate_template_action_ref.ResolvedActionRef(
        ref=ref,
        sha="a" * 40,
        remote_ref=f"refs/tags/{ref}",
    )


def test_validate_public_action_ref_accepts_matching_version(tmp_path):
    root = _write_contract(tmp_path, _contract())

    resolved = validate_template_action_ref.validate_public_action_ref(
        root=root,
        resolver=lambda contract: _resolved(contract.default_action_ref),
        version_reader=lambda _contract, _resolved_ref: "0.22.1",
    )

    assert resolved.ref == "v0"


def test_validate_public_action_ref_rejects_missing_ref(tmp_path):
    root = _write_contract(tmp_path, _contract())

    def resolver(
        contract: template_contract.TemplateContract,
    ) -> validate_template_action_ref.ResolvedActionRef:
        raise validate_template_action_ref.TemplateActionRefError(
            f"Public default action ref {contract.default_action_ref} was not found"
        )

    with pytest.raises(validate_template_action_ref.TemplateActionRefError, match="not found"):
        validate_template_action_ref.validate_public_action_ref(
            root=root,
            resolver=resolver,
            version_reader=lambda _contract, _resolved_ref: "0.22.1",
        )


def test_validate_public_action_ref_rejects_unparsable_version(tmp_path):
    root = _write_contract(tmp_path, _contract())

    with pytest.raises(validate_template_action_ref.TemplateActionRefError, match="unparsable"):
        validate_template_action_ref.validate_public_action_ref(
            root=root,
            resolver=lambda contract: _resolved(contract.default_action_ref),
            version_reader=lambda _contract, _resolved_ref: "next",
        )


def test_validate_public_action_ref_rejects_wrong_major(tmp_path):
    root = _write_contract(tmp_path, _contract(compatible_action_major=0))

    with pytest.raises(validate_template_action_ref.TemplateActionRefError, match="not compatible"):
        validate_template_action_ref.validate_public_action_ref(
            root=root,
            resolver=lambda contract: _resolved(contract.default_action_ref),
            version_reader=lambda _contract, _resolved_ref: "1.0.0",
        )


def test_parse_remote_action_version_requires_matching_metadata():
    with pytest.raises(validate_template_action_ref.TemplateActionRefError, match="mismatched"):
        _check_remote_metadata_versions("0.22.1", "0.22.2")


def test_parse_ls_remote_prefers_peeled_tag():
    output = "\n".join(
        [
            f"{'b' * 40}\trefs/tags/v0",
            f"{'a' * 40}\trefs/tags/v0^{{}}",
        ]
    )

    assert validate_template_action_ref._parse_ls_remote(output) == {
        "refs/tags/v0": "b" * 40,
        "refs/tags/v0^{}": "a" * 40,
    }


def _write_contract(
    root: Path,
    contract: template_contract.TemplateContract,
) -> Path:
    (root / "template-contract.yml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                f"template_version: {contract.template_version}",
                f"action_repository: {contract.action_repository}",
                f"default_action_ref: {contract.default_action_ref}",
                f"compatible_action_major: {contract.compatible_action_major}",
                "accepted_action:",
                f"  repository: {contract.accepted_action.repository}",
                f"  version: {contract.accepted_action.version}",
                f"  tag: {contract.accepted_action.tag}",
                f"  sha: {contract.accepted_action.sha}",
                f"  default_ref: {contract.accepted_action.default_ref}",
                (
                    "minimum_compatible_template_version: "
                    + f"{contract.minimum_compatible_template_version}"
                ),
                "protected_template_refs:",
                f"  - ref: reponomics-dashboard-v{contract.minimum_compatible_template_version}",
                (
                    "    template_version: "
                    + f"{contract.minimum_compatible_template_version}"
                ),
                "    source_commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "    status: required",
                f"managed_docs_namespace: {contract.managed_docs_namespace.as_posix()}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return root


def _check_remote_metadata_versions(pyproject_version: str, core_version: str) -> str:
    pyproject = f'[project]\nname = "demo"\nversion = "{pyproject_version}"\n'
    core = f'VERSION = "{core_version}"\n'
    parsed_pyproject = validate_template_action_ref._parse_pyproject_version(pyproject)
    parsed_core = validate_template_action_ref._parse_core_version(core)
    if parsed_pyproject != parsed_core:
        raise validate_template_action_ref.TemplateActionRefError(
            f"mismatched versions: pyproject.toml={parsed_pyproject}, core.py={parsed_core}"
        )
    return parsed_pyproject
