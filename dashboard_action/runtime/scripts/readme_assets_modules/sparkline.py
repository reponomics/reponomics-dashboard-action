"""Sparkline README SVG rendering."""

from __future__ import annotations

from collections.abc import Sequence

from .sparkline_components import date_labels, grid_lines, last_svg, peak_svg, polyline_svg
from .sparkline_geometry import SparklineLayout, SparkValue, fill_points, polyline_points, spark_points
from .theme import DARK, FONT_STYLE, Theme, empty_state_svg, responsive_svg


def svg_sparkline(
    values: Sequence[SparkValue],
    dates: Sequence[str] | None = None,
    width: int = 520,
    height: int = 100,
    stroke_color: str | None = None,
    theme: Theme = DARK,
) -> str:
    """Generate an SVG sparkline with peak annotation and subtle grid."""
    stroke_color = stroke_color or theme.accent_blue
    numeric_values = [value for value in values if value is not None]
    if not values or len(numeric_values) < 2:
        return empty_state_svg(
            "Not enough data for a trend chart.", width=width, height=height, theme=theme
        )

    layout = SparklineLayout(width=width, height=height)
    vals = list(values)
    points = spark_points(vals, layout)
    line_points = polyline_points(points)
    null_region = _null_region_svg(vals, layout, theme)

    inner = f"""{FONT_STYLE}
  <defs>
    <linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{stroke_color}" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="{stroke_color}" stop-opacity="0.02"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="{theme.bg}" rx="8"/>
{null_region}  {''.join(grid_lines(layout, theme))}
  <polygon points="{fill_points(line_points, layout)}" fill="url(#sparkFill)" />
  {polyline_svg(line_points, stroke_color)}
  {peak_svg(numeric_values, points, stroke_color, theme)}
  {last_svg(numeric_values, points, theme)}
  {date_labels(dates, layout, theme)}"""
    return responsive_svg(inner, width, height)


def _null_region_svg(
    values: list[SparkValue],
    layout: SparklineLayout,
    theme: Theme,
) -> str:
    try:
        first_null = values.index(None)
    except ValueError:
        return ""
    denominator = max(1, len(values) - 1)
    start_x = layout.left_pad + (first_null / denominator) * layout.usable_width
    width = max(0, layout.width - layout.right_pad - start_x)
    if width <= 0:
        return ""
    return (
        f'  <rect x="{start_x:.1f}" y="{layout.top_pad}" width="{width:.1f}" '
        + f'height="{layout.usable_height}" fill="{theme.surface}" opacity="0.45" rx="3">'
        + "<title>Unreported traffic dates</title></rect>\n"
    )
