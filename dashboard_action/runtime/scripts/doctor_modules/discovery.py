"""Dashboard payload discovery for doctor diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from doctor_support import (
    ENCRYPTED_DASHBOARD_SCRIPT_ID,
    PLAINTEXT_DASHBOARD_SCRIPT_ID,
    DashboardDoctorError as _DashboardDoctorError,
    DetectedDashboardMode,
    DoctorStage,
    _json_object,
    _optional_script_content,
    _stage,
)


ENCRYPTED_DASHBOARD_META_NAME = "reponomics-encrypted-dashboard-data"
PLAINTEXT_DASHBOARD_META_NAME = "reponomics-dashboard-data"
EXPORT_MANIFEST_META_NAME = "reponomics-export-manifest"


@dataclass(frozen=True)
class _DashboardJsonSource:
    """A dashboard JSON source found in either an asset reference or script tag."""

    content: str | None
    label: str
    detail: str
    error: str | None

    @property
    def was_found(self) -> bool:
        """Return whether a source marker was found, even if reading it failed."""
        return bool(self.content or self.error)


class _DashboardMetaParser(HTMLParser):
    """Collect dashboard metadata from HTML meta tags."""

    def __init__(self) -> None:
        """Create an empty parser for dashboard meta tag content."""
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record the first content value for each meta tag name."""
        if tag.lower() != "meta":
            return
        attr_map = {
            key.lower(): value for key, value in attrs if key is not None and value is not None
        }
        name = attr_map.get("name")
        content = attr_map.get("content")
        if name and content and name not in self.meta:
            self.meta[name] = content


def _dashboard_meta_content(html: str, name: str) -> str | None:
    """Return the requested dashboard meta tag content, when present."""
    parser = _DashboardMetaParser()
    parser.feed(html)
    return parser.meta.get(name)


def _dashboard_json_asset_path(dashboard_html_path: Path, asset_ref: str) -> Path:
    """Resolve a dashboard JSON asset reference inside the dashboard directory."""
    parsed = urlsplit(asset_ref)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise _DashboardDoctorError(
            "asset", f"dashboard JSON asset {asset_ref!r} must be a plain relative path"
        )
    asset_path = parsed.path
    if (
        asset_path.startswith("/")
        or not asset_path.startswith("assets/")
        or not asset_path.endswith(".json")
    ):
        raise _DashboardDoctorError(
            "asset", f"dashboard JSON asset {asset_ref!r} is not an expected assets/*.json path"
        )

    resolved = (dashboard_html_path.parent / asset_path).resolve()
    dashboard_dir = dashboard_html_path.parent.resolve()
    if not resolved.is_relative_to(dashboard_dir):
        raise _DashboardDoctorError(
            "asset", f"dashboard JSON asset {asset_ref!r} escapes the dashboard directory"
        )
    return resolved


def _optional_dashboard_json_source(
    html: str,
    dashboard_html_path: Path,
    *,
    meta_name: str,
    script_id: str,
) -> tuple[str | None, str, str, str | None]:
    """Return JSON source content plus compatibility tuple metadata."""
    source = _dashboard_json_source(
        html, dashboard_html_path, meta_name=meta_name, script_id=script_id
    )
    return source.content, source.label, source.detail, source.error


def _dashboard_json_source(
    html: str,
    dashboard_html_path: Path,
    *,
    meta_name: str,
    script_id: str,
) -> _DashboardJsonSource:
    """Find a dashboard JSON payload in an asset reference or inline script."""
    asset_ref = _dashboard_meta_content(html, meta_name)
    if asset_ref:
        return _dashboard_json_asset_source(dashboard_html_path, meta_name, asset_ref)

    script_content = _optional_script_content(html, script_id)
    if script_content:
        return _DashboardJsonSource(
            content=script_content,
            label=script_id,
            detail=f"script payload {script_id!r} was found",
            error=None,
        )
    return _DashboardJsonSource(content=None, label="", detail="", error=None)


def _dashboard_json_asset_source(
    dashboard_html_path: Path,
    meta_name: str,
    asset_ref: str,
) -> _DashboardJsonSource:
    """Read a JSON payload from a dashboard asset reference."""
    source_label = f"{meta_name} asset {asset_ref}"
    try:
        asset_path = _dashboard_json_asset_path(dashboard_html_path, asset_ref)
        content = asset_path.read_text(encoding="utf-8")
    except _DashboardDoctorError as exc:
        return _DashboardJsonSource(None, source_label, "", exc.detail)
    except OSError as exc:
        return _DashboardJsonSource(
            None,
            source_label,
            "",
            f"dashboard JSON asset {asset_ref!r} was not readable: {exc}",
        )
    return _DashboardJsonSource(content, source_label, f"JSON asset {asset_ref!r} was found", None)


def _payload_source_stage(
    *,
    encrypted: bool,
    content: str | None,
    detail: str,
    error: str | None,
) -> tuple[DoctorStage, DoctorStage] | None:
    """Build source-detection stages for a payload marker, when one was found."""
    if not (content or error):
        return None
    mode_detail = (
        "encrypted dashboard payload marker was found"
        if encrypted
        else "plaintext dashboard payload marker was found"
    )
    return (
        _stage("detected_dashboard_mode_recorded", "passed", mode_detail),
        _stage("dashboard_script_found", "failed" if error else "passed", error or detail),
    )


def _parse_payload_content(
    mode: DetectedDashboardMode,
    label: str,
    content: str | None,
    stages: list[DoctorStage],
) -> tuple[DetectedDashboardMode, dict[str, Any] | None, list[DoctorStage]]:
    """Parse a discovered payload source and append JSON validity stages."""
    if content is None:
        stages.append(
            _stage("dashboard_script_json_valid", "failed", f"{mode} payload was unavailable")
        )
        return mode, None, stages
    try:
        data = _json_object(content, label)
    except _DashboardDoctorError as exc:
        stages.append(_stage("dashboard_script_json_valid", "failed", exc.detail))
        return mode, None, stages
    stages.append(_stage("dashboard_script_json_valid", "passed", f"{mode} payload is JSON"))
    return mode, data, stages


def _parse_dashboard_payload(
    html: str,
    dashboard_html_path: Path,
) -> tuple[DetectedDashboardMode, dict[str, Any] | None, list[DoctorStage]]:
    """Detect and parse the dashboard payload, preferring encrypted markers."""
    encrypted_source = _dashboard_json_source(
        html,
        dashboard_html_path,
        meta_name=ENCRYPTED_DASHBOARD_META_NAME,
        script_id=ENCRYPTED_DASHBOARD_SCRIPT_ID,
    )
    plaintext_source = _dashboard_json_source(
        html,
        dashboard_html_path,
        meta_name=PLAINTEXT_DASHBOARD_META_NAME,
        script_id=PLAINTEXT_DASHBOARD_SCRIPT_ID,
    )

    if encrypted_source.was_found:
        return _parse_discovered_payload("encrypted", encrypted_source, encrypted=True)
    if plaintext_source.was_found:
        return _parse_discovered_payload("plaintext", plaintext_source, encrypted=False)
    return _missing_dashboard_payload()


def _parse_discovered_payload(
    mode: DetectedDashboardMode,
    source: _DashboardJsonSource,
    *,
    encrypted: bool,
) -> tuple[DetectedDashboardMode, dict[str, Any] | None, list[DoctorStage]]:
    """Build source stages and parse content for one discovered payload marker."""
    encrypted_stages = _payload_source_stage(
        encrypted=encrypted,
        content=source.content,
        detail=source.detail,
        error=source.error,
    )
    stages = list(encrypted_stages or [])
    if source.error:
        return mode, None, stages
    return _parse_payload_content(mode, source.label, source.content, stages)


def _missing_dashboard_payload() -> tuple[
    DetectedDashboardMode, dict[str, Any] | None, list[DoctorStage]
]:
    """Return stages for a dashboard with no known payload marker."""
    return (
        "unknown",
        None,
        [
            _stage(
                "detected_dashboard_mode_recorded",
                "failed",
                "no encrypted or plaintext dashboard payload marker was found",
            ),
            _stage("dashboard_script_found", "failed", "dashboard payload was not found"),
        ],
    )
