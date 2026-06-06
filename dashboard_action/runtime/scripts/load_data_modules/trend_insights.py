"""Traffic trend and spike insight candidates."""

import math
import statistics

TREND_MIN_DAYS = 6
TREND_MIN_WINDOW = 3
SPIKE_MIN_DAYS = 8
SPIKE_MIN_BASELINE_DAYS = 5
SPIKE_TAIL_WINDOW = 15


def _window_change_candidate(repo, metric, values, min_floor):
    """Build a 7d-over-7d candidate for one metric series."""
    window = _trend_window(values)
    if window is None:
        return None

    prev = sum(values[-2 * window:-window])
    curr = sum(values[-window:])
    delta = curr - prev
    if not _passes_trend_floor(prev, curr, delta, min_floor):
        return None

    pct_text, pct_factor, pct_value = _trend_percent(prev, delta)
    return {
        "score": math.log1p(abs(delta)) * pct_factor,
        "repo": repo,
        "kind": "trend",
        "metric": metric,
        "window_days": window,
        "prior": prev,
        "current": curr,
        "delta": delta,
        "pct": pct_value,
        "text": (
            f"`{repo}` {metric} {pct_text} over the last {window}d "
            + f"({prev:,} -> {curr:,}, {delta:+,})."
        ),
    }


def _trend_window(values):
    if len(values) < TREND_MIN_DAYS:
        return None
    window = min(7, len(values) // 2)
    return window if window >= TREND_MIN_WINDOW else None


def _passes_trend_floor(prev, curr, delta, min_floor):
    abs_delta = abs(delta)
    if abs_delta == 0:
        return False
    total_floor = max(prev, curr)
    return total_floor >= min_floor or abs_delta >= max(2, min_floor // 2)


def _trend_percent(prev, delta):
    if prev == 0:
        return "new activity", 1.5, None
    pct = (delta / prev) * 100.0
    return f"{pct:+.0f}%", 1.0 + min(abs(pct) / 100.0, 2.0), pct


def _spike_candidate(repo, metric, values):
    """Build a daily spike/drop candidate using trailing median + MAD."""
    baseline = _spike_baseline(values)
    if baseline is None:
        return None

    latest = values[-1]
    median = statistics.median(baseline)
    delta = latest - median
    if not _passes_spike_size(delta, median):
        return None

    z_like = abs(delta) / _spike_dispersion(baseline, median)
    if z_like < 2.0:
        return None

    direction = "spiked" if delta > 0 else "dropped"
    return {
        "score": math.log1p(abs(delta)) + z_like,
        "repo": repo,
        "kind": "spike",
        "metric": metric,
        "direction": direction,
        "current": latest,
        "baseline": median,
        "delta": delta,
        "text": (
            f"`{repo}` {metric} {direction} versus baseline "
            + f"(latest {latest:,} vs trailing median {median:.0f})."
        ),
    }


def _spike_baseline(values):
    if len(values) < SPIKE_MIN_DAYS:
        return None
    baseline = values[-SPIKE_TAIL_WINDOW:-1] if len(values) > SPIKE_TAIL_WINDOW else values[:-1]
    return baseline if len(baseline) >= SPIKE_MIN_BASELINE_DAYS else None


def _passes_spike_size(delta, median):
    return abs(delta) >= max(5, median * 0.5)


def _spike_dispersion(baseline, median):
    deviation = [abs(value - median) for value in baseline]
    mad = statistics.median(deviation) if deviation else 0
    return mad if mad >= 1 else max(median, 1)
