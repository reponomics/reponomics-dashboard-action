"""Sparkline chart layout and coordinate helpers."""

from __future__ import annotations


SparkPoint = tuple[float, float, int | float]
SparkValue = int | float | None


class SparklineLayout:
    def __init__(self, *, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.top_pad = 22
        self.bottom_pad = 20
        self.left_pad = 8
        self.right_pad = 8
        self.usable_width = width - self.left_pad - self.right_pad
        self.usable_height = height - self.top_pad - self.bottom_pad


def spark_points(values: list[SparkValue], layout: SparklineLayout) -> list[SparkPoint]:
    numeric_values = [value for value in values if value is not None]
    min_val = min(numeric_values)
    max_val = max(numeric_values)
    value_range = max_val - min_val if max_val != min_val else 1
    denominator = max(1, len(values) - 1)
    return [
        (
            layout.left_pad + (i / denominator) * layout.usable_width,
            layout.top_pad
            + layout.usable_height
            - ((value - min_val) / value_range) * layout.usable_height,
            value,
        )
        for i, value in enumerate(values)
        if value is not None
    ]


def polyline_points(points: list[SparkPoint]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)


def fill_points(line_points: str, layout: SparklineLayout) -> str:
    return (
        f"{layout.left_pad},{layout.height - layout.bottom_pad} {line_points} "
        + f"{layout.width - layout.right_pad},{layout.height - layout.bottom_pad}"
    )
