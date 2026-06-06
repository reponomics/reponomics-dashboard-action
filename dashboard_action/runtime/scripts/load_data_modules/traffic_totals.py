"""Per-repository traffic totals."""

from collections import defaultdict

from load_data_modules.types import Row, Rows


def _empty_traffic_totals() -> dict[str, int]:
    """Return a mutable accumulator for one repo's traffic totals."""
    return {
        "views": 0,
        "uniques": 0,
        "clones": 0,
        "clone_uniques": 0,
        "sample_count": 0,
    }


def _add_daily_traffic(totals: dict[str, int], row: Row) -> None:
    """Add one daily traffic row to an existing totals accumulator."""
    totals["views"] += int(row.get("views_count", 0) or 0)
    totals["uniques"] += int(row.get("views_uniques", 0) or 0)
    totals["clones"] += int(row.get("clones_count", 0) or 0)
    totals["clone_uniques"] += int(row.get("clones_uniques", 0) or 0)


def _traffic_totals_by_repo(
    daily_rows: Rows, cutoff: str | None = None
) -> dict[str, dict[str, int]]:
    """Group traffic totals by repo, optionally dropping rows before ``cutoff``."""
    by_repo: defaultdict[str, dict[str, int]] = defaultdict(_empty_traffic_totals)
    for row in daily_rows:
        if cutoff and row.get("ts", "") < cutoff:
            continue
        repo = row.get("repo", "")
        if not repo:
            continue
        _add_daily_traffic(by_repo[repo], row)
        by_repo[repo]["sample_count"] += 1
    return dict(by_repo)
