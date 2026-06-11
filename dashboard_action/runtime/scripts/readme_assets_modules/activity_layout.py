"""Activity heatmap calendar layout helpers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date, timedelta


class ActivityLayout:
    def __init__(
        self,
        pairs: list[tuple[date, int | None]],
        *,
        cell_size: int,
        gap: int,
    ) -> None:
        self.cell_size = cell_size
        self.gap = gap
        start_date = pairs[0][0]
        end_date = pairs[-1][0]
        days_to_sunday = (start_date.weekday() + 1) % 7
        self.start_sunday = start_date - timedelta(days=days_to_sunday)
        self.total_days = (end_date - self.start_sunday).days + 1
        self.num_weeks = math.ceil(self.total_days / 7)
        self.day_label_width = 28
        self.month_label_height = 14
        self.grid_x = self.day_label_width + 4
        self.grid_y = self.month_label_height + 4
        self.svg_width = self.grid_x + self.num_weeks * (cell_size + gap) + 8
        self.svg_height = self.grid_y + 7 * (cell_size + gap) + 8

    def cell_xy(self, offset: int) -> tuple[int, int]:
        week = offset // 7
        day = offset % 7
        return (
            self.grid_x + week * (self.cell_size + self.gap),
            self.grid_y + day * (self.cell_size + self.gap),
        )


def valid_date_pairs(
    dates: Sequence[str],
    values: Sequence[int | None],
) -> list[tuple[date, int | None]]:
    pairs = []
    for raw_date, value in zip(dates, values):
        try:
            parsed = date.fromisoformat(raw_date)
        except ValueError:
            continue
        pairs.append((parsed, value))
    return sorted(pairs, key=lambda item: item[0])
