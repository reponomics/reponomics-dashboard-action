"""SVG chart helpers for the generated README."""
# ruff: noqa: F401

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from readme_assets_modules.activity import svg_activity_graph
from readme_assets_modules.badges import svg_version_badge
from readme_assets_modules.bars import svg_bar_chart
from readme_assets_modules.data import build_readme_asset_data
from readme_assets_modules.donut import svg_donut_chart
from readme_assets_modules.hero import svg_hero_stats, trend_arrow
from readme_assets_modules.sparkline import svg_sparkline
from readme_assets_modules.theme import (
    DARK,
    LIGHT,
    LIGHT_SUFFIX,
    Theme,
    empty_state_svg,
    estimate_text_width,
    format_compact,
    responsive_svg,
    strip_owner,
)


README_ASSET_FILENAMES = {
    "hero": "hero-stats.svg",
    "sparkline": "sparkline.svg",
    "bar_chart": "bar-chart.svg",
    "activity": "activity.svg",
    "donut": "donut.svg",
}

VERSION_BADGE_FILENAMES = {
    "current": "action-version-current.svg",
    "latest": "action-version-latest.svg",
}

_responsive_svg = responsive_svg
_estimate_text_width = estimate_text_width
_empty_state_svg = empty_state_svg
_format_compact = format_compact
_trend_arrow = trend_arrow
_strip_owner = strip_owner


def _light_filename(name: str) -> str:
    """Derive the light-variant filename: 'foo.svg' -> 'foo-light.svg'."""
    stem, ext = name.rsplit(".", 1)
    return f"{stem}{LIGHT_SUFFIX}.{ext}"


def _write_svg_pair(
    output_dir: Path,
    key: str,
    generator: Callable[..., str],
    *args: object,
    **kwargs: object,
) -> tuple[Path, Path]:
    """Write dark + light SVG pair and return (dark_path, light_path)."""
    dark_name = README_ASSET_FILENAMES[key]
    light_name = _light_filename(dark_name)

    dark_path = output_dir / dark_name
    light_path = output_dir / light_name

    dark_path.write_text(generator(*args, theme=DARK, **kwargs), encoding="utf-8")
    light_path.write_text(generator(*args, theme=LIGHT, **kwargs), encoding="utf-8")

    return dark_path, light_path


def write_readme_svg_assets(output_dir: Path | str, asset_data: dict) -> dict[str, Path]:
    """Write dark + light README SVG assets to disk.

    Returns a dict mapping asset key -> dark-variant Path.
    Light variants are written alongside with a '-light' suffix.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, Path] = {}
    files["hero"], _ = _write_svg_pair(
        output_dir,
        "hero",
        svg_hero_stats,
        **_hero_kwargs(asset_data),
    )
    files["sparkline"], _ = _write_svg_pair(
        output_dir,
        "sparkline",
        svg_sparkline,
        asset_data["daily_30_views"],
        dates=asset_data["daily_30_dates"],
    )
    files["bar_chart"], _ = _write_svg_pair(
        output_dir,
        "bar_chart",
        svg_bar_chart,
        asset_data["top_repo_labels"],
        asset_data["top_repo_views"],
    )
    files["activity"], _ = _write_svg_pair(
        output_dir,
        "activity",
        svg_activity_graph,
        asset_data["daily_90_dates"],
        asset_data["daily_90_views"],
    )
    files["donut"], _ = _write_svg_pair(
        output_dir,
        "donut",
        svg_donut_chart,
        asset_data["share_repo_labels"],
        asset_data["share_repo_views"],
    )

    return files


def _hero_kwargs(asset_data: dict) -> dict[str, object]:
    totals = asset_data.get("totals") or {}
    return {
        "total_views": totals.get("total_views", 0),
        "total_uniques": totals.get("total_uniques", 0),
        "total_clones": totals.get("total_clones", 0),
        "total_clone_uniques": totals.get("total_clone_uniques", 0),
        "repo_count": len(totals.get("repos", [])),
        "days_tracked": totals.get("days_tracked", 0),
    }


def write_version_badge_assets(
    output_dir: Path | str,
    *,
    current_version: str,
    latest_version: str,
) -> dict[str, Path]:
    """Write static action-version badge SVG assets and return paths by badge key."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    latest_color = "#0969da" if latest_version and latest_version != current_version else "#1a7f37"
    if not latest_version:
        latest_color = "#6e7781"

    badges = {
        "current": ("your version", current_version, "#1a7f37"),
        "latest": ("latest version", latest_version or "unknown", latest_color),
    }
    files: dict[str, Path] = {}
    for key, (label, value, color) in badges.items():
        path = output_dir / VERSION_BADGE_FILENAMES[key]
        path.write_text(svg_version_badge(label, value, color), encoding="utf-8")
        files[key] = path
    return files
