"""Version and managed-docs status markup for dashboard pages."""

from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone

VERSION_STATUS_ENV = "REPONOMICS_VERSION_STATUS_JSON"
MANAGED_DOCS_LINK_ENV = "REPONOMICS_MANAGED_DOCS_DASHBOARD_LINK"
DOCS_SYNC_STATE_ENV = "REPONOMICS_DOCS_SYNC_STATE"
DOCS_ACTION_VERSION_ENV = "REPONOMICS_DOCS_ACTION_VERSION"
DOCS_UPDATED_AT_ENV = "REPONOMICS_DOCS_UPDATED_AT"
DOCS_STATE_LABELS = {
    "disabled": "sync disabled",
    "manifest_inconsistent": "needs manual review",
    "permission_missing": "workflow cannot update docs",
    "push_race": "update not pushed",
    "stale": "version is out of sync with this repository's action version",
}


def load_version_status():
    raw = os.environ.get(VERSION_STATUS_ENV, "")
    if not raw:
        return None
    try:
        status = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(status, dict):
        return None
    current_version = str(status.get("current_version") or "").strip()
    current_url = str(status.get("current_url") or "").strip()
    latest_version = str(status.get("latest_version") or "").strip()
    url = str(status.get("url") or "").strip()
    update_available = bool(status.get("update_available"))
    if not current_version or not url:
        return None
    return {
        "current_version": current_version,
        "current_url": current_url or url,
        "latest_version": latest_version,
        "update_available": update_available,
        "url": url,
    }


def display_version(version):
    value = str(version or "").strip()
    if not value:
        return ""
    return value if value.startswith("v") else f"v{value}"


def format_docs_timestamp(value):
    if not value:
        return ""
    try:
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return value
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def render_version_badges():
    status = load_version_status()
    if not status:
        return ""
    current_display = display_version(status["current_version"])
    latest_display = display_version(status["latest_version"])
    latest_state = ""
    if latest_display and latest_display != current_display:
        latest_state = " different"
    if not latest_display:
        latest_state = " unknown"
    latest_value = latest_display or "unknown"
    current_href = html.escape(status["current_url"], quote=True)
    latest_href = html.escape(status["url"], quote=True)
    updates_href = html.escape(
        os.environ.get(MANAGED_DOCS_LINK_ENV, "").strip() or status["url"], quote=True
    )
    current_value = html.escape(current_display)
    latest_value = html.escape(latest_value)
    docs_status = render_docs_sync_status()
    return (
        '        <div class="action-version-badges" role="group" '
        + 'aria-label="Reponomics action version status">\n'
        + f'          <a class="action-version-badge current" href="{current_href}">'
        + '<span class="badge-label">your version</span>'
        + f'<span class="badge-value">{current_value}</span></a>\n'
        + f'          <a class="action-version-badge latest{latest_state}" href="{latest_href}">'
        + '<span class="badge-label">latest version</span>'
        + f'<span class="badge-value">{latest_value}</span></a>\n'
        + f'          <a class="action-version-link" href="{updates_href}">'
        + 'View latest updates</a>\n'
        + docs_status
        + "        </div>"
    )


def render_docs_sync_status():
    state = os.environ.get(DOCS_SYNC_STATE_ENV, "").strip()
    if not state or state in {"unchanged", "written"}:
        return ""
    label = html.escape(DOCS_STATE_LABELS.get(state, state.replace("_", " ")))
    detail = render_docs_status_detail()
    return (
        '          <div class="managed-docs-status">Local docs: '
        + f"<strong>{label}</strong>.{detail}</div>\n"
    )


def render_docs_status_detail():
    parts = []
    docs_action_version = display_version(
        os.environ.get(DOCS_ACTION_VERSION_ENV, "").strip()
    )
    status = load_version_status()
    current_action_version = (
        display_version(status["current_version"]) if status else ""
    )
    docs_updated_at = format_docs_timestamp(
        os.environ.get(DOCS_UPDATED_AT_ENV, "").strip()
    )
    if docs_action_version:
        parts.append(f"Docs version: {docs_action_version}.")
    if current_action_version:
        parts.append(f"Action version: {current_action_version}.")
    if docs_updated_at:
        parts.append(f"Last docs update: {docs_updated_at}.")
    if not parts:
        return ""
    return " " + html.escape(" ".join(parts))
