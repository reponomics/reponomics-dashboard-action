"""Aggregate traffic momentum metrics."""

from collections import defaultdict
from datetime import date as date_type
import statistics
from typing import Any

MOMENTUM_EMPTY = {
    "best_day": None,
    "streak_days": 0,
    "baseline": 0.0,
    "days_since_peak": None,
    "top_single_day": None,
}

MOMENTUM_BASELINE_WINDOW = 14


def compute_momentum(daily_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate momentum stats from daily traffic rows."""
    if not daily_rows:
        return dict(MOMENTUM_EMPTY)

    by_date, top_single_day = _daily_view_totals(daily_rows)
    if not by_date:
        return {**MOMENTUM_EMPTY, "top_single_day": top_single_day}

    sorted_dates = sorted(by_date.keys())
    values = [by_date[d] for d in sorted_dates]
    best_day = _best_day(sorted_dates, values)
    baseline = _momentum_baseline(values)
    return {
        "best_day": best_day,
        "streak_days": _trailing_streak(values, baseline),
        "baseline": float(baseline),
        "days_since_peak": _days_since_peak(sorted_dates[-1], best_day["date"]),
        "top_single_day": top_single_day,
    }


def _daily_view_totals(daily_rows):
    by_date: dict[str, int] = defaultdict(int)
    top_single_day = None
    for row in daily_rows:
        ts = row.get("ts")
        views = int(row.get("views_count", 0) or 0)
        if not ts:
            continue
        by_date[ts] += views
        top_single_day = _top_single_day(top_single_day, row, ts, views)
    return by_date, top_single_day


def _top_single_day(current, row, ts, views):
    if current is not None and views <= current["views"]:
        return current
    return {"repo": row.get("repo", ""), "date": ts, "views": views}


def _best_day(sorted_dates, values):
    best_idx = max(range(len(values)), key=lambda i: values[i])
    return {"date": sorted_dates[best_idx], "views": values[best_idx]}


def _momentum_baseline(values):
    end_excl = max(0, len(values) - 1)
    start = max(0, end_excl - MOMENTUM_BASELINE_WINDOW)
    tail = values[start:end_excl]
    return statistics.median(tail) if tail else 0.0


def _trailing_streak(values, baseline):
    streak_days = 0
    for views in reversed(values):
        if views <= baseline:
            break
        streak_days += 1
    return streak_days


def _days_since_peak(latest_date, peak_date):
    try:
        latest = date_type.fromisoformat(latest_date)
        peak = date_type.fromisoformat(peak_date)
    except (ValueError, TypeError):
        return None
    return (latest - peak).days
