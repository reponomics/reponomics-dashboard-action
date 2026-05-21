"""Best-effort GitHub Release update notices for publish output."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import requests


ACTION_REPOSITORY = "reponomics/reponomics-dashboard-action"
RELEASES_API_URL = f"https://api.github.com/repos/{ACTION_REPOSITORY}/releases"
UPDATE_BLOCK_RE = re.compile(
    r"<!--\s*reponomics-update\s+(?P<json>.*?)\s*-->",
    re.DOTALL,
)
MAX_BODY_BYTES = 1_000_000
MAX_NOTICE_BYTES = 4096
MAX_TITLE_CHARS = 80
MAX_SUMMARY_CHARS = 220
REQUEST_TIMEOUT_SECONDS = 5
ALLOWED_UPDATE_KEYS = {
    "title",
    "summary",
    "min_runtime_version",
    "max_runtime_version",
    "action_refs",
    "action_repository",
}


@dataclass(frozen=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str | int, ...] = ()


def parse_semver(value: str) -> SemVer | None:
    """Parse a constrained semver string with an optional leading v."""
    match = re.match(
        r"^\s*v?(?P<major>0|[1-9]\d*)\."
        r"(?P<minor>0|[1-9]\d*)\."
        r"(?P<patch>0|[1-9]\d*)"
        r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?"
        r"(?:\+[0-9A-Za-z.-]+)?\s*$",
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
    """Return -1, 0, or 1 for semver precedence."""
    left_version = parse_semver(left)
    right_version = parse_semver(right)
    if left_version is None or right_version is None:
        raise ValueError("Both values must be valid semantic versions.")
    base_left = (left_version.major, left_version.minor, left_version.patch)
    base_right = (right_version.major, right_version.minor, right_version.patch)
    if base_left != base_right:
        return -1 if base_left < base_right else 1
    return _compare_prerelease(left_version.prerelease, right_version.prerelease)


def parse_update_block(body: str) -> dict[str, Any] | None:
    """Extract and parse the first constrained reponomics update JSON block."""
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        return None
    match = UPDATE_BLOCK_RE.search(body)
    if not match:
        return None
    raw = match.group("json")
    if len(raw.encode("utf-8")) > MAX_NOTICE_BYTES:
        return None
    if not raw.lstrip().startswith("{") or not raw.rstrip().endswith("}"):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def validate_update_block(body: str, *, require_block: bool = True) -> list[str]:
    """Return validation errors for a release-note reponomics-update block."""
    errors: list[str] = []
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        return [f"release body exceeds {MAX_BODY_BYTES} bytes"]

    matches = list(UPDATE_BLOCK_RE.finditer(body))
    if not matches:
        return ["missing reponomics-update block"] if require_block else []
    if len(matches) > 1:
        errors.append("release body must contain exactly one reponomics-update block")

    raw = matches[0].group("json")
    if len(raw.encode("utf-8")) > MAX_NOTICE_BYTES:
        errors.append(f"reponomics-update JSON exceeds {MAX_NOTICE_BYTES} bytes")
    if not raw.lstrip().startswith("{") or not raw.rstrip().endswith("}"):
        errors.append("reponomics-update content must be a single JSON object")
        return errors

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        errors.append(f"reponomics-update JSON is invalid: {exc.msg}")
        return errors
    if not isinstance(parsed, dict):
        errors.append("reponomics-update JSON must decode to an object")
        return errors

    unknown = sorted(set(parsed) - ALLOWED_UPDATE_KEYS)
    if unknown:
        errors.append(f"unsupported reponomics-update key(s): {', '.join(unknown)}")

    title = parsed.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("title is required and must be a non-empty string")
    elif len(_clean_text(title, MAX_TITLE_CHARS + 1)) > MAX_TITLE_CHARS:
        errors.append(f"title must be at most {MAX_TITLE_CHARS} display characters")

    summary = parsed.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        errors.append("summary is required and must be a non-empty string")
    elif len(_clean_text(summary, MAX_SUMMARY_CHARS + 1)) > MAX_SUMMARY_CHARS:
        errors.append(f"summary must be at most {MAX_SUMMARY_CHARS} display characters")

    for key in ("min_runtime_version", "max_runtime_version"):
        value = parsed.get(key)
        if value is not None and (not isinstance(value, str) or parse_semver(value) is None):
            errors.append(f"{key} must be a semantic version string")

    min_runtime = parsed.get("min_runtime_version")
    max_runtime = parsed.get("max_runtime_version")
    if (
        isinstance(min_runtime, str)
        and isinstance(max_runtime, str)
        and parse_semver(min_runtime)
        and parse_semver(max_runtime)
        and compare_semver(min_runtime, max_runtime) > 0
    ):
        errors.append("min_runtime_version must not exceed max_runtime_version")

    action_repository = parsed.get("action_repository")
    if action_repository is not None and (
        not isinstance(action_repository, str)
        or action_repository.strip() != ACTION_REPOSITORY
    ):
        errors.append(f"action_repository must be {ACTION_REPOSITORY} when present")

    refs = parsed.get("action_refs")
    if refs is not None and refs != "*":
        if not isinstance(refs, list) or not refs:
            errors.append("action_refs must be '*' or a non-empty list of action ref strings")
        elif any(not isinstance(ref, str) or not ref.strip() for ref in refs):
            errors.append("action_refs entries must be non-empty strings")

    return errors


def find_update_notice(
    *,
    token: str,
    current_version: str,
    action_ref: str,
    action_repository: str,
) -> dict[str, str] | None:
    """Fetch releases and return sanitized notice metadata, or None on any failure."""
    try:
        releases = _fetch_releases(token)
        current = _current_semver(current_version, action_ref)
        if current is None:
            return None
        for release in releases:
            notice = _notice_from_release(
                release,
                current_version=current_version,
                current=current,
                action_ref=action_ref,
                action_repository=action_repository,
            )
            if notice:
                return notice
    except Exception as exc:
        print(f"Update notice check skipped: {exc}")
    return None


def _parse_prerelease_part(value: str) -> str | int:
    if re.fullmatch(r"0|[1-9]\d*", value):
        return int(value)
    return value


def _compare_prerelease(left: tuple[str | int, ...], right: tuple[str | int, ...]) -> int:
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


def _fetch_releases(token: str) -> list[dict[str, Any]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "reponomics-dashboard-action-update-notice",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(
        RELEASES_API_URL,
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def _current_semver(current_version: str, action_ref: str) -> str | None:
    if action_ref and parse_semver(action_ref):
        return action_ref
    if parse_semver(current_version):
        return current_version
    return None


def _notice_from_release(
    release: dict[str, Any],
    *,
    current_version: str,
    current: str,
    action_ref: str,
    action_repository: str,
) -> dict[str, str] | None:
    tag = str(release.get("tag_name") or "").strip()
    if not tag or parse_semver(tag) is None or compare_semver(tag, current) <= 0:
        return None
    if release.get("draft") or release.get("prerelease"):
        return None

    block = parse_update_block(str(release.get("body") or ""))
    if not block or not _is_compatible(block, current_version, action_ref, action_repository):
        return None

    title = _clean_text(
        block.get("title") or release.get("name") or f"Reponomics {tag}",
        MAX_TITLE_CHARS,
    )
    summary = _clean_text(block.get("summary") or "", MAX_SUMMARY_CHARS)
    url = _release_url(str(release.get("html_url") or ""), tag)
    if not title or not url:
        return None
    return {
        "version": tag,
        "title": title,
        "summary": summary,
        "url": url,
    }


def _is_compatible(
    block: dict[str, Any],
    current_version: str,
    action_ref: str,
    action_repository: str,
) -> bool:
    repo = str(block.get("action_repository") or ACTION_REPOSITORY).strip()
    if repo and repo != ACTION_REPOSITORY:
        return False
    if action_repository and action_repository != ACTION_REPOSITORY:
        return False

    min_runtime = str(block.get("min_runtime_version") or "").strip()
    max_runtime = str(block.get("max_runtime_version") or "").strip()
    if min_runtime and (
        parse_semver(min_runtime) is None
        or compare_semver(current_version, min_runtime) < 0
    ):
        return False
    if max_runtime and (
        parse_semver(max_runtime) is None
        or compare_semver(current_version, max_runtime) > 0
    ):
        return False

    refs = block.get("action_refs")
    if refs is None or refs == "*":
        return True
    if not isinstance(refs, list) or not action_ref:
        return False
    allowed_refs = {str(ref).strip() for ref in refs if isinstance(ref, str)}
    return action_ref in allowed_refs


def _clean_text(value: Any, limit: int) -> str:
    text = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1>",
        "",
        str(value),
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<[^>]*>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = "".join(ch for ch in text if ch.isprintable() and ch not in "<>`[]*_")
    return text[:limit].strip()


def _release_url(value: str, tag: str) -> str:
    expected = f"https://github.com/{ACTION_REPOSITORY}/releases/tag/{tag}"
    if value == expected:
        return value
    return expected
