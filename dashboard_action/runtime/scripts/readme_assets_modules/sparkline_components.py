"""Sparkline SVG component fragments."""

from __future__ import annotations

from collections.abc import Sequence

from .sparkline_geometry import SparkPoint, SparklineLayout
from .theme import Theme, format_compact


def grid_lines(layout: SparklineLayout, theme: Theme) -> list[str]:
    lines = []
    for frac in (0.25, 0.5, 0.75):
        gy = layout.top_pad + layout.usable_height * (1 - frac)
        lines.append(
            f'<line x1="{layout.left_pad}" y1="{gy:.1f}" x2="{layout.width - layout.right_pad}" '
            + f'y2="{gy:.1f}" stroke="{theme.grid}" stroke-width="1"/>'
        )
    return lines


def polyline_svg(points: str, stroke_color: str) -> str:
    return (
        f'<polyline points="{points}" fill="none" stroke="{stroke_color}" '
        + 'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        + 'stroke-dasharray="2000" stroke-dashoffset="2000">'
        + '<animate attributeName="stroke-dashoffset" values="2000;0;0;2000" '
        + 'keyTimes="0;0.1;0.92;1" dur="12s" repeatCount="indefinite" '
        + 'calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1;0.4 0 0.2 1"/>'
        + "</polyline>"
    )


def peak_svg(
    values: list[int | float],
    points: list[SparkPoint],
    stroke_color: str,
    theme: Theme,
) -> str:
    peak_idx = values.index(max(values))
    px, py, pv = points[peak_idx]
    peak_label = format_compact(int(pv))
    return (
        f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" fill="{stroke_color}" opacity="0">'
        + '<animate attributeName="opacity" values="0;0;1;1;0" '
        + 'keyTimes="0;0.08;0.1;0.92;1" dur="12s" repeatCount="indefinite"/></circle>'
        + f'<text x="{px:.1f}" y="{py - 8:.1f}" text-anchor="middle" '
        + f'font-size="10" fill="{theme.text_primary}" font-weight="600" opacity="0">{peak_label}'
        + '<animate attributeName="opacity" values="0;0;1;1;0" '
        + 'keyTimes="0;0.09;0.11;0.92;1" dur="12s" repeatCount="indefinite"/></text>'
    )


def last_svg(values: list[int | float], points: list[SparkPoint], theme: Theme) -> str:
    if values.index(max(values)) == len(values) - 1:
        return ""
    last_x, last_y, last_v = points[-1]
    last_label = format_compact(int(last_v))
    return (
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2.5" fill="{theme.text_muted}"/>'
        + f'<text x="{last_x - 6:.1f}" y="{last_y - 7:.1f}" text-anchor="end" '
        + f'font-size="9" fill="{theme.text_muted}">{last_label}</text>'
    )


def date_labels(dates: Sequence[str] | None, layout: SparklineLayout, theme: Theme) -> str:
    if not dates or len(dates) < 2:
        return ""
    return (
        f'<text x="{layout.left_pad}" y="{layout.height - 4}" font-size="9" '
        + f'fill="{theme.text_faint}">{dates[0]}</text>'
        + f'<text x="{layout.width - layout.right_pad}" y="{layout.height - 4}" text-anchor="end" '
        + f'font-size="9" fill="{theme.text_faint}">{dates[-1]}</text>'
    )
