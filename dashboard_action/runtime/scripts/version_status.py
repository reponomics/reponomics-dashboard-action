"""Reponomics action version status for generated dashboards."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import requests

ACTION_REPOSITORY = "reponomics/reponomics-dashboard-action"
RELEASES_API_URL = f"https://api.github.com/repos/{ACTION_REPOSITORY}/releases"
RELEASES_PAGE_URL = f"https://github.com/{ACTION_REPOSITORY}/releases"
REQUEST_TIMEOUT_SECONDS = 5
MAX_TITLE_CHARS = 80


@dataclass(frozen=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str | int, ...] = ()


def parse_semver(value: str) -> SemVer | None:
    """Parse a constrained SemVer string with an optional leading v."""
    match = re.match(
        r"^\s*v?(?P<major>0|[1-9]\d*)\."
        + r"(?P<minor>0|[1-9]\d*)\."
        + r"(?P<patch>0|[1-9]\d*)"
        + r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?"
        + r"(?:\+[0-9A-Za-z.-]+)?\s*$",
        value,
    )
    if not match:
        return None
    prerelease = tuple(
        _parse_prerelease_part(part)
        for part in (match.group("prerelease") or "").split(".")
        if part
    )
    return SemVer(
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        prerelease,
    )


def compare_semver(left: str, right: str) -> int:
    """Return -1, 0, or 1 for SemVer precedence."""
    left_version = parse_semver(left)
    right_version = parse_semver(right)
    if left_version is None or right_version is None:
        raise ValueError("Both values must be valid semantic versions.")
    base_left = (left_version.major, left_version.minor, left_version.patch)
    base_right = (right_version.major, right_version.minor, right_version.patch)
    if base_left != base_right:
        return -1 if base_left < base_right else 1
    return _compare_prerelease(left_version.prerelease, right_version.prerelease)


def build_status_payload(
    *,
    current_version: str,
    action_ref: str,
    action_repository: str,
    check_latest: bool,
) -> dict[str, Any] | None:
    """Build a local status payload; network/API failures keep publish non-fatal."""
    if action_repository and action_repository != ACTION_REPOSITORY:
        return None
    current = parse_semver(current_version)
    if current is None:
        return None

    latest = None
    if check_latest:
        try:
            latest = latest_stable_release(_fetch_releases())
        except Exception as exc:
            print(f"Version status check skipped: {exc}")

    payload: dict[str, Any] = {
        "current_version": current_version,
        "current_url": _status_url(_release_tag(current_version)),
        "action_ref": action_ref,
        "update_available": False,
        "url": _status_url(latest["tag_name"] if latest else ""),
    }
    if latest:
        tag = latest["tag_name"]
        payload["latest_version"] = tag
        payload["update_available"] = compare_semver(tag, current_version) > 0
        title = _clean_title(latest.get("name") or "")
        if title and title not in {tag, f"Reponomics {tag}"}:
            payload["latest_title"] = title
    return payload


def latest_stable_release(releases: list[dict[str, Any]]) -> dict[str, str] | None:
    """Return the highest stable SemVer release in a GitHub releases payload."""
    candidates: list[dict[str, str]] = []
    for release in releases:
        tag = str(release.get("tag_name") or "").strip()
        parsed = parse_semver(tag)
        if parsed is None or parsed.prerelease:
            continue
        if release.get("draft") or release.get("prerelease"):
            continue
        candidates.append(
            {
                "tag_name": tag,
                "name": str(release.get("name") or "").strip(),
                "html_url": str(release.get("html_url") or "").strip(),
            }
        )
    if not candidates:
        return None
    return max(
        candidates, key=lambda item: parse_semver(item["tag_name"]) or SemVer(0, 0, 0)
    )


def _parse_prerelease_part(value: str) -> str | int:
    if re.fullmatch(r"0|[1-9]\d*", value):
        return int(value)
    return value


def _compare_prerelease(
    left: tuple[str | int, ...], right: tuple[str | int, ...]
) -> int:
    if not left and not right:
        return 0
    if not left:
        return 1
    if not right:
        return -1
    for left_part, right_part in zip(left, right):
        if left_part == right_part:
            continue
        if isinstance(left_part, int) and isinstance(right_part, str):
            return -1
        if isinstance(left_part, str) and isinstance(right_part, int):
            return 1
        if isinstance(left_part, int) and isinstance(right_part, int):
            return -1 if left_part < right_part else 1
        if isinstance(left_part, str) and isinstance(right_part, str):
            return -1 if left_part < right_part else 1
    if len(left) == len(right):
        return 0
    return -1 if len(left) < len(right) else 1


def _fetch_releases() -> list[dict[str, Any]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": "reponomics-dashboard-action-version-status",
    }
    response = requests.get(
        RELEASES_API_URL,
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def _clean_title(value: Any) -> str:
    text = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1>",
        "",
        str(value),
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<[^>]*>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = "".join(ch for ch in text if ch.isprintable() and ch not in "<>`[]*_")
    return text[:MAX_TITLE_CHARS].strip()


def _status_url(tag: str) -> str:
    if tag:
        return f"{RELEASES_PAGE_URL}/tag/{tag}"
    return RELEASES_PAGE_URL


def _release_tag(version: str) -> str:
    clean = version.strip()
    if not clean:
        return ""
    return clean if clean.startswith("v") else f"v{clean}"
