"""Donut share chart README SVG rendering."""

from __future__ import annotations

from collections.abc import Sequence

from .donut_components import center_svg, legend_item, slice_path
from .donut_geometry import DonutLayout, default_palette, slice_specs
from .theme import (
    DARK,
    FONT_STYLE,
    Theme,
    empty_state_svg,
    responsive_svg,
)


def svg_donut_chart(
    labels: Sequence[str],
    values: Sequence[int | float],
    size: int = 180,
    colors: Sequence[str] | None = None,
    theme: Theme = DARK,
) -> str:
    """Generate an SVG donut chart with percentage labels and compact legend."""
    if not values:
        return empty_state_svg("No repository share data yet.", width=520, height=120, theme=theme)
    total = sum(values)
    if total <= 0:
        return empty_state_svg("No repository share data yet.", width=520, height=120, theme=theme)

    layout = DonutLayout(labels, size)
    palette = list(colors or default_palette(theme))
    slices = list(slice_specs(labels, values, total, layout, palette))
    paths = [slice_path(index, spec) for index, spec in enumerate(slices)]
    legend_items = [legend_item(index, spec, layout, theme) for index, spec in enumerate(slices)]
    inner = f"""{FONT_STYLE}
  <rect width="100%" height="100%" fill="{theme.bg}" rx="8"/>
  {''.join(paths)}
  {center_svg(int(total), layout, theme)}
  {''.join(legend_items)}"""
    return responsive_svg(inner, layout.width, layout.height)
