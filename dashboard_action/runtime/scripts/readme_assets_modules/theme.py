"""Shared SVG theme and formatting helpers."""

from __future__ import annotations

import math


LIGHT_SUFFIX = "-light"


class Theme:
    """Color palette for SVG chart rendering."""

    def __init__(
        self,
        *,
        bg: str,
        surface: str,
        border: str,
        border_subtle: str,
        text_primary: str,
        text_secondary: str,
        text_muted: str,
        text_faint: str,
        accent_blue: str,
        accent_purple: str,
        accent_green: str,
        accent_yellow: str,
        accent_red: str,
        accent_cyan: str,
        grid: str,
        heatmap_empty: str,
        heatmap_scale: list[str],
    ) -> None:
        self.bg = bg
        self.surface = surface
        self.border = border
        self.border_subtle = border_subtle
        self.text_primary = text_primary
        self.text_secondary = text_secondary
        self.text_muted = text_muted
        self.text_faint = text_faint
        self.accent_blue = accent_blue
        self.accent_purple = accent_purple
        self.accent_green = accent_green
        self.accent_yellow = accent_yellow
        self.accent_red = accent_red
        self.accent_cyan = accent_cyan
        self.grid = grid
        self.heatmap_empty = heatmap_empty
        self.heatmap_scale = heatmap_scale


DARK = Theme(
    bg="#0a0e14",
    surface="#1c2128",
    border="#30363d",
    border_subtle="rgba(48,54,61,0.6)",
    text_primary="#e6edf3",
    text_secondary="#c9d1d9",
    text_muted="#8b949e",
    text_faint="#6e7681",
    accent_blue="#58a6ff",
    accent_purple="#CC79A7",
    accent_green="#3fb950",
    accent_yellow="#ffa657",
    accent_red="#f85149",
    accent_cyan="#1f6feb",
    grid="#21262d",
    heatmap_empty="#14191f",
    heatmap_scale=["#0e4429", "#006d32", "#26a641", "#39d353"],
)

LIGHT = Theme(
    bg="#ffffff",
    surface="#ffffff",
    border="#d0d7de",
    border_subtle="rgba(208,215,222,0.7)",
    text_primary="#1f2328",
    text_secondary="#1f2328",
    text_muted="#57606a",
    text_faint="#6e7781",
    accent_blue="#0969da",
    accent_purple="#af3aa6",
    accent_green="#1a7f37",
    accent_yellow="#bf6a02",
    accent_red="#cf222e",
    accent_cyan="#0969da",
    grid="#d8dee4",
    heatmap_empty="#ebedf0",
    heatmap_scale=["#9be9a8", "#40c463", "#30a14e", "#216e39"],
)

FONT_STYLE = (
    "  <style>text { font-family: -apple-system, BlinkMacSystemFont, "
    + "'Segoe UI', Roboto, sans-serif; }</style>"
)


def responsive_svg(inner: str, width: int, height: int) -> str:
    """Wrap SVG content in a responsive root element."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        + f'viewBox="0 0 {width} {height}" '
        + f'width="{width}" height="{height}">\n'
    ) + inner + "\n</svg>"


def estimate_text_width(text: str, font_size: int = 11) -> int:
    """Estimate SVG text width with a simple monospace-like heuristic."""
    if not text:
        return 0
    return int(math.ceil(len(text) * font_size * 0.6))


def empty_state_svg(
    message: str, width: int = 420, height: int = 90, theme: Theme = DARK,
) -> str:
    """Return a small empty-state SVG so README assets always exist."""
    inner = f"""  <rect width="100%" height="100%" fill="{theme.bg}" rx="8"/>
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" fill="none" stroke="{theme.border}" rx="8"/>
  <text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle"
        font-size="14" fill="{theme.text_muted}"
        font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">{message}</text>"""
    return responsive_svg(inner, width, height)


def format_compact(n: int | float) -> str:
    """Format large numbers compactly: 110657 -> '110.7k'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return f"{n:,.0f}"


def strip_owner(repo: str) -> str:
    """Strip the owner/ prefix from a repo name for compact display."""
    return repo.split("/", 1)[-1] if "/" in repo else repo
