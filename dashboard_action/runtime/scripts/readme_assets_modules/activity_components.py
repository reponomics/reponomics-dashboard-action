"""Activity heatmap SVG component fragments."""

from __future__ import annotations

from datetime import date, timedelta

from .activity_layout import ActivityLayout
from .theme import Theme


def day_labels(layout: ActivityLayout, theme: Theme) -> list[str]:
    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    labels = []
    for day_index in (1, 3, 5):
        dy = layout.grid_y + day_index * (layout.cell_size + layout.gap) + layout.cell_size // 2 + 3
        labels.append(
            f'<text x="{layout.day_label_width}" y="{dy}" text-anchor="end" '
            + f'font-size="9" fill="{theme.text_faint}">{day_names[day_index]}</text>'
        )
    return labels


def month_labels(layout: ActivityLayout, theme: Theme) -> list[str]:
    labels = []
    seen_months: set[tuple[int, int]] = set()
    for week_idx in range(layout.num_weeks):
        week_start = layout.start_sunday + timedelta(days=week_idx * 7)
        month_key = (week_start.year, week_start.month)
        if month_key in seen_months:
            continue
        seen_months.add(month_key)
        mx = layout.grid_x + week_idx * (layout.cell_size + layout.gap)
        labels.append(
            f'<text x="{mx}" y="{layout.month_label_height}" '
            + f'font-size="9" fill="{theme.text_faint}">{week_start.strftime("%b")}</text>'
        )
    return labels


def activity_cell(
    offset: int,
    layout: ActivityLayout,
    values_by_date: dict[date, int | None],
    max_value: int,
    theme: Theme,
) -> str:
    current_date = layout.start_sunday + timedelta(days=offset)
    value = values_by_date.get(current_date, 0)
    x, y = layout.cell_xy(offset)
    color = level_color(value, max_value, theme)
    label = (
        f"{current_date.isoformat()}: unreported traffic"
        if value is None
        else f"{current_date.isoformat()}: {value:,} views"
    )
    fade_in = f"{offset * 0.012 / 14:.3f}"
    fade_in_end = f"{min((offset * 0.012 + 0.3) / 14, 0.15):.3f}"
    return (
        f'<rect x="{x}" y="{y}" width="{layout.cell_size}" height="{layout.cell_size}" '
        + f'fill="{color}" rx="2" opacity="0">'
        + '<animate attributeName="opacity" values="0;0;1;1;0" '
        + f'keyTimes="0;{fade_in};{fade_in_end};0.92;1" dur="14s" '
        + 'repeatCount="indefinite"/>'
        + f"<title>{label}</title></rect>"
    )


def level_color(value: int | None, max_val: int, theme: Theme) -> str:
    heatmap_colors = [theme.heatmap_empty] + theme.heatmap_scale
    if value is None:
        return theme.border
    if value <= 0 or max_val <= 0:
        return heatmap_colors[0]
    ratio = value / max_val
    if ratio <= 0.25:
        return heatmap_colors[1]
    if ratio <= 0.5:
        return heatmap_colors[2]
    if ratio <= 0.75:
        return heatmap_colors[3]
    return heatmap_colors[4]
