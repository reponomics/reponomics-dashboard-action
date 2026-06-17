"""Write generated-template release metadata and notes from the template contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

try:
    from scripts.repo_paths import find_repo_root
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_paths import find_repo_root  # type: ignore[import-not-found,no-redef]


ROOT = find_repo_root(Path(__file__))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import template_contract  # noqa: E402


NOTES_MARKER_RE = re.compile(
    r"(?is)<!--\s*template-release-notes:start\s*-->\s*(?P<body>.*?)\s*"
    + r"<!--\s*template-release-notes:end\s*-->"
)
NOTES_HEADING_RE = re.compile(
    r"(?ims)^#{2,6}\s*Template release notes\s*$\s*(?P<body>.*?)(?=^#{1,6}\s+\S|\Z)"
)


def extract_notes_from_pr_body(body: str) -> str:
    marker_match = NOTES_MARKER_RE.search(body)
    if marker_match:
        return marker_match.group("body").strip()

    heading_match = NOTES_HEADING_RE.search(body)
    if heading_match:
        return heading_match.group("body").strip()

    return ""


def write_outputs(path: Path, contract: template_contract.TemplateContract) -> None:
    lines = [
        f"template_version={contract.template_version}",
        f"template_tag=reponomics-dashboard-v{contract.template_version}",
        f"accepted_action_version={contract.accepted_action.version}",
        f"accepted_action_tag={contract.accepted_action.tag}",
        f"accepted_action_sha={contract.accepted_action.sha}",
    ]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _fallback_notes(contract: template_contract.TemplateContract) -> str:
    accepted_action = contract.accepted_action
    return (
        "Updated "
        + f"`{accepted_action.repository}` to `{accepted_action.tag}` "
        + f"(`{accepted_action.sha[:7]}`)."
    )


def write_notes(
    path: Path,
    contract: template_contract.TemplateContract,
    *,
    pr_body: str = "",
) -> None:
    notes = extract_notes_from_pr_body(pr_body) if pr_body else ""
    if not notes:
        notes = _fallback_notes(contract)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(notes.strip() + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--release-notes", type=Path)
    parser.add_argument("--pr-body", type=Path)
    args = parser.parse_args()

    contract = template_contract.validate_local_contract(args.root)
    pr_body = args.pr_body.read_text(encoding="utf-8") if args.pr_body else ""
    if args.github_output:
        write_outputs(args.github_output, contract)
    if args.release_notes:
        write_notes(args.release_notes, contract, pr_body=pr_body)
    print(f"Prepared release metadata for reponomics-dashboard v{contract.template_version}")


if __name__ == "__main__":
    main()
