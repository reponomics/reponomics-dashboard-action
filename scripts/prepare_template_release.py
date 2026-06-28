"""Prepare a template-only release contract bump."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import TextIO

import yaml

try:
    from scripts.repo_paths import find_repo_root
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_paths import find_repo_root  # type: ignore[import-not-found,no-redef]


ROOT = find_repo_root(Path(__file__))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import template_contract  # noqa: E402
from scripts import template_release_notes  # noqa: E402


class PrepareTemplateReleaseError(RuntimeError):
    """Raised when a template-only release cannot be prepared."""


def _version_tuple(version: str) -> tuple[int, int, int]:
    try:
        return template_contract._version_tuple(version)  # noqa: SLF001
    except template_contract.TemplateContractError as exc:
        raise PrepareTemplateReleaseError(str(exc)) from exc


def bump_version(version: str, release_type: str) -> str:
    major, minor, patch = _version_tuple(version)
    if release_type == "major":
        return f"{major + 1}.0.0"
    if release_type == "minor":
        return f"{major}.{minor + 1}.0"
    if release_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise PrepareTemplateReleaseError(f"unsupported template release type: {release_type}")


def _load_contract_payload(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise PrepareTemplateReleaseError(f"{path} must parse as a YAML object")
    return payload


def prepare_template_release(
    *,
    root: Path,
    release_type: str,
) -> tuple[dict, str, str]:
    contract_path = root / "template-contract.yml"
    original_text = contract_path.read_text(encoding="utf-8")
    payload = _load_contract_payload(contract_path)
    contract = template_contract.load_contract(root)
    previous_version = contract.template_version
    next_version = bump_version(previous_version, release_type)
    payload["template_version"] = next_version
    if not payload.get("protected_template_refs"):
        payload["minimum_compatible_template_version"] = next_version
    contract_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    try:
        template_contract.validate_local_contract(root)
    except Exception:
        contract_path.write_text(original_text, encoding="utf-8")
        raise
    return payload, previous_version, next_version


def _format_pr_entry(item: object) -> str:
    if not isinstance(item, dict):
        raise PrepareTemplateReleaseError("release notes source entries must be objects")
    number = item.get("number")
    title = item.get("title")
    url = item.get("url")
    body = item.get("body")
    if not isinstance(number, int):
        raise PrepareTemplateReleaseError("release notes source entry number must be an integer")
    if not isinstance(title, str) or not title.strip():
        raise PrepareTemplateReleaseError("release notes source entry title is required")
    if not isinstance(url, str) or not url.strip():
        raise PrepareTemplateReleaseError("release notes source entry URL is required")

    notes = template_release_notes.extract_notes_from_pr_body(body if isinstance(body, str) else "")
    if notes:
        return notes
    return f"- {title.strip()} ([#{number}]({url.strip()}))"


def _release_notes(
    *,
    release_notes_source: Path | None,
    next_version: str,
    release_type: str,
) -> str:
    if release_notes_source:
        try:
            payload = json.loads(release_notes_source.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise PrepareTemplateReleaseError(
                f"release notes source does not exist: {release_notes_source}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise PrepareTemplateReleaseError("release notes source must be valid JSON") from exc
        if not isinstance(payload, list):
            raise PrepareTemplateReleaseError("release notes source must be a JSON array")
        entries = [_format_pr_entry(item) for item in payload]
        if entries:
            return "\n".join(entries)
    return (
        f"Prepared a {release_type} template-only release for "
        + f"`reponomics-dashboard v{next_version}`."
    )


def _write_multiline_output(handle: TextIO, key: str, value: str) -> None:
    delimiter = f"__{key.upper()}__"
    while delimiter in value:
        delimiter += "_"
    handle.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")


def _write_outputs(
    path: Path,
    *,
    previous_version: str,
    next_version: str,
    release_type: str,
    release_notes_source: Path | None = None,
) -> None:
    template_tag = f"reponomics-dashboard-v{next_version}"
    branch = f"automation/template-release-{template_tag}"
    title = f"chore: prepare template release {template_tag}"
    body = (
        f"Template-only {release_type} release from `{previous_version}` to "
        + f"`{next_version}`.\n\n"
        + "Merging this PR is the template release approval step. After it lands on "
        + "main, the Template Release workflow will run the release gates, publish "
        + "the generated template repository, and create "
        + f"{template_tag} in reponomics/reponomics-dashboard.\n\n"
        + "## Template release notes\n\n"
        + _release_notes(
            release_notes_source=release_notes_source,
            next_version=next_version,
            release_type=release_type,
        )
        + "\n"
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"previous_version={previous_version}\n")
        handle.write(f"template_version={next_version}\n")
        handle.write(f"template_tag={template_tag}\n")
        handle.write(f"branch={branch}\n")
        handle.write(f"title={title}\n")
        handle.write(f"release_type={release_type}\n")
        _write_multiline_output(handle, "body", body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--release-type", choices=["patch", "minor", "major"], required=True)
    parser.add_argument("--release-notes-source", type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    _payload, previous_version, next_version = prepare_template_release(
        root=args.root,
        release_type=args.release_type,
    )
    if args.github_output:
        _write_outputs(
            args.github_output,
            previous_version=previous_version,
            next_version=next_version,
            release_type=args.release_type,
            release_notes_source=args.release_notes_source,
        )
    print(
        "Prepared template release "
        + f"{previous_version} -> {next_version} ({args.release_type})"
    )


if __name__ == "__main__":
    try:
        main()
    except PrepareTemplateReleaseError as exc:
        print(f"Template release preparation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
