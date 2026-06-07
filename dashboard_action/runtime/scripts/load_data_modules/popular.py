"""Popular traffic aggregation facade."""

from load_data_modules.paths import _content_label, top_paths
from load_data_modules.referrers import top_referrers
from load_data_modules.snapshots import _latest_snapshot_rows

__all__ = [
    "_content_label",
    "_latest_snapshot_rows",
    "top_paths",
    "top_referrers",
]
