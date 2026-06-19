"""Canonical config option mappings across config, workflows, and action inputs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class ConfigOptionSpec:
    config_key: str
    workflow_env_var: str
    action_input: str | None = None
    runtime_env_var: str | None = None
    default: Any = None
    explicit_decision: bool = False


class ConfigOption(Enum):
    I_HAVE_READ_README = ConfigOptionSpec(
        config_key="i_have_read_the_readme",
        workflow_env_var="I_HAVE_READ_THE_README",
        explicit_decision=True,
    )
    DATA_MODE = ConfigOptionSpec(
        config_key="data_mode",
        workflow_env_var="DATA_MODE",
        action_input="data-mode",
        runtime_env_var="REPONOMICS_DATA_MODE",
        explicit_decision=True,
    )
    PUBLISH_PAGES = ConfigOptionSpec(
        config_key="publish_pages_dashboard",
        workflow_env_var="PUBLISH_PAGES_DASHBOARD",
        action_input="publish-pages",
        runtime_env_var="REPONOMICS_PUBLISH_PAGES",
        explicit_decision=True,
    )
    PUBLISH_README = ConfigOptionSpec(
        config_key="publish_readme_dashboard",
        workflow_env_var="PUBLISH_README_DASHBOARD",
        action_input="generate-readme",
        runtime_env_var="REPONOMICS_GENERATE_README",
        explicit_decision=True,
    )
    RETENTION_DAYS = ConfigOptionSpec(
        config_key="artifact_retention_days",
        workflow_env_var="RETENTION_DAYS",
        action_input="retention-days",
        runtime_env_var="REPONOMICS_RETENTION_DAYS",
        default=90,
    )
    USE_GITHUB_APP = ConfigOptionSpec(
        config_key="use_github_app",
        workflow_env_var="USE_GITHUB_APP",
        action_input="use-github-app",
        runtime_env_var="REPONOMICS_USE_GITHUB_APP",
        default=False,
    )
    AUTO_DOCTOR_DAYS = ConfigOptionSpec(
        config_key="auto_doctor_every_n_days",
        workflow_env_var="AUTO_DOCTOR_EVERY_N_DAYS",
        default=0,
    )

    @property
    def config_key(self) -> str:
        return self.value.config_key

    @property
    def workflow_env_var(self) -> str:
        return self.value.workflow_env_var

    @property
    def action_input(self) -> str | None:
        return self.value.action_input

    @property
    def runtime_env_var(self) -> str | None:
        return self.value.runtime_env_var

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
ACTION_CONFIG_OPTIONS = tuple(
    option
    for option in CONFIG_OPTIONS
    if option.action_input is not None and option.runtime_env_var is not None
)
