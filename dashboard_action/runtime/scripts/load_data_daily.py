"""Daily traffic aggregation facade."""

from load_data_daily_aggregates import (
    aggregate_by_date,
    aggregate_per_repo,
    aggregate_totals,
)
from load_data_traffic_totals import (
    _add_daily_traffic,
    _empty_traffic_totals,
    _traffic_totals_by_repo,
)

__all__ = [
    "_add_daily_traffic",
    "_empty_traffic_totals",
    "_traffic_totals_by_repo",
    "aggregate_by_date",
    "aggregate_per_repo",
    "aggregate_totals",
]
