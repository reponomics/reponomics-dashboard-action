"""Runtime configuration validation helpers."""

from __future__ import annotations

from .core import (
    INCIDENT_CONFIRM_IRREVERSIBLE,
    INCIDENT_CONFIRM_MODE,
    INCIDENT_CONFIRM_PURGE,
    MIN_SECRET_LENGTH,
    ActionError,
    RuntimeConfig,
)


def validate_config(config: RuntimeConfig) -> None:
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
    if config.repo_is_public and config.privacy_mode == "plain":
        raise ActionError("privacy-mode plain is only supported for private repositories.")
    if config.repo_is_public and config.generate_readme:
        raise ActionError("generate-readme is only supported for private repositories.")


def _validate_encrypted_mode(config: RuntimeConfig) -> None:
    if config.mode in {"collect", "publish"} and config.privacy_mode in {"strong", "casual"}:
        _validate_secret(
            config.dashboard_secret,
            "dashboard-secret or DASHBOARD_SECRET_DO_NOT_REPLACE",
            allow_weak=config.privacy_mode == "casual",
        )
    if config.mode == "rotate-key":
        if config.privacy_mode == "plain":
            raise ActionError("rotate-key requires strong or casual privacy mode.")
        _validate_key_rotation_secrets(config)


def _validate_incident_reset_config(config: RuntimeConfig) -> None:
    if config.privacy_mode == "plain":
        raise ActionError("incident-reset requires strong or casual privacy mode.")
    _validate_key_rotation_secrets(config)
    if not config.github_token:
        raise ActionError("github-token, GITHUB_TOKEN, or GH_TOKEN is required for incident-reset mode.")
    _validate_incident_confirmations(config)


def _validate_key_rotation_secrets(config: RuntimeConfig) -> None:
    _validate_secret(
        config.dashboard_secret,
        "dashboard-secret or DASHBOARD_SECRET_DO_NOT_REPLACE",
        allow_weak=True,
    )
    _validate_secret(
        config.dashboard_next_secret,
        "dashboard-next-secret or DASHBOARD_NEXT_SECRET",
        allow_weak=config.privacy_mode == "casual",
    )


def _validate_secret(value: str, label: str, *, allow_weak: bool) -> None:
    if not value:
        raise ActionError(f"{label} is required for the selected encrypted mode.")
    if len(value) < MIN_SECRET_LENGTH and not allow_weak:
        raise ActionError(
            f"{label} is below the Reponomics dashboard secret entropy policy. "
            + "Use a generated random secret, or set allow-weak-dashboard-secret "
            + "to true if you explicitly accept the disclosure and brute-force risk."
        )


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
