"""Activity heatmap README SVG rendering."""

from __future__ import annotations

from collections.abc import Sequence

from .activity_components import activity_cell, day_labels, month_labels
from .activity_layout import ActivityLayout, valid_date_pairs
from .theme import DARK, FONT_STYLE, Theme, empty_state_svg, responsive_svg


def svg_activity_graph(
    dates: Sequence[str],
    values: Sequence[int],
    cell_size: int = 11,
    gap: int = 3,
    theme: Theme = DARK,
) -> str:
    """Generate a GitHub-style activity heatmap with month and day labels."""
    if not values or not dates:
        return empty_state_svg("No 90-day activity yet.", width=520, height=120, theme=theme)
    pairs = valid_date_pairs(dates, values)
    if not pairs:
        return empty_state_svg("No 90-day activity yet.", width=520, height=120, theme=theme)

    layout = ActivityLayout(pairs, cell_size=cell_size, gap=gap)
    values_by_date = dict(pairs)
    max_value = max(values_by_date.values()) if values_by_date else 1
    cells = [
        activity_cell(offset, layout, values_by_date, max_value, theme)
        for offset in range(layout.total_days)
    ]
    inner = f"""{FONT_STYLE}
  <rect width="100%" height="100%" fill="{theme.bg}" rx="8"/>
  {''.join(month_labels(layout, theme))}
  {''.join(day_labels(layout, theme))}
  {''.join(cells)}"""
    return responsive_svg(inner, layout.svg_width, layout.svg_height)
