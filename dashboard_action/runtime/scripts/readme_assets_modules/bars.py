"""Horizontal bar chart README SVG rendering."""

from __future__ import annotations

from collections.abc import Sequence

from .theme import (
    DARK,
    FONT_STYLE,
    Theme,
    empty_state_svg,
    estimate_text_width,
    format_compact,
    responsive_svg,
    strip_owner,
)


def svg_bar_chart(
    labels: Sequence[str],
    values: Sequence[int | float],
    width: int = 520,
    bar_color: str | None = None,
    theme: Theme = DARK,
) -> str:
    """Generate an SVG horizontal bar chart with compact labels and value context."""
    bar_color = bar_color or theme.accent_blue
    if not values:
        return empty_state_svg("No repository totals yet.", width=width, height=260, theme=theme)

    layout = BarChartLayout(labels, values, width)
    bars = [
        _bar_row(i, label, value, layout, bar_color, theme)
        for i, (label, value) in enumerate(zip(layout.short_labels, values))
    ]
    inner = f"""{FONT_STYLE}
  <rect width="100%" height="100%" fill="{theme.bg}" rx="8"/>
  {''.join(bars)}"""
    return responsive_svg(inner, layout.total_width, layout.total_height)


class BarChartLayout:
    def __init__(self, labels: Sequence[str], values: Sequence[int | float], width: int) -> None:
        self.short_labels = [strip_owner(lbl) for lbl in labels]
        self.total = sum(values) or 1
        self.max_val = max(values) if values else 1
        self.bar_height = 22
        self.spacing = 8
        self.label_font = 11
        self.value_font = 10
        self.top_pad = 8
        self.label_width = (
            estimate_text_width(max(self.short_labels, key=len, default=""), self.label_font)
            + 16
        )
        value_col = 70
        self.bar_area_width = max(140, width - self.label_width - value_col - 20)
        self.total_width = self.label_width + self.bar_area_width + value_col + 20
        self.total_height = self.top_pad + len(values) * (self.bar_height + self.spacing) + 4


def _bar_row(
    index: int,
    label: str,
    value: int | float,
    layout: BarChartLayout,
    bar_color: str,
    theme: Theme,
) -> str:
    y = layout.top_pad + index * (layout.bar_height + layout.spacing)
    bar_w = _visible_bar_width(value, layout.max_val, layout.bar_area_width)
    pct = value / layout.total * 100
    value_str = format_compact(int(value))
    pct_str = f"{pct:.0f}%" if pct >= 1 else "&lt;1%"
    return (
        f'<rect x="{layout.label_width}" y="{y}" width="{layout.bar_area_width}" '
        + f'height="{layout.bar_height}" fill="{theme.surface}" rx="4"/>'
        + f'<rect x="{layout.label_width}" y="{y}" width="{bar_w:.1f}" '
        + f'height="{layout.bar_height}" fill="{bar_color}" rx="4" opacity="0.85"/>'
        + f'<text x="{layout.label_width - 8}" y="{y + layout.bar_height // 2 + 4}" '
        + f'text-anchor="end" font-size="{layout.label_font}" fill="{theme.text_secondary}">{label}</text>'
        + f'<text x="{layout.label_width + layout.bar_area_width + 8}" '
        + f'y="{y + layout.bar_height // 2 + 4}" font-size="{layout.value_font}" fill="{theme.text_primary}">'
        + f'{value_str} <tspan fill="{theme.text_faint}">{pct_str}</tspan></text>'
    )


def _visible_bar_width(
    value: int | float,
    max_val: int | float,
    bar_area_width: int,
) -> int | float:
    bar_w = (value / max_val) * bar_area_width if max_val else 0
    if value > 0 and bar_w < 4:
        return 4
    return bar_w
