"""Runtime configuration validation helpers."""

from __future__ import annotations

from .core import (
    INCIDENT_CONFIRM_IRREVERSIBLE,
    INCIDENT_CONFIRM_MODE,
    INCIDENT_CONFIRM_PURGE,
    ActionError,
    RuntimeConfig,
)


def validate_config(config: RuntimeConfig) -> None:
    if config.mode == "doctor":
        return
    _validate_collect_credentials(config)
    _validate_public_repo_settings(config)
    _validate_encrypted_mode(config)
    if config.mode == "incident-reset":
        _validate_incident_reset_config(config)


def validate_collect_cleanup_config(config: RuntimeConfig) -> None:
    if config.mode != "collect":
        raise ActionError("collect-retention-cleanup-only requires collect mode.")
    if not config.github_token:
        raise ActionError("github-token, GITHUB_TOKEN, or GH_TOKEN is required for collect artifact cleanup.")


def _validate_collect_credentials(config: RuntimeConfig) -> None:
    if config.mode == "collect" and not config.collection_token:
        raise ActionError("collection-token, COLLECTION_TOKEN, or GH_TOKEN is required for collect mode.")
    if config.mode == "collect" and not config.github_token:
        raise ActionError("github-token, GITHUB_TOKEN, or GH_TOKEN is required for collect mode.")


def _validate_public_repo_settings(config: RuntimeConfig) -> None:
    if config.repo_is_public and config.data_mode == "plaintext":
        raise ActionError("data-mode plaintext is only supported for private repositories.")
    if config.repo_is_public and config.generate_readme:
        raise ActionError("generate-readme is only supported for private repositories.")


def _validate_encrypted_mode(config: RuntimeConfig) -> None:
    if config.mode in {"collect", "publish"} and config.data_mode == "encrypted":
        _validate_secret(
            config.dashboard_secret,
            "dashboard-secret or DASHBOARD_SECRET_DO_NOT_REPLACE",
        )
    if config.mode == "rotate-key":
        if config.data_mode == "plaintext":
            raise ActionError("rotate-key requires encrypted data mode.")
        _validate_key_rotation_secrets(config)


def _validate_incident_reset_config(config: RuntimeConfig) -> None:
    if config.data_mode == "plaintext":
        raise ActionError("incident-reset requires encrypted data mode.")
    _validate_key_rotation_secrets(config)
    if not config.github_token:
        raise ActionError("github-token, GITHUB_TOKEN, or GH_TOKEN is required for incident-reset mode.")
    _validate_incident_confirmations(config)


def _validate_key_rotation_secrets(config: RuntimeConfig) -> None:
    _validate_secret(
        config.dashboard_secret,
        "dashboard-secret or DASHBOARD_SECRET_DO_NOT_REPLACE",
    )
    _validate_secret(
        config.dashboard_next_secret,
        "dashboard-next-secret or DASHBOARD_NEXT_SECRET",
    )


def _validate_secret(value: str, label: str) -> None:
    if not value:
        raise ActionError(f"{label} is required for the selected encrypted mode.")


def _validate_incident_confirmations(config: RuntimeConfig) -> None:
    if config.incident_confirm_mode != INCIDENT_CONFIRM_MODE:
        raise ActionError(
            "incident-confirm-mode must be set to "
            + f"{INCIDENT_CONFIRM_MODE!r} for incident-reset mode."
        )
    if config.incident_confirm_purge != INCIDENT_CONFIRM_PURGE:
        raise ActionError(
            "incident-confirm-purge must be set to "
            + f"{INCIDENT_CONFIRM_PURGE!r} for incident-reset mode."
        )
    if config.incident_confirm_irreversible != INCIDENT_CONFIRM_IRREVERSIBLE:
        raise ActionError(
            "incident-confirm-irreversible must be set to "
            + f"{INCIDENT_CONFIRM_IRREVERSIBLE!r} for incident-reset mode."
        )
