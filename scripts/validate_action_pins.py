"""Validate that imported GitHub Actions are pinned to full commit SHAs.

This is a defense-in-depth CI check for the repository's workflow supply chain.
GitHub repository settings may also require SHA-pinned actions, but this script
keeps the policy visible in pull requests and in the public CI result. It scans
workflow and action YAML for third-party ``uses: owner/repo@ref`` imports and
rejects anything other than a full 40-character lowercase commit SHA. Local
actions and Docker image references are intentionally out of scope.

Policy details: docs/SECURITY_CHECKS.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def iter_yaml_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(
                child
                for child in path.rglob("*")
                if child.suffix in {".yml", ".yaml"} and child.is_file()
            )
        elif path.suffix in {".yml", ".yaml"}:
            files.append(path)
    return sorted(files)


def iter_uses(value: Any) -> list[str]:
    if isinstance(value, dict):
        found: list[str] = []
        for key, child in value.items():
            if key == "uses" and isinstance(child, str):
                found.append(child)
            else:
                found.extend(iter_uses(child))
        return found
    if isinstance(value, list):
        found = []
        for item in value:
            found.extend(iter_uses(item))
        return found
    return []


def validate_uses(uses: str) -> str | None:
    if uses.startswith(("./", "../", "docker://")):
        return None
    if "@" not in uses:
        return "missing @ref"
    ref = uses.rsplit("@", 1)[1]
    if not FULL_SHA.fullmatch(ref):
        return "ref is not a full 40-character lowercase commit SHA"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()

    failures: list[str] = []
    for path in iter_yaml_files(args.paths):
        data = yaml.safe_load(path.read_text()) or {}
        for uses in iter_uses(data):
            reason = validate_uses(uses)
            if reason:
                failures.append(f"{path}: {uses}: {reason}")

    if failures:
        print("GitHub Action imports must be pinned to full commit SHAs:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
