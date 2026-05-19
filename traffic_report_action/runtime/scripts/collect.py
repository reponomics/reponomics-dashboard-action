"""Fetch traffic and aggregate repository metric data from the GitHub API.

Handles authentication validation, repository discovery, request pacing,
transient-failure retries, secondary-rate-limit aborts, and structured error
reporting so that bad tokens or API errors surface clearly instead of
producing silently empty data.
"""

from __future__ import annotations

import math
import os
import random
import sys
import time
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, TypedDict

import requests

from repo_config import load_repo_config
from storage import (
    DATA_DIR,
    SCHEMA_VERSION,
    LOG_FIELDS,
    SNAPSHOT_FIELDS,
    REFERRER_FIELDS,
    PATH_FIELDS,
    REPO_METRIC_FIELDS,
    append_csv,
    read_manifest,
    write_manifest,
)

CONFIG_PATH = "config.yaml"

MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds; doubles each attempt
REQUEST_PACING_MIN_SECONDS = 0.5
REQUEST_PACING_MAX_SECONDS = 1.0
SECONDARY_LIMIT_FALLBACK_SECONDS = 60
NOT_FOUND_RETRIES = 2
TOKEN_VALIDATION_URL = "https://api.github.com/user"
REPO_DISCOVERY_URL = "https://api.github.com/user/repos"
REPO_DISCOVERY_PAGE_SIZE = 100
CURRENT_REPOSITORY_ENV_KEYS = ("GITHUB_REPOSITORY", "GH_REPO")

Headers = Mapping[str, str]
RepoMetadata = dict[str, Any]


class NetworkWarning(TypedDict):
    url: str
    attempt: int
    error_type: str
    message: str


_LAST_REQUEST_COMPLETED_AT: float | None = None
_NETWORK_WARNINGS: list[NetworkWarning] = []
_REPO_DETAIL_WARNINGS: list[str] = []


class SecondaryRateLimitError(requests.HTTPError):
    """Abort collection immediately when GitHub reports a secondary limit."""

    def __init__(
        self,
        url: str,
        response: requests.Response,
        retry_after_seconds: int,
        retry_at_utc: datetime,
        source: str,
    ) -> None:
        self.url = url
        self.response = response
        self.retry_after_seconds = retry_after_seconds
        self.retry_at_utc = retry_at_utc
        self.retry_source = source
        message = (
            "GitHub secondary rate limit encountered for "
            f"{url}. Do not retry until after "
            f"{retry_at_utc.strftime('%Y-%m-%d %H:%M:%S UTC')} "
            f"({retry_after_seconds}s, source: {source})."
        )
        super().__init__(message, response=response)


class RepoUnavailableError(requests.HTTPError):
    """Skip a repo for this run after repeated 404s from traffic endpoints."""

    def __init__(
        self,
        url: str,
        response: requests.Response,
        attempts: int,
    ) -> None:
        self.url = url
        self.response = response
        self.attempts = attempts
        message = (
            "Repository traffic endpoint remained unavailable after "
            f"{attempts} attempt(s): {url}. The repo may have been deleted, "
            "renamed, transferred, or may no longer be accessible."
        )
        super().__init__(message, response=response)


def _reset_runtime_state() -> None:
    """Reset per-run pacing and warning state."""
    global _LAST_REQUEST_COMPLETED_AT, _NETWORK_WARNINGS, _REPO_DETAIL_WARNINGS
    _LAST_REQUEST_COMPLETED_AT = None
    _NETWORK_WARNINGS = []
    _REPO_DETAIL_WARNINGS = []


def _record_network_warning(
    url: str,
    attempt: int,
    exc: requests.RequestException,
) -> None:
    """Track transient network problems for the workflow summary."""
    _NETWORK_WARNINGS.append({
        "url": url,
        "attempt": attempt,
        "error_type": exc.__class__.__name__,
        "message": str(exc),
    })


def _write_step_summary(
    outcome: str,
    errors: list[str] | None = None,
    secondary_limit: SecondaryRateLimitError | None = None,
    skipped_repos: list[str] | None = None,
) -> None:
    """Write a GitHub Actions step summary when available."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    lines = [
        "## Traffic Collection Summary",
        "",
        f"- Outcome: **{outcome}**",
    ]

    if errors:
        lines.append(f"- Repositories with errors: {', '.join(errors)}")
    if skipped_repos:
        lines.append(
            "- Repositories skipped as unavailable: "
            + ", ".join(skipped_repos)
        )

    if secondary_limit is not None:
        lines.extend([
            "",
            "### Secondary Rate Limit",
            "",
            f"- Endpoint: `{secondary_limit.url}`",
            f"- Status: `{secondary_limit.response.status_code}`",
            f"- Retry source: `{secondary_limit.retry_source}`",
            f"- Retry after: `{secondary_limit.retry_after_seconds}` second(s)",
            f"- Do not retry before: **{secondary_limit.retry_at_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}**",
            "- Action: Stop rerunning the workflow until that time has passed.",
        ])

    if _NETWORK_WARNINGS:
        lines.extend([
            "",
            "### Network Warnings",
            "",
            "Transient network errors were observed during collection:",
        ])
        for warning in _NETWORK_WARNINGS:
            lines.append(
                "- Attempt "
                f"{warning['attempt']} for `{warning['url']}` failed with "
                f"`{warning['error_type']}`: {warning['message']}"
            )

    if _REPO_DETAIL_WARNINGS:
        lines.extend([
            "",
            "### Repository Detail Warnings",
            "",
        ])
        lines.extend(f"- {warning}" for warning in _REPO_DETAIL_WARNINGS)

    with open(summary_path, "a") as f:
        f.write("\n".join(lines) + "\n")


def _pace_request() -> None:
    """Serialize requests with a small random gap to avoid bursty polling."""
    global _LAST_REQUEST_COMPLETED_AT
    if _LAST_REQUEST_COMPLETED_AT is None:
        return

    target_gap = random.uniform(
        REQUEST_PACING_MIN_SECONDS,
        REQUEST_PACING_MAX_SECONDS,
    )
    elapsed = time.monotonic() - _LAST_REQUEST_COMPLETED_AT
    if elapsed < target_gap:
        time.sleep(target_gap - elapsed)


def _mark_request_complete() -> None:
    """Track when the previous request finished for pacing."""
    global _LAST_REQUEST_COMPLETED_AT
    _LAST_REQUEST_COMPLETED_AT = time.monotonic()


def _perform_get(url: str, headers: Headers, timeout: int) -> requests.Response:
    """Issue a paced GET request and update pacing state afterwards."""
    _pace_request()
    try:
        return requests.get(url, headers=headers, timeout=timeout)
    finally:
        _mark_request_complete()


def _response_text_lower(resp: requests.Response) -> str:
    text = getattr(resp, "text", "") or ""
    return text.lower()


def _is_secondary_rate_limit(resp: requests.Response) -> bool:
    """Detect GitHub secondary-rate-limit responses."""
    return resp.status_code in {403, 429} and "secondary" in _response_text_lower(resp)


def _parse_retry_after_seconds(value: str | None) -> int | None:
    """Parse a Retry-After header as either delta-seconds or HTTP-date."""
    if not value:
        return None

    try:
        return max(0, int(math.ceil(float(value))))
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None

    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    retry_at = retry_at.astimezone(timezone.utc)
    return max(
        0,
        int(math.ceil((retry_at - datetime.now(timezone.utc)).total_seconds())),
    )


def _secondary_retry_window(resp: requests.Response) -> tuple[int, datetime, str]:
    """Return how long to wait before retrying a secondary-limited request."""
    retry_after_header = resp.headers.get("Retry-After")
    retry_after_seconds = _parse_retry_after_seconds(retry_after_header)
    source = "Retry-After"
    if retry_after_seconds is None:
        reset_header = resp.headers.get("X-RateLimit-Reset")
        if reset_header:
            try:
                reset_epoch = int(reset_header)
            except ValueError:
                reset_epoch = None
            if reset_epoch is not None:
                retry_after_seconds = max(
                    0, reset_epoch - int(datetime.now(timezone.utc).timestamp())
                )
                source = "X-RateLimit-Reset"

    if retry_after_seconds is None:
        retry_after_seconds = SECONDARY_LIMIT_FALLBACK_SECONDS
        source = "default-minimum"

    retry_at_utc = datetime.now(timezone.utc) + timedelta(seconds=retry_after_seconds)
    return retry_after_seconds, retry_at_utc, source


def _is_retryable_throttle(resp: requests.Response) -> bool:
    """Return whether a non-secondary 403/429 looks transient."""
    text = _response_text_lower(resp)
    if resp.status_code == 429:
        return True
    if resp.status_code != 403:
        return False
    return (
        "rate limit" in text
        or "abuse" in text
        or "temporarily unavailable" in text
        or bool(resp.headers.get("Retry-After"))
        or resp.headers.get("X-RateLimit-Remaining") == "0"
    )


def _retry_delay_with_jitter(attempt: int) -> float:
    """Compute exponential backoff with jitter for retryable throttling/errors."""
    base = RETRY_BACKOFF * (2 ** (attempt - 1))
    return base + random.uniform(0, base / 2)


def load_config() -> dict[str, Any]:
    """Load repository-selection settings from config.yaml."""
    try:
        return load_repo_config(CONFIG_PATH)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)


def get_headers() -> dict[str, str]:
    token = os.environ.get("GH_TOKEN")
    if not token:
        print("Error: GH_TOKEN environment variable is not set.")
        print("Set the TRAFFIC_TOKEN secret in your repository settings.")
        sys.exit(1)
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def validate_token(headers: Headers) -> None:
    """Verify the token is valid before starting collection."""
    try:
        resp = _perform_get(TOKEN_VALIDATION_URL, headers=headers, timeout=15)
    except requests.RequestException as exc:
        _record_network_warning(TOKEN_VALIDATION_URL, 1, exc)
        _write_step_summary("failed", errors=["token validation"])
        print(f"Error: could not reach GitHub API: {exc}")
        sys.exit(1)
    if resp.status_code == 401:
        print("Error: TRAFFIC_TOKEN is invalid or expired.")
        print("Create a new token at https://github.com/settings/tokens")
        sys.exit(1)
    if resp.status_code == 403:
        print("Error: TRAFFIC_TOKEN lacks required permissions.")
        print("The token needs read access to repository traffic data.")
        sys.exit(1)
    if resp.status_code >= 400:
        print(f"Error: GitHub API returned status {resp.status_code} during token validation.")
        sys.exit(1)
    user = resp.json().get("login", "unknown")
    print(f"Authenticated as: {user}")


def fetch_json(
    url: str,
    headers: Headers,
    allow_not_found: bool = False,
) -> Any:
    """Fetch JSON from the GitHub API with pacing and targeted retries."""
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = _perform_get(url, headers=headers, timeout=30)
        except requests.RequestException as exc:
            last_exc = exc
            _record_network_warning(url, attempt, exc)
            if attempt < MAX_RETRIES:
                wait = _retry_delay_with_jitter(attempt)
                print(
                    f"  Retry {attempt}/{MAX_RETRIES} after network error: {exc} "
                    f"(sleeping {wait:.2f}s)"
                )
                time.sleep(wait)
                continue
            break

        if _is_secondary_rate_limit(resp):
            retry_after_seconds, retry_at_utc, source = _secondary_retry_window(resp)
            raise SecondaryRateLimitError(
                url,
                resp,
                retry_after_seconds,
                retry_at_utc,
                source,
            )

        if _is_retryable_throttle(resp) and attempt < MAX_RETRIES:
            wait = _retry_delay_with_jitter(attempt)
            print(
                f"  Transient throttle {resp.status_code} — retrying in {wait:.2f}s..."
            )
            time.sleep(wait)
            continue

        if resp.status_code >= 500 and attempt < MAX_RETRIES:
            wait = _retry_delay_with_jitter(attempt)
            print(
                f"  Server error {resp.status_code} — retrying in {wait:.2f}s..."
            )
            time.sleep(wait)
            continue

        if resp.status_code == 404:
            if allow_not_found and attempt <= NOT_FOUND_RETRIES:
                wait = _retry_delay_with_jitter(attempt)
                print(
                    f"  404 for {url} — retrying in {wait:.2f}s to confirm the repo is unavailable..."
                )
                time.sleep(wait)
                continue
            if allow_not_found:
                raise RepoUnavailableError(url, resp, attempt)
            print(f"  Warning: {url} returned 404 — repo may not exist or token lacks access.")
            raise requests.HTTPError(
                f"404 Not Found: {url}", response=resp
            )

        resp.raise_for_status()
        return resp.json()

    # All retries exhausted
    if last_exc:
        raise last_exc
    raise requests.HTTPError(
        f"Failed after {MAX_RETRIES} retries: {url}", response=resp
    )


def discover_repositories(headers: Headers) -> list[RepoMetadata]:
    """Return all accessible repositories visible to the authenticated user."""
    page = 1
    discovered = []
    while True:
        url = (
            f"{REPO_DISCOVERY_URL}?affiliation=owner,collaborator,organization_member"
            f"&sort=updated&direction=desc&per_page={REPO_DISCOVERY_PAGE_SIZE}"
            f"&page={page}"
        )
        page_rows = fetch_json(url, headers)
        if not page_rows:
            break
        discovered.extend(page_rows)
        if len(page_rows) < REPO_DISCOVERY_PAGE_SIZE:
            break
        page += 1
    return discovered


def _is_trackable_repo(repo: RepoMetadata) -> bool:
    """Return whether a discovered repository is eligible for tracking."""
    permissions = repo.get("permissions") or {}
    return (
        bool(repo.get("full_name"))
        and not repo.get("fork", False)
        and not repo.get("archived", False)
        and not repo.get("disabled", False)
        and bool(permissions.get("push") or permissions.get("admin"))
    )


def _selection_state(manifest: dict[str, Any]) -> dict[str, str]:
    """Return the persisted automatic-selection state."""
    state = manifest.get("selection_state")
    if not isinstance(state, dict):
        state = {}
        manifest["selection_state"] = state
    state.setdefault("auto_seeded_at", "")
    state.setdefault("auto_cutoff_created_at", "")
    return state


def _current_repository() -> str:
    """Return the repository running the collector when available."""
    for env_key in CURRENT_REPOSITORY_ENV_KEYS:
        value = (os.environ.get(env_key) or "").strip()
        if "/" in value:
            return value
    return ""


def _resolve_named_repos(
    repo_names: list[str],
    eligible: dict[str, RepoMetadata],
) -> tuple[list[RepoMetadata], list[str]]:
    """Resolve a configured repo list against the discovered eligible set."""
    resolved = []
    missing = []
    seen = set()

    for repo_name in repo_names:
        if repo_name in seen:
            continue
        repo = eligible.get(repo_name)
        if repo is None:
            missing.append(repo_name)
            continue
        resolved.append(repo)
        seen.add(repo_name)

    return resolved, missing


def _sort_auto_candidates(repos: list[RepoMetadata]) -> list[RepoMetadata]:
    """Sort automatic candidates by creation date descending, then name."""
    repos = sorted(repos, key=lambda repo: repo.get("full_name") or "")
    return sorted(repos, key=lambda repo: repo.get("created_at") or "", reverse=True)


def _build_auto_candidates(
    eligible: dict[str, RepoMetadata],
    excluded: set[str],
    selected_names: set[str],
    current_repository: str,
    include_private: bool,
    include_new: bool,
    auto_seeded_at: str,
) -> list[RepoMetadata]:
    """Return automatic candidates after applying explicit selection rules."""
    candidates = []
    for repo_name, repo in eligible.items():
        if repo_name in selected_names or repo_name in excluded:
            continue
        if current_repository and repo_name == current_repository:
            continue
        if not include_private and repo.get("private", False):
            continue
        if (
            auto_seeded_at
            and not include_new
            and (repo.get("created_at") or "") > auto_seeded_at
        ):
            continue
        candidates.append(repo)
    return _sort_auto_candidates(candidates)


def resolve_repositories(
    headers: Headers,
    config: dict[str, Any],
    manifest: dict[str, Any],
) -> tuple[list[str], dict[str, Any], dict[str, RepoMetadata]]:
    """Resolve the tracked repo set from explicit config plus stable auto-fill."""
    discovered = discover_repositories(headers)

    eligible = {}
    for repo in discovered:
        full_name = (repo.get("full_name") or "").strip()
        if not full_name or full_name in eligible:
            continue
        if _is_trackable_repo(repo):
            eligible[full_name] = repo

    include_only = config["include_only"]
    include = config["include"]
    exclude = set(config["exclude"])
    max_repos = config["max_repos"]
    current_repository = _current_repository()

    if include_only:
        include_only_repos, missing_include_only = _resolve_named_repos(
            include_only,
            eligible,
        )
        if missing_include_only:
            print(
                "Warning: some configured include_only repos were not eligible "
                "for tracking (missing access, archived, forked, disabled, or "
                "no push access): "
                + ", ".join(missing_include_only)
            )
        resolved = [repo["full_name"] for repo in include_only_repos[:max_repos]]
        if not resolved:
            print("Error: no eligible repositories remain in 'include_only'.")
            sys.exit(1)
        print(
            "Repository discovery: "
            f"{len(discovered)} accessible, {len(eligible)} eligible after filters, "
            f"tracking {len(resolved)} from include_only."
        )
        return resolved, manifest, {
            repo_name: eligible[repo_name]
            for repo_name in resolved
            if repo_name in eligible
        }

    include_repos, missing_include = _resolve_named_repos(include, eligible)
    if missing_include:
        print(
            "Warning: some configured include repos were not eligible for "
            "tracking (missing access, archived, forked, disabled, or no push "
            "access): "
            + ", ".join(missing_include)
        )

    resolved = [repo["full_name"] for repo in include_repos]
    selected_names = set(resolved)
    explicit_count = len(resolved)
    auto_count = 0
    state = _selection_state(manifest)

    if config["include_others"] and len(resolved) < max_repos:
        if not state["auto_seeded_at"]:
            state["auto_seeded_at"] = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        auto_candidates = _build_auto_candidates(
            eligible=eligible,
            excluded=exclude,
            selected_names=selected_names,
            current_repository=current_repository,
            include_private=config["include_private"],
            include_new=config["include_new"],
            auto_seeded_at=state["auto_seeded_at"],
        )
        remaining_slots = max_repos - len(resolved)
        selected_auto = auto_candidates[:remaining_slots]
        resolved.extend(repo["full_name"] for repo in selected_auto)
        auto_count = len(selected_auto)
        state["auto_cutoff_created_at"] = (
            selected_auto[-1].get("created_at") or ""
            if selected_auto
            else ""
        )
    else:
        state["auto_cutoff_created_at"] = ""

    print(
        "Repository discovery: "
        f"{len(discovered)} accessible, {len(eligible)} eligible after filters, "
        f"tracking {len(resolved)} "
        f"({explicit_count} explicit, {auto_count} automatic)."
    )

    if not resolved:
        print("Error: no eligible repositories found for traffic collection.")
        print(
            "Check your config or token access. Explicit includes must be "
            "accessible, and automatic tracking excludes forks, archived repos, "
            "disabled repos, and repos without push access."
        )
        sys.exit(1)

    return resolved, manifest, {
        repo_name: eligible[repo_name]
        for repo_name in resolved
        if repo_name in eligible
    }


def collect_views_clones(
    repo: str,
    headers: Headers,
    captured_at: str,
) -> list[dict[str, Any]]:
    """Fetch views and clones and return per-day rows for the log."""
    base = f"https://api.github.com/repos/{repo}/traffic"
    views_data = fetch_json(f"{base}/views", headers, allow_not_found=True)
    clones_data = fetch_json(f"{base}/clones", headers, allow_not_found=True)

    # Index clones by date for joining
    clones_by_date = {}
    for entry in clones_data.get("clones", []):
        ts = entry["timestamp"][:10]
        clones_by_date[ts] = entry

    rows = []
    for entry in views_data.get("views", []):
        ts = entry["timestamp"][:10]
        clone_entry = clones_by_date.pop(ts, {})
        rows.append({
            "repo": repo,
            "ts": ts,
            "views_count": entry.get("count", 0),
            "views_uniques": entry.get("uniques", 0),
            "clones_count": clone_entry.get("count", 0),
            "clones_uniques": clone_entry.get("uniques", 0),
            "captured_at": captured_at,
            "source": "api",
            "schema_version": SCHEMA_VERSION,
        })

    # Remaining clone-only dates
    for ts, clone_entry in clones_by_date.items():
        rows.append({
            "repo": repo,
            "ts": ts,
            "views_count": 0,
            "views_uniques": 0,
            "clones_count": clone_entry.get("count", 0),
            "clones_uniques": clone_entry.get("uniques", 0),
            "captured_at": captured_at,
            "source": "api",
            "schema_version": SCHEMA_VERSION,
        })

    return rows


def collect_referrers(
    repo: str,
    headers: Headers,
    captured_at: str,
) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/traffic/popular/referrers"
    data = fetch_json(url, headers, allow_not_found=True)
    return [
        {
            "repo": repo,
            "captured_at": captured_at,
            "referrer": item.get("referrer", ""),
            "count": item.get("count", 0),
            "uniques": item.get("uniques", 0),
            "schema_version": SCHEMA_VERSION,
        }
        for item in data
    ]


def collect_paths(
    repo: str,
    headers: Headers,
    captured_at: str,
) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/traffic/popular/paths"
    data = fetch_json(url, headers, allow_not_found=True)
    return [
        {
            "repo": repo,
            "captured_at": captured_at,
            "path": item.get("path", ""),
            "title": item.get("title", ""),
            "count": item.get("count", 0),
            "uniques": item.get("uniques", 0),
            "schema_version": SCHEMA_VERSION,
        }
        for item in data
    ]


def collect_repo_detail(repo: str, headers: Headers) -> RepoMetadata:
    """Fetch the canonical repository profile used for growth metrics."""
    url = f"https://api.github.com/repos/{repo}"
    data = fetch_json(url, headers)
    if not isinstance(data, dict):
        raise requests.HTTPError(
            f"Unexpected repository detail response for {repo}: {type(data).__name__}"
        )
    return data


def collect_repo_metrics(
    repo: str,
    repo_detail: RepoMetadata,
    captured_at: str,
    *,
    source: str = "repo-detail",
) -> list[dict[str, Any]]:
    """Return aggregate repository growth counters from repository detail data."""
    return [{
        "repo": repo,
        "repo_id": repo_detail.get("id", ""),
        "node_id": repo_detail.get("node_id", ""),
        "ts": captured_at[:10],
        "captured_at": captured_at,
        "stargazers_count": int(repo_detail.get("stargazers_count", 0) or 0),
        "subscribers_count": int(repo_detail.get("subscribers_count", 0) or 0),
        "forks_count": int(repo_detail.get("forks_count", 0) or 0),
        "open_issues_count": int(repo_detail.get("open_issues_count", 0) or 0),
        "size_kb": int(repo_detail.get("size", 0) or 0),
        "created_at": repo_detail.get("created_at", ""),
        "pushed_at": repo_detail.get("pushed_at", ""),
        "updated_at": repo_detail.get("updated_at", ""),
        "language": repo_detail.get("language", ""),
        "visibility": repo_detail.get("visibility", ""),
        "default_branch": repo_detail.get("default_branch", ""),
        "has_pages": repo_detail.get("has_pages", ""),
        "has_discussions": repo_detail.get("has_discussions", ""),
        "archived": repo_detail.get("archived", ""),
        "disabled": repo_detail.get("disabled", ""),
        "source": source,
        "schema_version": SCHEMA_VERSION,
    }]


def _fallback_repo_detail_warning(repo: str, exc: Exception) -> str:
    return (
        f"{repo}: repository detail request failed ({exc}); "
        "traffic collection continued and repo metrics used discovery fallback."
    )


def main() -> None:
    _reset_runtime_state()
    config = load_config()
    headers = get_headers()
    validate_token(headers)
    manifest = read_manifest(DATA_DIR)
    repos, manifest, repo_metadata = resolve_repositories(headers, config, manifest)
    write_manifest(manifest, DATA_DIR)
    captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    errors = []
    skipped_repos: list[str] = []
    for repo in repos:
        print(f"Collecting traffic for {repo}...")
        detail = None
        metric_source = "repo-detail"
        try:
            try:
                detail = collect_repo_detail(repo, headers)
            except SecondaryRateLimitError:
                raise
            except (requests.HTTPError, requests.RequestException) as exc:
                warning = _fallback_repo_detail_warning(repo, exc)
                _REPO_DETAIL_WARNINGS.append(warning)
                print(f"  Warning: {warning}")
                detail = repo_metadata.get(repo, {})
                metric_source = "discovery-fallback"

            vc_rows = collect_views_clones(repo, headers, captured_at)
            append_csv(os.path.join(DATA_DIR, "traffic-log.csv"), vc_rows, LOG_FIELDS)

            # Snapshot rows share structure but omit source
            snapshot_rows = [
                {k: v for k, v in row.items() if k in SNAPSHOT_FIELDS}
                for row in vc_rows
            ]
            append_csv(os.path.join(DATA_DIR, "traffic-snapshots.csv"), snapshot_rows, SNAPSHOT_FIELDS)

            ref_rows = collect_referrers(repo, headers, captured_at)
            append_csv(os.path.join(DATA_DIR, "traffic-referrers.csv"), ref_rows, REFERRER_FIELDS)

            path_rows = collect_paths(repo, headers, captured_at)
            append_csv(os.path.join(DATA_DIR, "traffic-paths.csv"), path_rows, PATH_FIELDS)

            metric_rows = collect_repo_metrics(
                repo,
                detail or {},
                captured_at,
                source=metric_source,
            )
            append_csv(
                os.path.join(DATA_DIR, "repo-metrics.csv"),
                metric_rows,
                REPO_METRIC_FIELDS,
            )

            print(
                f"  OK: {len(vc_rows)} day(s), {len(ref_rows)} referrer(s), "
                f"{len(path_rows)} path(s), {len(metric_rows)} repo metric row(s)"
            )
        except SecondaryRateLimitError as exc:
            errors.append(repo)
            print(f"  Error collecting {repo}: {exc}")
            print("  Stop rerunning this workflow until the reported retry window has passed.")
            _write_step_summary(
                "failed",
                errors=errors,
                secondary_limit=exc,
                skipped_repos=skipped_repos,
            )
            sys.exit(1)
        except RepoUnavailableError as exc:
            skipped_repos.append(repo)
            print(f"  Skipping {repo}: {exc}")
        except requests.HTTPError as exc:
            print(f"  Error collecting {repo}: {exc}")
            errors.append(repo)
        except requests.RequestException as exc:
            print(f"  Error collecting {repo}: {exc}")
            errors.append(repo)

    if errors:
        _write_step_summary("failed", errors=errors, skipped_repos=skipped_repos)
        print(f"\nCollection finished with errors for: {', '.join(errors)}")
        sys.exit(1)

    if skipped_repos:
        _write_step_summary("success-with-skips", skipped_repos=skipped_repos)
        print(
            "Collection complete with unavailable repositories skipped: "
            + ", ".join(skipped_repos)
        )
        return

    _write_step_summary("success")
    print("Collection complete.")


if __name__ == "__main__":
    main()
