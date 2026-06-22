"""Smoke-check dashboard JavaScript syntax and flattened secure runtime output."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_JS_DIR = (
    ROOT
    / "dashboard_action"
    / "runtime"
    / "scripts"
    / "render_dashboard_support"
    / "assets"
    / "static"
    / "dashboard"
)
RUNTIME_SCRIPTS = ROOT / "dashboard_action" / "runtime" / "scripts"
SMOKE_DIR = ROOT / ".tmp" / "js-smoke"


def _run_node_check(path: Path) -> None:
    node = os.environ.get("NODE", "node")
    subprocess.run([node, "--check", str(path)], check=True)


def _assert_flattened_runtime_contract(source: str) -> None:
    leftovers = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("export ")
    ]
    if leftovers:
        raise AssertionError(
            "flattened secure runtime still contains module syntax: " + leftovers[0]
        )
    if "await readJsonAsset" in source:
        raise AssertionError(
            "flattened secure runtime still contains published JSON asset loading"
        )


def main() -> int:
    for path in sorted(DASHBOARD_JS_DIR.glob("*.js")):
        _run_node_check(path)

    sys.path.insert(0, str(RUNTIME_SCRIPTS))
    from render_dashboard_support import html  # noqa: PLC0415

    source = html.SECURE_RUNTIME_JS
    _assert_flattened_runtime_contract(source)

    SMOKE_DIR.mkdir(parents=True, exist_ok=True)
    flattened_runtime = SMOKE_DIR / "secure-runtime.js"
    flattened_runtime.write_text(source, encoding="utf-8")
    _run_node_check(flattened_runtime)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
