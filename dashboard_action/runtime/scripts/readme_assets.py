"""SVG chart helpers for the generated README."""

from __future__ import annotations

import math
import html
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence


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

# Light-theme variants use this suffix
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
    # Aligned with the HTML dashboard's dark tokens
    # (--bg, --bg-card, --border, --text, --text-muted, --c-views, etc.)
    bg="#0a0e14",
    surface="#1c2128",
    border="#30363d",
    border_subtle="rgba(48,54,61,0.6)",
    text_primary="#e6edf3",
    text_secondary="#c9d1d9",
    text_muted="#8b949e",
    text_faint="#6e7681",
    accent_blue="#58a6ff",      # views
    accent_purple="#CC79A7",    # clones
    accent_green="#3fb950",     # visitors / positives
    accent_yellow="#ffa657",    # cloners (warmer than #d29922 for the new palette)
    accent_red="#f85149",
    accent_cyan="#1f6feb",      # accent / brand
    grid="#21262d",
    heatmap_empty="#14191f",
    # Keep the GitHub contribution-graph green palette — this is one of the
    # few visual assets that already reads as "GitHub-native".
    heatmap_scale=["#0e4429", "#006d32", "#26a641", "#39d353"],
)

LIGHT = Theme(
    # Aligned with the HTML dashboard's [data-theme="light"] tokens.
    bg="#ffffff",
    surface="#ffffff",
    border="#d0d7de",
    border_subtle="rgba(208,215,222,0.7)",
    text_primary="#1f2328",
    text_secondary="#1f2328",
    text_muted="#57606a",
    text_faint="#6e7781",
    accent_blue="#0969da",      # views
    accent_purple="#af3aa6",    # clones
    accent_green="#1a7f37",     # visitors / positives
    accent_yellow="#bf6a02",    # cloners
    accent_red="#cf222e",
    accent_cyan="#0969da",      # accent / brand
    grid="#d8dee4",
    heatmap_empty="#ebedf0",
    heatmap_scale=["#9be9a8", "#40c463", "#30a14e", "#216e39"],
)


def _responsive_svg(inner: str, width: int, height: int) -> str:
    """Wrap SVG content in a responsive root element.

    Uses viewBox so the SVG scales to its container width on mobile.
    GitHub strips inline styles on SVG files rendered via ![](path.svg),
    so we rely on viewBox + width/height for sizing. The viewBox lets
    browsers scale the image proportionally when the container is
    narrower than the designed width.
    """
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" ' +
        f'viewBox="0 0 {width} {height}" ' +
        f'width="{width}" height="{height}">\n'
    ) + inner + "\n</svg>"


def svg_version_badge(label: str, value: str, color: str, height: int = 22) -> str:
    """Generate a small static SVG badge for GitHub README rendering."""
    label = label.strip()
    value = value.strip()
    label_width = max(72, _estimate_text_width(label, 11) + 18)
    value_width = max(56, _estimate_text_width(value, 11) + 18)
    width = label_width + value_width
    label_text_x = label_width // 2
    value_text_x = label_width + (value_width // 2)
    safe_label = html.escape(label)
    safe_value = html.escape(value)
    safe_color = html.escape(color, quote=True)
    inner = f"""  <rect width="{width}" height="{height}" fill="#555"/>
  <rect x="{label_width}" width="{value_width}" height="{height}" fill="{safe_color}"/>
  <rect x="{label_width}" width="4" height="{height}" fill="{safe_color}"/>
  <text x="{label_text_x}" y="15" text-anchor="middle" fill="#fff"
        font-size="11" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">{safe_label}</text>
  <text x="{value_text_x}" y="15" text-anchor="middle" fill="#fff"
        font-size="11" font-weight="600" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">{safe_value}</text>"""
    return _responsive_svg(inner, width, height)


def _estimate_text_width(text: str, font_size: int = 11) -> int:
    """Estimate SVG text width with a simple monospace-like heuristic."""
    if not text:
        return 0
    return int(math.ceil(len(text) * font_size * 0.6))


def _empty_state_svg(
    message: str, width: int = 420, height: int = 90, theme: Theme = DARK,
) -> str:
    """Return a small empty-state SVG so README assets always exist."""
    t = theme
    inner = f"""  <rect width="100%" height="100%" fill="{t.bg}" rx="8"/>
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" fill="none" stroke="{t.border}" rx="8"/>
  <text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle"
        font-size="14" fill="{t.text_muted}"
        font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">{message}</text>"""
    return _responsive_svg(inner, width, height)


def _format_compact(n: int | float) -> str:
    """Format large numbers compactly: 110657 -> '110.7k'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1_000:.1f}k"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return f"{n:,.0f}"


def _trend_arrow(
    current: int | float, previous: int | float, theme: Theme = DARK,
) -> tuple[str, str]:
    """Return (arrow_char, color) for a trend indicator."""
    if previous <= 0:
        return ("", theme.text_muted)
    pct = (current - previous) / previous
    if pct > 0.05:
        return (f"+{pct:.0%}", theme.accent_green)
    if pct < -0.05:
        return (f"{pct:.0%}", theme.accent_red)
    return ("~0%", theme.text_muted)


def svg_hero_stats(
    total_views: int,
    total_uniques: int,
    total_clones: int,
    total_clone_uniques: int,
    repo_count: int,
    days_tracked: int,
    trend_views: int | None = None,
    prev_views: int | None = None,
    width: int = 520,
    theme: Theme = DARK,
) -> str:
    """Generate an SVG hero stat banner with 4 key metrics."""
    t = theme
    if total_views == 0 and total_clones == 0:
        return _empty_state_svg("No traffic data yet.", width=width, height=100, theme=t)

    height = 120
    col_w = width // 4
    metrics = [
        ("VIEWS", total_views, t.accent_blue),
        ("VISITORS", total_uniques, t.accent_green),
        ("CLONES", total_clones, t.accent_purple),
        ("CLONERS", total_clone_uniques, t.accent_yellow),
    ]

    # Trend arrow for views (optional)
    trend_svg = ""
    if trend_views is not None and prev_views is not None and prev_views > 0:
        arrow_text, arrow_color = _trend_arrow(trend_views, prev_views, theme=t)
        if arrow_text:
            trend_svg = (
                f'<text x="{col_w // 2 + 48}" y="58" font-size="11" ' +
                f'fill="{arrow_color}" font-weight="600">{arrow_text}</text>'
            )

    metric_blocks = []
    for i, (label, value, color) in enumerate(metrics):
        cx = col_w * i + col_w // 2
        bar_w = 32
        metric_blocks.append(
            f'<rect x="{cx - bar_w // 2}" y="16" width="{bar_w}" height="3" ' +
            f'fill="{color}" rx="1.5" opacity="0.7"/>'
        )
        delay = f"{i * 0.12:.2f}s"
        metric_blocks.append(
            f'<text x="{cx}" y="56" text-anchor="middle" ' +
            f'font-size="26" font-weight="700" fill="{color}" ' +
            f'letter-spacing="-0.03em" opacity="0">{_format_compact(value)}' +
            '<animate attributeName="opacity" values="0;1;1;0" ' +
            'keyTimes="0;0.03;0.92;1" dur="12s" ' +
            f'begin="{delay}" repeatCount="indefinite"/></text>'
        )
        metric_blocks.append(
            f'<text x="{cx}" y="76" text-anchor="middle" ' +
            f'font-size="10" fill="{t.text_muted}" font-weight="600" ' +
            f'letter-spacing="0.08em">{label}</text>'
        )

    footer_text = f"{repo_count} repos \u00b7 {days_tracked} days"
    footer_svg = (
        f'<text x="{width // 2}" y="104" text-anchor="middle" ' +
        f'font-size="11" fill="{t.text_faint}">{footer_text}</text>'
    )

    dots = []
    for i in range(1, 4):
        dx = col_w * i
        dots.append(f'<circle cx="{dx}" cy="50" r="1.5" fill="{t.border}"/>')

    inner = f"""  <style>text {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}</style>
  <rect width="100%" height="100%" fill="{t.bg}" rx="10"/>
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" fill="none" stroke="{t.border}" rx="10" stroke-opacity="0.6"/>
  {''.join(metric_blocks)}
  {''.join(dots)}
  {trend_svg}
  {footer_svg}"""
    return _responsive_svg(inner, width, height)


def svg_sparkline(
    values: Sequence[int | float],
    dates: Sequence[str] | None = None,
    width: int = 520,
    height: int = 100,
    stroke_color: str | None = None,
    theme: Theme = DARK,
) -> str:
    """Generate an SVG sparkline with peak annotation and subtle grid."""
    t = theme
    stroke_color = stroke_color or t.accent_blue
    if not values or len(values) < 2:
        return _empty_state_svg("Not enough data for a trend chart.", width=width, height=height, theme=t)

    vals = list(values)
    min_val = min(vals)
    max_val = max(vals)
    value_range = max_val - min_val if max_val != min_val else 1

    top_pad = 22
    bottom_pad = 20
    left_pad = 8
    right_pad = 8
    usable_width = width - left_pad - right_pad
    usable_height = height - top_pad - bottom_pad

    points = []
    for i, value in enumerate(vals):
        x = left_pad + (i / (len(vals) - 1)) * usable_width
        y = top_pad + usable_height - ((value - min_val) / value_range) * usable_height
        points.append((x, y, value))

    polyline_points = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
    fill_points = (
        f"{left_pad},{height - bottom_pad} {polyline_points} " +
        f"{width - right_pad},{height - bottom_pad}"
    )

    # Gradient fill
    gradient_id = "sparkFill"

    # Subtle horizontal grid lines (25%, 50%, 75%)
    grid_lines = []
    for frac in (0.25, 0.5, 0.75):
        gy = top_pad + usable_height * (1 - frac)
        grid_lines.append(
            f'<line x1="{left_pad}" y1="{gy:.1f}" x2="{width - right_pad}" ' +
            f'y2="{gy:.1f}" stroke="{t.grid}" stroke-width="1"/>'
        )

    # Peak annotation
    peak_idx = vals.index(max_val)
    px, py, pv = points[peak_idx]
    peak_label = _format_compact(int(pv))
    peak_svg = (
        f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" fill="{stroke_color}" opacity="0">' +
        '<animate attributeName="opacity" values="0;0;1;1;0" ' +
        'keyTimes="0;0.08;0.1;0.92;1" dur="12s" repeatCount="indefinite"/></circle>' +
        f'<text x="{px:.1f}" y="{py - 8:.1f}" text-anchor="middle" ' +
        f'font-size="10" fill="{t.text_primary}" font-weight="600" opacity="0">{peak_label}' +
        '<animate attributeName="opacity" values="0;0;1;1;0" ' +
        'keyTimes="0;0.09;0.11;0.92;1" dur="12s" repeatCount="indefinite"/></text>'
    )

    # Latest value annotation (right edge)
    last_x, last_y, last_v = points[-1]
    last_label = _format_compact(int(last_v))
    last_svg = (
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2.5" fill="{t.text_muted}"/>' +
        f'<text x="{last_x - 6:.1f}" y="{last_y - 7:.1f}" text-anchor="end" ' +
        f'font-size="9" fill="{t.text_muted}">{last_label}</text>'
    )

    # Date labels (first and last)
    date_labels = ""
    if dates and len(dates) >= 2:
        date_labels = (
            f'<text x="{left_pad}" y="{height - 4}" font-size="9" ' +
            f'fill="{t.text_faint}">{dates[0]}</text>' +
            f'<text x="{width - right_pad}" y="{height - 4}" text-anchor="end" ' +
            f'font-size="9" fill="{t.text_faint}">{dates[-1]}</text>'
        )

    inner = f"""  <style>text {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}</style>
  <defs>
    <linearGradient id="{gradient_id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{stroke_color}" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="{stroke_color}" stop-opacity="0.02"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="{t.bg}" rx="8"/>
  {''.join(grid_lines)}
  <polygon points="{fill_points}" fill="url(#{gradient_id})" />
  <polyline points="{polyline_points}" fill="none" stroke="{stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="2000" stroke-dashoffset="2000"><animate attributeName="stroke-dashoffset" values="2000;0;0;2000" keyTimes="0;0.1;0.92;1" dur="12s" repeatCount="indefinite" calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1;0.4 0 0.2 1"/></polyline>
  {peak_svg}
  {last_svg if peak_idx != len(vals) - 1 else ""}
  {date_labels}"""
    return _responsive_svg(inner, width, height)


def _strip_owner(repo: str) -> str:
    """Strip the owner/ prefix from a repo name for compact display."""
    return repo.split("/", 1)[-1] if "/" in repo else repo


def svg_bar_chart(
    labels: Sequence[str],
    values: Sequence[int | float],
    width: int = 520,
    bar_color: str | None = None,
    theme: Theme = DARK,
) -> str:
    """Generate an SVG horizontal bar chart with compact labels and value context."""
    t = theme
    bar_color = bar_color or t.accent_blue
    if not values:
        return _empty_state_svg("No repository totals yet.", width=width, height=260, theme=t)

    total = sum(values) or 1
    max_val = max(values) if values else 1
    short_labels = [_strip_owner(lbl) for lbl in labels]

    bar_height = 22
    spacing = 8
    label_font = 11
    value_font = 10
    top_pad = 8
    label_width = _estimate_text_width(
        max(short_labels, key=len, default=""), label_font
    ) + 16
    value_col = 70  # space for "108.5k (98%)"
    bar_area_width = max(140, width - label_width - value_col - 20)
    total_width = label_width + bar_area_width + value_col + 20

    bars = []
    for i, (label, value) in enumerate(zip(short_labels, values)):
        y = top_pad + i * (bar_height + spacing)
        bar_w = (value / max_val) * bar_area_width if max_val else 0
        # Minimum visible bar width for non-zero values
        if value > 0 and bar_w < 4:
            bar_w = 4
        pct = value / total * 100
        value_str = _format_compact(int(value))
        pct_str = f"{pct:.0f}%" if pct >= 1 else "&lt;1%"

        # Subtle track behind bar
        bars.append(
            f'<rect x="{label_width}" y="{y}" width="{bar_area_width}" ' +
            f'height="{bar_height}" fill="{t.surface}" rx="4"/>'
        )
        # Actual bar
        bars.append(
            f'<rect x="{label_width}" y="{y}" width="{bar_w:.1f}" ' +
            f'height="{bar_height}" fill="{bar_color}" rx="4" opacity="0.85"/>'
        )
        # Label
        bars.append(
            f'<text x="{label_width - 8}" y="{y + bar_height // 2 + 4}" ' +
            f'text-anchor="end" font-size="{label_font}" fill="{t.text_secondary}">{label}</text>'
        )
        # Value + percentage
        bars.append(
            f'<text x="{label_width + bar_area_width + 8}" ' +
            f'y="{y + bar_height // 2 + 4}" font-size="{value_font}" fill="{t.text_primary}">' +
            f'{value_str} <tspan fill="{t.text_faint}">{pct_str}</tspan></text>'
        )

    total_height = top_pad + len(values) * (bar_height + spacing) + 4
    inner = f"""  <style>text {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}</style>
  <rect width="100%" height="100%" fill="{t.bg}" rx="8"/>
  {''.join(bars)}"""
    return _responsive_svg(inner, total_width, total_height)


def svg_activity_graph(
    dates: Sequence[str],
    values: Sequence[int],
    cell_size: int = 11,
    gap: int = 3,
    theme: Theme = DARK,
) -> str:
    """Generate a GitHub-style activity heatmap with month and day labels."""
    t = theme
    if not values or not dates:
        return _empty_state_svg("No 90-day activity yet.", width=520, height=120, theme=t)

    pairs = []
    for raw_date, value in zip(dates, values):
        try:
            parsed = date.fromisoformat(raw_date)
        except ValueError:
            continue
        pairs.append((parsed, value))

    if not pairs:
        return _empty_state_svg("No 90-day activity yet.", width=520, height=120)

    pairs.sort(key=lambda item: item[0])
    values_by_date = {parsed: value for parsed, value in pairs}
    start_date = pairs[0][0]
    end_date = pairs[-1][0]
    days_to_sunday = (start_date.weekday() + 1) % 7
    start_sunday = start_date - timedelta(days=days_to_sunday)
    total_days = (end_date - start_sunday).days + 1
    num_weeks = math.ceil(total_days / 7)

    max_val = max(values) if values else 1
    hm_colors = [t.heatmap_empty] + t.heatmap_scale

    def level_color(value: int) -> str:
        if value <= 0 or max_val <= 0:
            return hm_colors[0]
        ratio = value / max_val
        if ratio <= 0.25:
            return hm_colors[1]
        if ratio <= 0.5:
            return hm_colors[2]
        if ratio <= 0.75:
            return hm_colors[3]
        return hm_colors[4]

    # Layout offsets for labels
    day_label_width = 28
    month_label_height = 14
    grid_x = day_label_width + 4
    grid_y = month_label_height + 4

    # Day-of-week labels (Mon, Wed, Fri)
    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    day_labels = []
    for d_idx in (1, 3, 5):  # Mon, Wed, Fri
        dy = grid_y + d_idx * (cell_size + gap) + cell_size // 2 + 3
        day_labels.append(
            f'<text x="{day_label_width}" y="{dy}" text-anchor="end" ' +
            f'font-size="9" fill="{t.text_faint}">{day_names[d_idx]}</text>'
        )

    # Month labels along the top
    month_labels = []
    seen_months: set[tuple[int, int]] = set()
    for week_idx in range(num_weeks):
        # First day of this week column
        week_start = start_sunday + timedelta(days=week_idx * 7)
        month_key = (week_start.year, week_start.month)
        if month_key not in seen_months:
            seen_months.add(month_key)
            mx = grid_x + week_idx * (cell_size + gap)
            month_name = week_start.strftime("%b")
            month_labels.append(
                f'<text x="{mx}" y="{month_label_height}" ' +
                f'font-size="9" fill="{t.text_faint}">{month_name}</text>'
            )

    cells = []
    for offset in range(total_days):
        current_date = start_sunday + timedelta(days=offset)
        value = values_by_date.get(current_date, 0)
        week = offset // 7
        day = offset % 7
        x = grid_x + week * (cell_size + gap)
        y = grid_y + day * (cell_size + gap)
        color = level_color(value)
        # Staggered fade-in, loops every 14s with fade-out
        anim_offset = offset * 0.012
        # Express as fraction of 14s cycle
        fade_in = f"{anim_offset / 14:.3f}"
        fade_in_end = f"{min((anim_offset + 0.3) / 14, 0.15):.3f}"
        cells.append(
            f'<rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" ' +
            f'fill="{color}" rx="2" opacity="0">' +
            '<animate attributeName="opacity" values="0;0;1;1;0" ' +
            f'keyTimes="0;{fade_in};{fade_in_end};0.92;1" dur="14s" ' +
            'repeatCount="indefinite"/>' +
            f"<title>{current_date.isoformat()}: {value:,} views</title></rect>"
        )

    svg_width = grid_x + num_weeks * (cell_size + gap) + 8
    svg_height = grid_y + 7 * (cell_size + gap) + 8

    inner = f"""  <style>text {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}</style>
  <rect width="100%" height="100%" fill="{t.bg}" rx="8"/>
  {''.join(month_labels)}
  {''.join(day_labels)}
  {''.join(cells)}"""
    return _responsive_svg(inner, svg_width, svg_height)


def svg_donut_chart(
    labels: Sequence[str],
    values: Sequence[int | float],
    size: int = 180,
    colors: Sequence[str] | None = None,
    theme: Theme = DARK,
) -> str:
    """Generate an SVG donut chart with percentage labels and compact legend."""
    t = theme
    if not values:
        return _empty_state_svg("No repository share data yet.", width=520, height=120, theme=t)

    palette = list(colors or [
        t.accent_blue, t.accent_green, t.accent_purple, t.accent_yellow,
        t.accent_red, t.accent_cyan,
        # Extended palette for 7+ slices — slightly shifted variants
        t.accent_blue, t.accent_green, t.accent_purple, t.accent_yellow,
    ])

    total = sum(values)
    if total <= 0:
        return _empty_state_svg("No repository share data yet.", width=520, height=120)

    short_labels = [_strip_owner(lbl) for lbl in labels]
    center = size // 2
    radius = size // 2 - 12
    inner_radius = radius * 0.55
    legend_x = size + 16
    legend_row_height = 22
    legend_font = 11
    legend_width = (
        _estimate_text_width(max(short_labels, key=len, default=""), legend_font)
        + 70  # room for "99.1%  name"
    )

    paths = []
    legend_items = []
    start_angle = -90.0
    for i, (label, value) in enumerate(zip(short_labels, values)):
        if value < 0:
            continue
        pct = value / total if total else 0
        angle = pct * 360
        end_angle = start_angle + angle
        start_rad = math.radians(start_angle)
        end_rad = math.radians(end_angle)

        x1 = center + radius * math.cos(start_rad)
        y1 = center + radius * math.sin(start_rad)
        x2 = center + radius * math.cos(end_rad)
        y2 = center + radius * math.sin(end_rad)
        x3 = center + inner_radius * math.cos(end_rad)
        y3 = center + inner_radius * math.sin(end_rad)
        x4 = center + inner_radius * math.cos(start_rad)
        y4 = center + inner_radius * math.sin(start_rad)
        large_arc = 1 if angle > 180 else 0
        color = palette[i % len(palette)]
        path = (
            f"M {x1:.1f} {y1:.1f} " +
            f"A {radius} {radius} 0 {large_arc} 1 {x2:.1f} {y2:.1f} " +
            f"L {x3:.1f} {y3:.1f} " +
            f"A {inner_radius} {inner_radius} 0 {large_arc} 0 {x4:.1f} {y4:.1f} Z"
        )
        slice_delay = i * 0.08 / 12  # fraction of 12s cycle
        paths.append(
            f'<path d="{path}" fill="{color}" opacity="0">' +
            '<animate attributeName="opacity" values="0;0.9;0.9;0" ' +
            f'keyTimes="0;{slice_delay + 0.03:.3f};0.92;1" dur="12s" ' +
            'repeatCount="indefinite"/>' +
            f"<title>{labels[i]}: {value:,.0f} ({pct:.1%})</title></path>"
        )
        # Legend row: color dot + percentage + name
        ly = i * legend_row_height + 10
        pct_str = f"{pct:.1%}" if pct >= 0.01 else "&lt;1%"
        legend_items.append(
            f'<circle cx="{legend_x + 6}" cy="{ly + 4}" r="5" fill="{color}"/>' +
            f'<text x="{legend_x + 18}" y="{ly + 8}" font-size="10" ' +
            f'fill="{t.text_primary}" font-weight="600" ' +
            f'font-variant-numeric="tabular-nums">{pct_str}</text>' +
            f'<text x="{legend_x + 56}" y="{ly + 8}" font-size="{legend_font}" ' +
            f'fill="{t.text_muted}">{label}</text>'
        )
        start_angle = end_angle

    # Center label — total
    center_label = _format_compact(int(total))
    center_svg = (
        f'<text x="{center}" y="{center - 2}" text-anchor="middle" ' +
        f'font-size="18" font-weight="700" fill="{t.text_primary}">{center_label}</text>' +
        f'<text x="{center}" y="{center + 14}" text-anchor="middle" ' +
        f'font-size="9" fill="{t.text_faint}">total views</text>'
    )

    width = legend_x + legend_width
    height = max(size, len(labels) * legend_row_height + 16)
    inner = f"""  <style>text {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}</style>
  <rect width="100%" height="100%" fill="{t.bg}" rx="8"/>
  {''.join(paths)}
  {center_svg}
  {''.join(legend_items)}"""
    return _responsive_svg(inner, width, height)


def build_readme_asset_data(
    daily_rows: list[dict],
    per_repo: list[dict],
    totals: dict | None = None,
) -> dict:
    """Build chart-ready data for README SVG assets."""
    daily_by_date: dict[str, int] = {}
    for row in daily_rows:
        ts = row["ts"]
        daily_by_date[ts] = daily_by_date.get(ts, 0) + int(row.get("views_count", 0))

    sorted_dates = sorted(daily_by_date)
    last_30_dates = sorted_dates[-30:]
    last_90_dates = sorted_dates[-90:]
    top_repo_rows = per_repo[:10]
    donut_rows = per_repo[:6]

    return {
        "daily_30_dates": last_30_dates,
        "daily_30_views": [daily_by_date[ts] for ts in last_30_dates],
        "daily_90_dates": last_90_dates,
        "daily_90_views": [daily_by_date[ts] for ts in last_90_dates],
        "top_repo_labels": [row["repo"] for row in top_repo_rows],
        "top_repo_views": [row["total_views"] for row in top_repo_rows],
        "share_repo_labels": [row["repo"] for row in donut_rows],
        "share_repo_views": [row["total_views"] for row in donut_rows],
        "totals": totals,
    }


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

    totals = asset_data.get("totals") or {}
    hero_kwargs = dict(
        total_views=totals.get("total_views", 0),
        total_uniques=totals.get("total_uniques", 0),
        total_clones=totals.get("total_clones", 0),
        total_clone_uniques=totals.get("total_clone_uniques", 0),
        repo_count=len(totals.get("repos", [])),
        days_tracked=totals.get("days_tracked", 0),
    )

    files: dict[str, Path] = {}

    files["hero"], _ = _write_svg_pair(
        output_dir, "hero", svg_hero_stats, **hero_kwargs,
    )
    files["sparkline"], _ = _write_svg_pair(
        output_dir, "sparkline", svg_sparkline,
        asset_data["daily_30_views"],
        dates=asset_data["daily_30_dates"],
    )
    files["bar_chart"], _ = _write_svg_pair(
        output_dir, "bar_chart", svg_bar_chart,
        asset_data["top_repo_labels"], asset_data["top_repo_views"],
    )
    files["activity"], _ = _write_svg_pair(
        output_dir, "activity", svg_activity_graph,
        asset_data["daily_90_dates"], asset_data["daily_90_views"],
    )
    files["donut"], _ = _write_svg_pair(
        output_dir, "donut", svg_donut_chart,
        asset_data["share_repo_labels"], asset_data["share_repo_views"],
    )

    return files


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
