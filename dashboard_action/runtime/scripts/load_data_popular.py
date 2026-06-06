"""Popular traffic aggregation facade."""

from load_data_paths import _content_label, top_paths
from load_data_referrers import top_referrers
from load_data_snapshots import _latest_snapshot_rows

__all__ = [
    "_content_label",
    "_latest_snapshot_rows",
    "top_paths",
    "top_referrers",
]
