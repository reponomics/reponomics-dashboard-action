"""Popular referrer aggregation."""

from collections import defaultdict

from load_data_modules.snapshots import _latest_snapshot_rows
from load_data_modules.types import Result, Rows


def top_referrers(referrer_rows: Rows, limit: int = 10) -> list[Result]:
    """Aggregate the latest referrer snapshot per repo and return top N."""
    by_ref: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "uniques": 0})
    for row in _latest_snapshot_rows(referrer_rows):
        ref = row["referrer"]
        by_ref[ref]["count"] += int(row.get("count", 0))
        by_ref[ref]["uniques"] += int(row.get("uniques", 0))

    result: list[Result] = [
        {"referrer": ref, "count": totals["count"], "uniques": totals["uniques"]}
        for ref, totals in by_ref.items()
    ]
    result.sort(key=lambda x: int(x["count"]), reverse=True)
    return result[:limit]
