"""Daily traffic aggregate projections."""

from collections import defaultdict

from load_data_traffic_totals import _add_daily_traffic


def aggregate_totals(daily_rows):
    """Compute grand totals from daily rows."""
    repos = set()
    dates = set()
    totals = _empty_grand_totals()

    for row in daily_rows:
        repos.add(row["repo"])
        dates.add(row["ts"])
        totals["total_views"] += int(row.get("views_count", 0))
        totals["total_uniques"] += int(row.get("views_uniques", 0))
        totals["total_clones"] += int(row.get("clones_count", 0))
        totals["total_clone_uniques"] += int(row.get("clones_uniques", 0))

    return {"repos": repos, **totals, "days_tracked": len(dates)}


def _empty_grand_totals():
    return {
        "total_views": 0,
        "total_uniques": 0,
        "total_clones": 0,
        "total_clone_uniques": 0,
    }


def aggregate_by_date(daily_rows):
    """Group daily rows by date, summing across repos."""
    by_date = defaultdict(
        lambda: {"views": 0, "uniques": 0, "clones": 0, "clone_uniques": 0}
    )
    for row in daily_rows:
        _add_daily_traffic(by_date[row["ts"]], row)

    dates = sorted(by_date.keys())
    return dates, _series_for_dates(by_date, dates)


def _series_for_dates(by_date, dates):
    return {
        "views": [by_date[d]["views"] for d in dates],
        "uniques": [by_date[d]["uniques"] for d in dates],
        "clones": [by_date[d]["clones"] for d in dates],
        "clone_uniques": [by_date[d]["clone_uniques"] for d in dates],
    }


def aggregate_per_repo(daily_rows):
    """Compute per-repo totals from daily rows."""
    by_repo = defaultdict(
        lambda: {"views": 0, "uniques": 0, "clones": 0, "clone_uniques": 0}
    )
    for row in daily_rows:
        _add_daily_traffic(by_repo[row["repo"]], row)

    result = [_repo_total_row(repo, totals) for repo, totals in by_repo.items()]
    result.sort(key=lambda x: x["total_views"], reverse=True)
    return result


def _repo_total_row(repo, totals):
    return {
        "repo": repo,
        "total_views": totals["views"],
        "total_uniques": totals["uniques"],
        "total_clones": totals["clones"],
        "total_clone_uniques": totals["clone_uniques"],
    }
