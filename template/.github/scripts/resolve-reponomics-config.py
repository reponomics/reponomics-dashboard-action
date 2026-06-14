#!/usr/bin/env python3
"""Resolve workflow-facing Reponomics config without third-party dependencies."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


DEFAULTS = {
    "DATA_MODE": "encrypted",
    "RETENTION_DAYS": "90",
    "GENERATE_HTML_DASHBOARD": "false",
    "GENERATE_README": "false",
    "USE_GITHUB_APP": "false",
}

CONFIG_KEYS = {
    "data_mode": "DATA_MODE",
    "retention_days": "RETENTION_DAYS",
    "generate_html_dashboard": "GENERATE_HTML_DASHBOARD",
    "generate_readme": "GENERATE_README",
    "use_github_app": "USE_GITHUB_APP",
}

VALID_DATA_MODES = {"encrypted", "plaintext"}


def _summary(*lines: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as summary:
        for line in lines:
            summary.write(f"{line}\n")
        summary.write("\n")


def _parse_scalar(raw: str) -> str:
    value = raw.strip()
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value


def _load_top_level_scalars(config_path: Path) -> dict[str, str]:
    if not config_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in config_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith((" ", "\t", "#")):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$", line)
        if not match:
            continue
        key, raw = match.groups()
        if key in CONFIG_KEYS and raw:
            values[key] = _parse_scalar(raw)
    return values


def _bool(value: str, *, name: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return "true"
    if normalized in {"0", "false", "no", "off"}:
        return "false"
    raise ValueError(f"{name} must be true or false, got {value!r}.")


def _resolve(config_path: Path) -> dict[str, str]:
    resolved = dict(DEFAULTS)
    scalars = _load_top_level_scalars(config_path)

    if "data_mode" in scalars:
        data_mode = scalars["data_mode"].strip().lower()
        if data_mode not in VALID_DATA_MODES:
            allowed = ", ".join(sorted(VALID_DATA_MODES))
            raise ValueError(f"data_mode must be one of: {allowed}.")
        resolved["DATA_MODE"] = data_mode

    if "retention_days" in scalars:
        try:
            retention_days = int(scalars["retention_days"])
        except ValueError as exc:
            raise ValueError("retention_days must be an integer.") from exc
        if retention_days < 1 or retention_days > 90:
            raise ValueError("retention_days must be between 1 and 90.")
        resolved["RETENTION_DAYS"] = str(retention_days)

    for key in ("generate_html_dashboard", "generate_readme", "use_github_app"):
        if key in scalars:
            resolved[CONFIG_KEYS[key]] = _bool(scalars[key], name=key)

    return resolved


def _write_env(values: dict[str, str]) -> None:
    env_path = os.environ.get("GITHUB_ENV", "").strip()
    if not env_path:
        for key, value in values.items():
            print(f"{key}={value}")
        return
    with Path(env_path).open("a", encoding="utf-8") as env_file:
        for key, value in values.items():
            env_file.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--require-setup", action="store_true")
    args = parser.parse_args()

    setup_complete = Path(".reponomics/setup-complete").exists()
    _write_env({"REPONOMICS_SETUP_COMPLETE": str(setup_complete).lower()})
    if args.require_setup and not setup_complete:
        _summary(
            "## Reponomics setup required",
            "",
            "Run **Actions -> Set up Reponomics dashboard** before this workflow does work.",
        )
        return 0

    try:
        _write_env(_resolve(Path(args.config)))
    except ValueError as exc:
        _summary("## Reponomics configuration error", "", str(exc))
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
