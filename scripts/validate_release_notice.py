#!/usr/bin/env python3
"""Validate Reponomics release-note update notice blocks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "traffic_report_action" / "runtime" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import release_notice  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate constrained <!-- reponomics-update {...} --> blocks.",
    )
    parser.add_argument(
        "release_notes",
        nargs="+",
        type=Path,
        help="Markdown release-note file(s) to validate.",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Allow files without a reponomics-update block.",
    )
    args = parser.parse_args()

    failed = False
    for path in args.release_notes:
        body = path.read_text(encoding="utf-8")
        errors = release_notice.validate_update_block(
            body,
            require_block=not args.allow_missing,
        )
        if errors:
            failed = True
            print(f"{path}: invalid reponomics-update block", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
        else:
            print(f"{path}: ok")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
