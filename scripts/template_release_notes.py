"""Write generated-template release metadata and notes from the template contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

try:
    from scripts.repo_paths import find_repo_root
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_paths import find_repo_root  # type: ignore[import-not-found,no-redef]


ROOT = find_repo_root(Path(__file__))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import template_contract  # noqa: E402


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


def write_notes(path: Path, contract: template_contract.TemplateContract) -> None:
    accepted_action = contract.accepted_action
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"# reponomics-dashboard v{contract.template_version}",
                "",
                "Generated template release.",
                "",
                "Accepted action metadata:",
                "",
                f"- Action repository: `{accepted_action.repository}`",
                f"- Action version: `{accepted_action.version}`",
                f"- Action tag: `{accepted_action.tag}`",
                f"- Action SHA: `{accepted_action.sha}`",
                f"- Default compatible ref: `{accepted_action.default_ref}`",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--release-notes", type=Path)
    args = parser.parse_args()

    contract = template_contract.validate_local_contract(args.root)
    if args.github_output:
        write_outputs(args.github_output, contract)
    if args.release_notes:
        write_notes(args.release_notes, contract)
    print(f"Prepared release metadata for reponomics-dashboard v{contract.template_version}")


if __name__ == "__main__":
    main()
