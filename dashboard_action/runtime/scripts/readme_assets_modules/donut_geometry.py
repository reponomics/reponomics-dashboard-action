"""Donut chart geometry and slice specifications."""

from __future__ import annotations

import math
from collections.abc import Sequence

from .theme import Theme, estimate_text_width, strip_owner


class DonutLayout:
    def __init__(self, labels: Sequence[str], size: int) -> None:
        short_labels = [strip_owner(label) for label in labels]
        self.size = size
        self.center = size // 2
        self.radius = size // 2 - 12
        self.inner_radius = self.radius * 0.55
        self.legend_x = size + 16
        self.legend_row_height = 22
        self.legend_font = 11
        legend_width = estimate_text_width(max(short_labels, key=len, default=""), self.legend_font) + 70
        self.width = self.legend_x + legend_width
        self.height = max(size, len(labels) * self.legend_row_height + 16)


class SliceSpec:
    def __init__(
        self,
        *,
        original_label: str,
        display_label: str,
        value: int | float,
        pct: float,
        path: str,
        color: str,
    ) -> None:
        self.original_label = original_label
        self.display_label = display_label
        self.value = value
        self.pct = pct
        self.path = path
        self.color = color


def default_palette(theme: Theme) -> list[str]:
    return [
        theme.accent_blue,
        theme.accent_green,
        theme.accent_purple,
        theme.accent_yellow,
        theme.accent_red,
        theme.accent_cyan,
        theme.accent_blue,
        theme.accent_green,
        theme.accent_purple,
        theme.accent_yellow,
    ]


def slice_specs(
    labels: Sequence[str],
    values: Sequence[int | float],
    total: int | float,
    layout: DonutLayout,
    palette: list[str],
) -> list[SliceSpec]:
    specs = []
    start_angle = -90.0
    short_labels = [strip_owner(label) for label in labels]
    for index, (label, value) in enumerate(zip(short_labels, values)):
        if value < 0:
            continue
        pct = value / total if total else 0
        angle = pct * 360
        end_angle = start_angle + angle
        specs.append(
            SliceSpec(
                original_label=labels[index],
                display_label=label,
                value=value,
                pct=pct,
                path=arc_path(start_angle, end_angle, layout),
                color=palette[index % len(palette)],
            )
        )
        start_angle = end_angle
    return specs


def arc_path(start_angle: float, end_angle: float, layout: DonutLayout) -> str:
    start_rad = math.radians(start_angle)
    end_rad = math.radians(end_angle)
    x1, y1 = _outer_point(start_rad, layout)
    x2, y2 = _outer_point(end_rad, layout)
    x3, y3 = _inner_point(end_rad, layout)
    x4, y4 = _inner_point(start_rad, layout)
    large_arc = 1 if end_angle - start_angle > 180 else 0
    return (
        f"M {x1:.1f} {y1:.1f} "
        + f"A {layout.radius} {layout.radius} 0 {large_arc} 1 {x2:.1f} {y2:.1f} "
        + f"L {x3:.1f} {y3:.1f} "
        + f"A {layout.inner_radius} {layout.inner_radius} 0 {large_arc} 0 {x4:.1f} {y4:.1f} Z"
    )


def _outer_point(angle: float, layout: DonutLayout) -> tuple[float, float]:
    return (
        layout.center + layout.radius * math.cos(angle),
        layout.center + layout.radius * math.sin(angle),
    )


def _inner_point(angle: float, layout: DonutLayout) -> tuple[float, float]:
    return (
        layout.center + layout.inner_radius * math.cos(angle),
        layout.center + layout.inner_radius * math.sin(angle),
    )
