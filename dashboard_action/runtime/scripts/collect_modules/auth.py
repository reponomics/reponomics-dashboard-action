"""Collector configuration and token validation."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, NoReturn

import requests

from collect_modules.constants import (
    APP_TOKEN_VALIDATION_URL,
    CONFIG_PATH,
    TOKEN_CREATION_URL,
    TOKEN_VALIDATION_URL,
)
from collect_modules.errors import CollectionAbort
from collect_modules.types import Headers
from repo_config import load_repo_config


def _abort(message: str) -> NoReturn:
    raise CollectionAbort(message)


def load_config(config_path: str = CONFIG_PATH) -> dict[str, Any]:
    """Load repository-selection settings from config.yaml."""
    try:
        return load_repo_config(config_path)
    except ValueError as exc:
        print(f"Error: {exc}")
        _abort(str(exc))


def use_github_app_collection_token() -> bool:
    """Return whether collection is using a GitHub App installation token."""
    raw = (os.environ.get("REPONOMICS_USE_GITHUB_APP") or "").strip().lower()
    if raw in {"", "0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    print("Error: REPONOMICS_USE_GITHUB_APP must be true or false.")
    _abort("REPONOMICS_USE_GITHUB_APP must be true or false.")


def get_headers(
    *,
    use_github_app: Callable[[], bool] = use_github_app_collection_token,
) -> dict[str, str]:
    """Build GitHub API headers from GH_TOKEN or exit with setup guidance."""
    token = os.environ.get("GH_TOKEN")
    if not token:
        print("Error: GH_TOKEN environment variable is not set.")
        if use_github_app():
            print(
                "Set collection-token (or COLLECTION_TOKEN) to a GitHub App "
                + "installation token minted by your workflow."
            )
        else:
            print("Set the COLLECTION_TOKEN secret in your repository settings.")
        _abort("GH_TOKEN environment variable is not set.")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
    }


def validate_token(
    headers: Headers,
    *,
    use_github_app: bool | None,
    use_github_app_collection_token: Callable[[], bool],
    perform_get: Callable[..., requests.Response],
    record_network_warning: Callable[[str, int, requests.RequestException], None],
    write_step_summary: Callable[..., None],
) -> None:
    """Verify the token is valid before starting collection."""
    if use_github_app is None:
        use_github_app = use_github_app_collection_token()
    validation_url = APP_TOKEN_VALIDATION_URL if use_github_app else TOKEN_VALIDATION_URL
    try:
        resp = perform_get(validation_url, headers=headers, timeout=15)
    except requests.RequestException as exc:
        record_network_warning(validation_url, 1, exc)
        write_step_summary("failed", errors=["token validation"])
        print(f"Error: could not reach GitHub API: {exc}")
        _abort(f"could not reach GitHub API: {exc}")

    if use_github_app:
        _validate_app_token_response(resp)
        return

    _validate_pat_response(resp)


def _validate_app_token_response(resp: requests.Response) -> None:
    if resp.status_code == 401:
        print("Error: the GitHub App installation token is invalid or expired.")
        print(
            "Mint a fresh installation token in the workflow and make sure "
            + "the app is installed on the repositories you collect."
        )
        _abort("the GitHub App installation token is invalid or expired.")
    if resp.status_code == 403:
        print("Error: the GitHub App installation token lacks required permissions.")
        print("The app installation needs repository Administration: read access.")
        _abort("the GitHub App installation token lacks required permissions.")
    if resp.status_code >= 400:
        print(
            f"Error: GitHub API returned status {resp.status_code} "
            + "during GitHub App token validation."
        )
        _abort(f"GitHub API returned status {resp.status_code} during GitHub App token validation.")
    payload = resp.json()
    if not isinstance(payload, dict):
        print(
            "Error: token validation response for app installation token "
            + "was not a JSON object."
        )
        _abort("token validation response for app installation token was not a JSON object.")
    repos = payload.get("repositories")
    if not isinstance(repos, list):
        print(
            "Error: token validation response for app installation token "
            + "did not include a repositories list."
        )
        _abort("token validation response for app installation token did not include a repositories list.")
    print(
        "Authenticated as GitHub App installation token "
        + f"(accessible repositories in first page: {len(repos)})."
    )


def _validate_pat_response(resp: requests.Response) -> None:
    if resp.status_code == 401:
        print("Error: COLLECTION_TOKEN is invalid or expired.")
        print(f"Create a fine-grained personal access token: {TOKEN_CREATION_URL}")
        _abort("COLLECTION_TOKEN is invalid or expired.")
    if resp.status_code == 403:
        print("Error: COLLECTION_TOKEN lacks required permissions.")
        print("The token needs repository Administration: read access.")
        _abort("COLLECTION_TOKEN lacks required permissions.")
    if resp.status_code >= 400:
        print(
            f"Error: GitHub API returned status {resp.status_code} during token validation."
        )
        _abort(f"GitHub API returned status {resp.status_code} during token validation.")
    user = resp.json().get("login", "unknown")
    print(f"Authenticated as: {user}")
