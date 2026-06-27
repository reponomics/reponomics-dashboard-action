"""Shared data-loading path for README and HTML dashboard renderers.

Both renderers must derive from the same canonical CSV data to ensure
core totals agree. This module keeps the public import surface stable while
delegating cohesive aggregation work to smaller modules.
"""

import os

from repo_config import load_repo_config
import storage

from load_data_modules.constants import GROWTH_COUNTERS
from load_data_modules.daily import (
    _traffic_totals_by_repo,
    aggregate_by_date,
    aggregate_per_repo,
    aggregate_totals,
)
from load_data_modules.dates import _latest_date_from_rows, _window_cutoff
from load_data_modules.growth.core import (
    growth_analytics,
    repo_metric_deltas,
)
from load_data_modules.growth.insights import _growth_insight_candidates
from load_data_modules.momentum import compute_momentum
from load_data_modules.parse import (
    _bool_or_none,
    _counter_snapshot,
    _int_or_none,
)
from load_data_modules.popular import (
    _content_label,
    _latest_snapshot_rows,
    top_paths,
    top_referrers,
)
from load_data_modules.repo_metrics import (
    aggregate_repo_metrics,
    latest_repo_community_profiles,
    latest_repo_metadata,
    latest_repo_metrics,
    latest_repo_metrics_per_day,
    repo_growth_series,
)
from load_data_modules.insights import (
    actionable_insights,
    actionable_insights_structured,
)
from load_data_modules.quality import (
    collection_quality,
)
from load_data_modules.quality_days import collection_quality_days
from load_data_modules.quality_summary import _quality_summary_for_rows
from load_data_modules.trend_insights import (
    _spike_candidate,
    _window_change_candidate,
)
from traffic_reporting import (
    traffic_reporting_summary,
)

__all__ = [
    "GROWTH_COUNTERS",
    "_bool_or_none",
    "_content_label",
    "_counter_snapshot",
    "_filter_published_rows",
    "_growth_insight_candidates",
    "_int_or_none",
    "_latest_date_from_rows",
    "_latest_snapshot_rows",
    "_quality_summary_for_rows",
    "_spike_candidate",
    "_traffic_totals_by_repo",
    "_window_change_candidate",
    "_window_cutoff",
    "actionable_insights",
    "actionable_insights_structured",
    "aggregate_by_date",
    "aggregate_per_repo",
    "aggregate_repo_metrics",
    "aggregate_totals",
    "collection_quality",
    "collection_quality_days",
    "compute_momentum",
    "growth_analytics",
    "latest_repo_community_profiles",
    "latest_repo_metadata",
    "latest_repo_metrics",
    "latest_repo_metrics_per_day",
    "load_collection_status",
    "load_collection_days",
    "load_daily",
    "load_paths",
    "load_referrers",
    "load_repo_metrics",
    "load_traffic_coverage",
    "repo_growth_series",
    "repo_metric_deltas",
    "storage",
    "top_paths",
    "top_referrers",
    "traffic_reporting_summary",
]


def load_daily(data_dir=None):
    """Load canonical daily rows, falling back to traffic-log.csv for old artifacts."""
    data_path = data_dir or storage.DATA_DIR
    rows = storage.read_csv(os.path.join(data_path, "traffic-daily.csv"))
    if not rows:
        rows = storage.read_csv(os.path.join(data_path, "traffic-log.csv"))
    return _filter_published_rows(rows)


def load_referrers(data_dir=None):
    """Load traffic-referrers.csv and return the raw row list."""
    return _load_csv("traffic-referrers.csv", data_dir)


def load_paths(data_dir=None):
    """Load traffic-paths.csv and return the raw row list."""
    return _load_csv("traffic-paths.csv", data_dir)


def load_repo_metrics(data_dir=None):
    """Load repo-metrics.csv and return the raw row list."""
    return _load_csv("repo-metrics.csv", data_dir)


def load_collection_status(data_dir=None):
    """Load collection-status.csv and return the raw row list."""
    return _load_csv("collection-status.csv", data_dir)


def load_collection_days(data_dir=None):
    """Load collection-days.csv and return the raw row list."""
    return _load_csv("collection-days.csv", data_dir)


def load_traffic_coverage(data_dir=None):
    """Load traffic-coverage.csv and return the raw row list."""
    return _load_csv("traffic-coverage.csv", data_dir)


def _load_csv(filename, data_dir=None):
    data_path = data_dir or storage.DATA_DIR
    return _filter_published_rows(storage.read_csv(os.path.join(data_path, filename)))


def _published_repos():
    """Return repos selected for rendering, ignoring missing config files."""
    return set(load_repo_config().get("publish_repositories", []))


def _filter_published_rows(rows):
    """Limit rendered outputs to publish.repositories while retaining history."""
    published = _published_repos()
    if not published:
        return rows
    return [row for row in rows if not row.get("repo") or row.get("repo") in published]
