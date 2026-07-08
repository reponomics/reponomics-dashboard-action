#!/usr/bin/env python3
"""Resolve workflow-facing Reponomics config without third-party dependencies."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Any


class ConfigOptionSpec:
    __slots__ = ("config_key", "workflow_env_var", "default", "explicit_decision")

    def __init__(
        self,
        *,
        config_key: str,
        workflow_env_var: str,
        default: Any = None,
        explicit_decision: bool = False,
    ) -> None:
        self.config_key = config_key
        self.workflow_env_var = workflow_env_var
        self.default = default
        self.explicit_decision = explicit_decision


class ConfigOption(Enum):
    I_HAVE_READ_README = ConfigOptionSpec(
        config_key="i_have_read_the_readme",
        workflow_env_var="I_HAVE_READ_THE_README",
        explicit_decision=True,
    )
    DATA_MODE = ConfigOptionSpec(
        config_key="data_mode",
        workflow_env_var="DATA_MODE",
        explicit_decision=True,
    )
    PUBLISH_PAGES = ConfigOptionSpec(
        config_key="publish_pages_dashboard",
        workflow_env_var="PUBLISH_PAGES_DASHBOARD",
        explicit_decision=True,
    )
    PUBLISH_README = ConfigOptionSpec(
        config_key="publish_readme_dashboard",
        workflow_env_var="PUBLISH_README_DASHBOARD",
        explicit_decision=True,
    )
    RETENTION_DAYS = ConfigOptionSpec(
        config_key="artifact_retention_days",
        workflow_env_var="RETENTION_DAYS",
        default="90",
    )
    USE_GITHUB_APP = ConfigOptionSpec(
        config_key="use_github_app",
        workflow_env_var="USE_GITHUB_APP",
        default="false",
    )
    AUTO_DOCTOR_DAYS = ConfigOptionSpec(
        config_key="auto_doctor_every_n_days",
        workflow_env_var="AUTO_DOCTOR_EVERY_N_DAYS",
        default="0",
    )

    @property
    def config_key(self) -> str:
        return self.value.config_key

    @property
    def workflow_env_var(self) -> str:
        return self.value.workflow_env_var

    @property
    def default(self) -> Any:
        return self.value.default

    @property
    def explicit_decision(self) -> bool:
        return self.value.explicit_decision


CONFIG_OPTIONS = tuple(ConfigOption)
EXPLICIT_DECISION_OPTIONS = tuple(
    option for option in CONFIG_OPTIONS if option.explicit_decision
)
DEFAULTED_OPTIONS = tuple(
    option for option in CONFIG_OPTIONS if not option.explicit_decision
)
CONFIG_KEYS = {
    option.config_key: option.workflow_env_var for option in CONFIG_OPTIONS
}

EXPLICIT_DECISION_KEYS = tuple(
    option.config_key for option in EXPLICIT_DECISION_OPTIONS
)
DEFAULT_CONFIG_VALUES = {
    option.config_key: option.default for option in DEFAULTED_OPTIONS
}
VALID_DATA_MODES = {"encrypted", "plaintext"}
MIN_RETENTION_DAYS = 14
MAX_RETENTION_DAYS = 90
MIN_AUTO_DOCTOR_DAYS = 0
MAX_AUTO_DOCTOR_DAYS = 30
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


def _defaulted_scalar(scalars: dict[str, str], key: str) -> str:
    value = scalars.get(key, "").strip()
    if value:
        return value
    return DEFAULT_CONFIG_VALUES[key]


def _resolve(config_path: Path) -> dict[str, str]:
    scalars = _load_top_level_scalars(config_path)
    missing = [key for key in EXPLICIT_DECISION_KEYS if not scalars.get(key, "").strip()]
    if missing:
        formatted = ", ".join(missing)
        raise ValueError(
            "Complete the explicit decision fields in config.yaml before running setup: "
            + formatted
            + "."
        )

    read_readme = _bool(
        _required_scalar(scalars, ConfigOption.I_HAVE_READ_README.config_key),
        name=ConfigOption.I_HAVE_READ_README.config_key,
    )
    if read_readme != "true":
        raise ValueError(
            "i_have_read_the_readme must be true before setup can proceed."
        )

    data_mode = _required_scalar(scalars, ConfigOption.DATA_MODE.config_key).lower()
    if data_mode not in VALID_DATA_MODES:
        allowed = ", ".join(sorted(VALID_DATA_MODES))
        raise ValueError(f"data_mode must be one of: {allowed}.")

    try:
        retention_days = int(
            _defaulted_scalar(scalars, ConfigOption.RETENTION_DAYS.config_key)
        )
    except ValueError as exc:
        raise ValueError("artifact_retention_days must be an integer.") from exc
    if retention_days < MIN_RETENTION_DAYS or retention_days > MAX_RETENTION_DAYS:
        raise ValueError(
            "artifact_retention_days must be between "
            + f"{MIN_RETENTION_DAYS} and {MAX_RETENTION_DAYS}."
        )

    try:
        auto_doctor_days = int(
            _defaulted_scalar(scalars, ConfigOption.AUTO_DOCTOR_DAYS.config_key)
        )
    except ValueError as exc:
        raise ValueError("auto_doctor_every_n_days must be an integer.") from exc
    if auto_doctor_days < MIN_AUTO_DOCTOR_DAYS or auto_doctor_days > MAX_AUTO_DOCTOR_DAYS:
        raise ValueError(
            "auto_doctor_every_n_days must be between "
            f"{MIN_AUTO_DOCTOR_DAYS} and {MAX_AUTO_DOCTOR_DAYS}."
        )

    publish_pages = _bool(
        _required_scalar(scalars, ConfigOption.PUBLISH_PAGES.config_key),
        name=ConfigOption.PUBLISH_PAGES.config_key,
    )
    publish_readme = _bool(
        _required_scalar(scalars, ConfigOption.PUBLISH_README.config_key),
        name=ConfigOption.PUBLISH_README.config_key,
    )
    use_github_app = _bool(
        _defaulted_scalar(scalars, ConfigOption.USE_GITHUB_APP.config_key),
        name=ConfigOption.USE_GITHUB_APP.config_key,
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
        ConfigOption.I_HAVE_READ_README.workflow_env_var: read_readme,
        ConfigOption.DATA_MODE.workflow_env_var: data_mode,
        ConfigOption.PUBLISH_PAGES.workflow_env_var: publish_pages,
        ConfigOption.PUBLISH_README.workflow_env_var: publish_readme,
        ConfigOption.RETENTION_DAYS.workflow_env_var: str(retention_days),
        ConfigOption.USE_GITHUB_APP.workflow_env_var: use_github_app,
        ConfigOption.AUTO_DOCTOR_DAYS.workflow_env_var: str(auto_doctor_days),
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
            "Fill in `config.yaml`, run **Actions -> Setup -> Run workflow**, "
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
