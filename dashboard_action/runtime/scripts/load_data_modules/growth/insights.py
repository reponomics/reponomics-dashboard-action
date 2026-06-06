"""Cross-signal growth insight candidate orchestration."""

from load_data_modules.growth.core import growth_analytics
from load_data_modules.growth.attention import (
    _clone_heavy_star_light,
    _downstream_without_traffic_spike,
    _high_attention_low_interest,
    _quiet_resonance,
    _traffic_without_downstream_growth,
)
from load_data_modules.growth.counters import (
    _fork_spike,
    _negative_counter_movement,
    _watcher_subscriber_spike,
)


_GROWTH_CANDIDATE_BUILDERS = (
    _high_attention_low_interest,
    _quiet_resonance,
    _clone_heavy_star_light,
    _fork_spike,
    _watcher_subscriber_spike,
    _traffic_without_downstream_growth,
    _downstream_without_traffic_spike,
    _negative_counter_movement,
)


def _growth_insight_candidates(daily_rows, metric_rows=None, growth=None):
    """Return cross-signal insight candidates with volume/sample guards."""
    growth = _resolved_growth(daily_rows, metric_rows, growth)
    if growth is None:
        return []

    candidates = []
    for repo, row in growth.get("per_repo", {}).items():
        context = _growth_context(repo, row)
        for builder in _GROWTH_CANDIDATE_BUILDERS:
            builder(candidates, context)
    return candidates


def _resolved_growth(daily_rows, metric_rows, growth):
    if growth is not None:
        return growth
    if metric_rows is None:
        return None
    return growth_analytics(daily_rows, metric_rows)


def _growth_context(repo, row):
    traffic = row.get("traffic", {})
    deltas = row.get("deltas", {})
    conversions = row.get("conversion", {})
    return {
        "repo": repo,
        "views": int(traffic.get("views", 0) or 0),
        "visitors": int(traffic.get("uniques", 0) or 0),
        "clones": int(traffic.get("clones", 0) or 0),
        "traffic_samples": int(traffic.get("sample_count", 0) or 0),
        "metric_samples": int(deltas.get("sample_count", 0) or 0),
        "stargazers_delta": int(deltas.get("stargazers_delta", 0) or 0),
        "subscribers_delta": int(deltas.get("subscribers_delta", 0) or 0),
        "forks_delta": int(deltas.get("forks_delta", 0) or 0),
        "conversions": conversions,
    }
