"""GitHub HTTP retry, rate-limit, and response helpers."""

from __future__ import annotations

import math
import random
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

from collect_modules.constants import (
    MAX_RETRIES,
    NOT_FOUND_RETRIES,
    RETRY_BACKOFF,
    SECONDARY_LIMIT_FALLBACK_SECONDS,
)
from collect_modules.types import Headers


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
            + f"{url}. Do not retry until after "
            + f"{retry_at_utc.strftime('%Y-%m-%d %H:%M:%S UTC')} "
            + f"({retry_after_seconds}s, source: {source})."
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
            + f"{attempts} attempt(s): {url}. The repo may have been deleted, "
            + "renamed, transferred, or may no longer be accessible."
        )
        super().__init__(message, response=response)


def response_text_lower(resp: requests.Response) -> str:
    text = getattr(resp, "text", "") or ""
    return text.lower()


def is_secondary_rate_limit(resp: requests.Response) -> bool:
    """Detect GitHub secondary-rate-limit responses."""
    return resp.status_code in {403, 429} and "secondary" in response_text_lower(resp)


def parse_retry_after_seconds(value: str | None) -> int | None:
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


def secondary_retry_window(resp: requests.Response) -> tuple[int, datetime, str]:
    """Return how long to wait before retrying a secondary-limited request."""
    retry_after_seconds = parse_retry_after_seconds(resp.headers.get("Retry-After"))
    source = "Retry-After"
    if retry_after_seconds is None:
        retry_after_seconds, source = _reset_header_retry_seconds(resp)

    if retry_after_seconds is None:
        retry_after_seconds = SECONDARY_LIMIT_FALLBACK_SECONDS
        source = "default-minimum"

    retry_at_utc = datetime.now(timezone.utc) + timedelta(seconds=retry_after_seconds)
    return retry_after_seconds, retry_at_utc, source


def _reset_header_retry_seconds(resp: requests.Response) -> tuple[int | None, str]:
    reset_header = resp.headers.get("X-RateLimit-Reset")
    if not reset_header:
        return None, "Retry-After"
    try:
        reset_epoch = int(reset_header)
    except ValueError:
        return None, "Retry-After"
    return max(0, reset_epoch - int(datetime.now(timezone.utc).timestamp())), "X-RateLimit-Reset"


def is_retryable_throttle(resp: requests.Response) -> bool:
    """Return whether a non-secondary 403/429 looks transient."""
    text = response_text_lower(resp)
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


def retry_delay_with_jitter(attempt: int) -> float:
    """Compute exponential backoff with jitter for retryable throttling/errors."""
    base = RETRY_BACKOFF * (2 ** (attempt - 1))
    return base + random.uniform(0, base / 2)


def fetch_json(
    url: str,
    headers: Headers,
    allow_not_found: bool = False,
    *,
    perform_get: Callable[[str, Headers, int], requests.Response],
    record_network_warning: Callable[[str, int, requests.RequestException], None],
    sleep: Callable[[float], None] = time.sleep,
    retry_delay: Callable[[int], float] = retry_delay_with_jitter,
) -> object:
    """Fetch JSON from the GitHub API with pacing and targeted retries."""
    last_exc: requests.RequestException | None = None
    resp: requests.Response | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = perform_get(url, headers, 30)
        except requests.RequestException as exc:
            last_exc = exc
            record_network_warning(url, attempt, exc)
            if attempt < MAX_RETRIES:
                _sleep_after_network_error(attempt, exc, sleep, retry_delay)
                continue
            break

        action = _response_action(url, resp, attempt, allow_not_found)
        if action == "return":
            return resp.json()
        if action == "retry_not_found":
            _sleep_after_not_found(url, attempt, sleep, retry_delay)
            continue
        if action == "retry":
            _sleep_after_response(resp, attempt, sleep, retry_delay)
            continue

    if last_exc:
        raise last_exc
    raise requests.HTTPError(f"Failed after {MAX_RETRIES} retries: {url}", response=resp)


def fetch_json_with_status(
    url: str,
    headers: Headers,
    allow_not_found: bool = False,
    *,
    perform_get: Callable[[str, Headers, int], requests.Response],
    record_network_warning: Callable[[str, int, requests.RequestException], None],
    accepted_statuses: set[int] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    retry_delay: Callable[[int], float] = retry_delay_with_jitter,
) -> tuple[int, object | None, dict[str, str]]:
    """Fetch JSON and preserve HTTP status for endpoints with meaningful non-200s."""
    accepted_statuses = accepted_statuses or set()
    last_exc: requests.RequestException | None = None
    resp: requests.Response | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = perform_get(url, headers, 30)
        except requests.RequestException as exc:
            last_exc = exc
            record_network_warning(url, attempt, exc)
            if attempt < MAX_RETRIES:
                _sleep_after_network_error(attempt, exc, sleep, retry_delay)
                continue
            break

        if resp.status_code in accepted_statuses and not is_secondary_rate_limit(resp):
            return resp.status_code, _response_json_or_none(resp), dict(resp.headers)

        action = _response_action(url, resp, attempt, allow_not_found)
        if action == "return":
            return resp.status_code, _response_json_or_none(resp), dict(resp.headers)
        if action == "retry_not_found":
            _sleep_after_not_found(url, attempt, sleep, retry_delay)
            continue
        if action == "retry":
            _sleep_after_response(resp, attempt, sleep, retry_delay)
            continue

    if last_exc:
        raise last_exc
    raise requests.HTTPError(f"Failed after {MAX_RETRIES} retries: {url}", response=resp)


def _response_json_or_none(resp: requests.Response) -> object | None:
    if not (getattr(resp, "content", b"") or getattr(resp, "text", "")):
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def _response_action(
    url: str,
    resp: requests.Response,
    attempt: int,
    allow_not_found: bool,
) -> str:
    if is_secondary_rate_limit(resp):
        retry_after_seconds, retry_at_utc, source = secondary_retry_window(resp)
        raise SecondaryRateLimitError(url, resp, retry_after_seconds, retry_at_utc, source)
    if _should_retry_response(resp, attempt):
        return "retry"
    if resp.status_code == 404:
        return _not_found_action(url, resp, attempt, allow_not_found)
    resp.raise_for_status()
    return "return"


def _should_retry_response(resp: requests.Response, attempt: int) -> bool:
    if attempt >= MAX_RETRIES:
        return False
    return is_retryable_throttle(resp) or resp.status_code >= 500


def _not_found_action(
    url: str,
    resp: requests.Response,
    attempt: int,
    allow_not_found: bool,
) -> str:
    if allow_not_found and attempt <= NOT_FOUND_RETRIES:
        return "retry_not_found"
    if allow_not_found:
        raise RepoUnavailableError(url, resp, attempt)
    print(f"  Warning: {url} returned 404 — repo may not exist or token lacks access.")
    raise requests.HTTPError(f"404 Not Found: {url}", response=resp)


def _sleep_after_network_error(
    attempt: int,
    exc: requests.RequestException,
    sleep: Callable[[float], None],
    retry_delay: Callable[[int], float],
) -> None:
    wait = retry_delay(attempt)
    print(
        f"  Retry {attempt}/{MAX_RETRIES} after network error: {exc} "
        + f"(sleeping {wait:.2f}s)"
    )
    sleep(wait)


def _sleep_after_response(
    resp: requests.Response,
    attempt: int,
    sleep: Callable[[float], None],
    retry_delay: Callable[[int], float],
) -> None:
    wait = retry_delay(attempt)
    if is_retryable_throttle(resp):
        print(f"  Transient throttle {resp.status_code} — retrying in {wait:.2f}s...")
    else:
        print(f"  Server error {resp.status_code} — retrying in {wait:.2f}s...")
    sleep(wait)


def _sleep_after_not_found(
    url: str,
    attempt: int,
    sleep: Callable[[float], None],
    retry_delay: Callable[[int], float],
) -> None:
    wait = retry_delay(attempt)
    print(
        f"  404 for {url} — retrying in {wait:.2f}s to "
        + "confirm the repo is unavailable..."
    )
    sleep(wait)
