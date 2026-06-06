"""Popular referrer aggregation."""

from collections import defaultdict

from load_data_snapshots import _latest_snapshot_rows


def top_referrers(referrer_rows, limit=10):
    """Aggregate the latest referrer snapshot per repo and return top N."""
    by_ref = defaultdict(lambda: {"count": 0, "uniques": 0})
    for row in _latest_snapshot_rows(referrer_rows):
        ref = row["referrer"]
        by_ref[ref]["count"] += int(row.get("count", 0))
        by_ref[ref]["uniques"] += int(row.get("uniques", 0))

    result = [
        {"referrer": ref, "count": totals["count"], "uniques": totals["uniques"]}
        for ref, totals in by_ref.items()
    ]
    result.sort(key=lambda x: x["count"], reverse=True)
    return result[:limit]
