#!/usr/bin/env python3
"""Resolve workflow-facing Reponomics config without third-party dependencies."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


CONFIG_KEYS = {
    "i_have_read_the_readme": "I_HAVE_READ_THE_README",
    "data_mode": "DATA_MODE",
    "publish_pages_dashboard": "PUBLISH_PAGES_DASHBOARD",
    "publish_readme_dashboard": "PUBLISH_README_DASHBOARD",
    "allow_docs_sync": "ALLOW_DOCS_SYNC",
    "artifact_retention_days": "RETENTION_DAYS",
    "use_github_app": "USE_GITHUB_APP",
}

REQUIRED_KEYS = tuple(CONFIG_KEYS)
VALID_DATA_MODES = {"encrypted", "plaintext"}
ENV_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
TOP_LEVEL_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$")


def _summary(*lines: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as summary:
        for line in lines:
            summary.write(f"{line}\n")
        summary.write("\n")


def _parse_scalar(raw: str, *, key: str, line_number: int) -> str:
    value = raw.strip()
    if value.startswith("#"):
        return ""
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    if value[:1] in {'"', "'"}:
        if len(value) < 2 or value[-1] != value[0]:
            raise ValueError(
                f"config.yaml line {line_number}: {key} has an unterminated quoted value."
            )
        value = value[1:-1]
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(
            f"config.yaml line {line_number}: {key} contains unsupported control characters."
        )
    return value


def _load_top_level_scalars(config_path: Path) -> dict[str, str]:
    if not config_path.exists():
        raise ValueError(f"{config_path} is required.")
    values: dict[str, str] = {}
    for line_number, line in enumerate(
        config_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line or line.startswith((" ", "\t", "#")):
            continue
        match = TOP_LEVEL_KEY_RE.match(line)
        if not match:
            raise ValueError(
                f"config.yaml line {line_number} is not valid top-level key syntax."
            )
        key, raw = match.groups()
        if key in CONFIG_KEYS:
            if key in values:
                raise ValueError(f"config.yaml defines {key} more than once.")
            values[key] = _parse_scalar(raw, key=key, line_number=line_number)
    return values


def _bool(value: str, *, name: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return "true"
    if normalized in {"0", "false", "no", "off"}:
        return "false"
    raise ValueError(f"{name} must be true or false, got {value!r}.")


def _repo_is_private() -> bool:
    for name in ("REPOSITORY_PRIVATE", "GITHUB_EVENT_REPOSITORY_PRIVATE"):
        value = os.environ.get(name, "").strip().lower()
        if value:
            if value == "true":
                return True
            if value == "false":
                return False
            raise ValueError(f"{name} must be true or false, got {value!r}.")

    event_path = os.environ.get("GITHUB_EVENT_PATH", "").strip()
    if event_path:
        try:
            payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("Could not determine repository visibility.") from exc
        private = payload.get("repository", {}).get("private")
        if isinstance(private, bool):
            return private

    raise ValueError("Could not determine repository visibility.")


def _required_scalar(scalars: dict[str, str], key: str) -> str:
    value = scalars.get(key, "").strip()
    if not value:
        raise ValueError(
            f"{key} must be set in config.yaml before setup can proceed."
        )
    return value


def _resolve(config_path: Path) -> dict[str, str]:
    scalars = _load_top_level_scalars(config_path)
    missing = [key for key in REQUIRED_KEYS if not scalars.get(key, "").strip()]
    if missing:
        formatted = ", ".join(missing)
        raise ValueError(
            "Complete the required setup fields in config.yaml before running setup: "
            + formatted
            + "."
        )

    read_readme = _bool(
        _required_scalar(scalars, "i_have_read_the_readme"),
        name="i_have_read_the_readme",
    )
    if read_readme != "true":
        raise ValueError(
            "i_have_read_the_readme must be true before setup can proceed."
        )

    data_mode = _required_scalar(scalars, "data_mode").lower()
    if data_mode not in VALID_DATA_MODES:
        allowed = ", ".join(sorted(VALID_DATA_MODES))
        raise ValueError(f"data_mode must be one of: {allowed}.")

    try:
        retention_days = int(_required_scalar(scalars, "artifact_retention_days"))
    except ValueError as exc:
        raise ValueError("artifact_retention_days must be an integer.") from exc
    if retention_days < 1 or retention_days > 90:
        raise ValueError("artifact_retention_days must be between 1 and 90.")

    publish_pages = _bool(
        _required_scalar(scalars, "publish_pages_dashboard"),
        name="publish_pages_dashboard",
    )
    publish_readme = _bool(
        _required_scalar(scalars, "publish_readme_dashboard"),
        name="publish_readme_dashboard",
    )
    allow_docs_sync = _bool(
        _required_scalar(scalars, "allow_docs_sync"),
        name="allow_docs_sync",
    )
    use_github_app = _bool(
        _required_scalar(scalars, "use_github_app"),
        name="use_github_app",
    )

    repo_private = _repo_is_private()
    if data_mode == "plaintext" and not repo_private:
        raise ValueError(
            "data_mode=plaintext is only supported for private repositories."
        )
    if publish_pages == "true" and data_mode != "encrypted":
        raise ValueError("publish_pages_dashboard=true requires data_mode=encrypted.")
    if publish_readme == "true" and not repo_private:
        raise ValueError(
            "publish_readme_dashboard=true is only supported for private repositories."
        )

    collection_auth_mode = "github_app" if use_github_app == "true" else "pat"
    return {
        "I_HAVE_READ_THE_README": read_readme,
        "DATA_MODE": data_mode,
        "PUBLISH_PAGES_DASHBOARD": publish_pages,
        "PUBLISH_README_DASHBOARD": publish_readme,
        "ALLOW_DOCS_SYNC": allow_docs_sync,
        "RETENTION_DAYS": str(retention_days),
        "USE_GITHUB_APP": use_github_app,
        "COLLECTION_AUTH_MODE": collection_auth_mode,
    }


def _write_env(values: dict[str, str]) -> None:
    env_path = os.environ.get("GITHUB_ENV", "").strip()
    if not env_path:
        for key, value in values.items():
            _validate_env_assignment(key, value)
            print(f"{key}={value}")
        return
    with Path(env_path).open("a", encoding="utf-8") as env_file:
        for key, value in values.items():
            _validate_env_assignment(key, value)
            env_file.write(f"{key}={value}\n")


def _validate_env_assignment(key: str, value: str) -> None:
    if not ENV_KEY_RE.match(key):
        raise ValueError(
            f"Configuration validation error: invalid environment key {key!r}."
        )
    # The following condition should not be reachable -
    # Defense in depth for future config values before writing GitHub env files.
    if any(character in value for character in ("\r", "\n")):
        raise ValueError(
            "Configuration validation error: "
            + f"environment value for {key} contains a newline."
        )


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
            "Fill in `config.yaml`, run **Actions -> Set up Reponomics dashboard**, "
            + "and let setup validate the config and write the setup marker "
            + "before this workflow does work.",
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
