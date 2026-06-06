"""Snapshot selection for rolling GitHub traffic endpoints."""

from load_data_modules.types import Rows


def _latest_snapshot_rows(rows: Rows) -> Rows:
    """Return only rows from the latest captured snapshot for each repo."""
    if not rows:
        return []

    latest_by_repo: dict[str, str] = {}
    for row in rows:
        repo = row["repo"]
        captured_at = row.get("captured_at", "")
        if captured_at > latest_by_repo.get(repo, ""):
            latest_by_repo[repo] = captured_at

    return [
        row
        for row in rows
        if row.get("captured_at", "") == latest_by_repo.get(row["repo"], "")
    ]
