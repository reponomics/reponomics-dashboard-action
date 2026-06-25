"""Dashboard payload discovery for doctor diagnostics."""

from __future__ import annotations

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


class _DashboardMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
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
    parser = _DashboardMetaParser()
    parser.feed(html)
    return parser.meta.get(name)


def _dashboard_json_asset_path(dashboard_html_path: Path, asset_ref: str) -> Path:
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
    asset_ref = _dashboard_meta_content(html, meta_name)
    if asset_ref:
        source_label = f"{meta_name} asset {asset_ref}"
        try:
            asset_path = _dashboard_json_asset_path(dashboard_html_path, asset_ref)
            content = asset_path.read_text(encoding="utf-8")
        except _DashboardDoctorError as exc:
            return None, source_label, "", exc.detail
        except OSError as exc:
            return (
                None,
                source_label,
                "",
                f"dashboard JSON asset {asset_ref!r} was not readable: {exc}",
            )
        return content, source_label, f"JSON asset {asset_ref!r} was found", None

    script_content = _optional_script_content(html, script_id)
    if script_content:
        return script_content, script_id, f"script payload {script_id!r} was found", None
    return None, "", "", None


def _payload_source_stage(
    *,
    encrypted: bool,
    content: str | None,
    detail: str,
    error: str | None,
) -> tuple[DoctorStage, DoctorStage] | None:
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
    assert content is not None
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
    encrypted_content, encrypted_label, encrypted_detail, encrypted_error = (
        _optional_dashboard_json_source(
            html,
            dashboard_html_path,
            meta_name=ENCRYPTED_DASHBOARD_META_NAME,
            script_id=ENCRYPTED_DASHBOARD_SCRIPT_ID,
        )
    )
    plaintext_content, plaintext_label, plaintext_detail, plaintext_error = (
        _optional_dashboard_json_source(
            html,
            dashboard_html_path,
            meta_name=PLAINTEXT_DASHBOARD_META_NAME,
            script_id=PLAINTEXT_DASHBOARD_SCRIPT_ID,
        )
    )

    encrypted_stages = _payload_source_stage(
        encrypted=True,
        content=encrypted_content,
        detail=encrypted_detail,
        error=encrypted_error,
    )
    if encrypted_stages is not None:
        stages = list(encrypted_stages)
        if encrypted_error:
            return "encrypted", None, stages
        return _parse_payload_content("encrypted", encrypted_label, encrypted_content, stages)

    plaintext_stages = _payload_source_stage(
        encrypted=False,
        content=plaintext_content,
        detail=plaintext_detail,
        error=plaintext_error,
    )
    if plaintext_stages is not None:
        stages = list(plaintext_stages)
        if plaintext_error:
            return "plaintext", None, stages
        return _parse_payload_content("plaintext", plaintext_label, plaintext_content, stages)

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
