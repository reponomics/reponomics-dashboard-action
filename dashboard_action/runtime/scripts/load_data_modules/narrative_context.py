"""Pre-indexed context object for narrative insight recipes."""

from __future__ import annotations

from load_data_modules.narrative_grouping import (
    latest_label_buckets,
    latest_row_by_repo,
    latest_snapshot_by_repo,
    release_assets_by_release,
    rows_by_repo,
)
from load_data_modules.repo_metrics import latest_repo_community_profiles
from load_data_modules.types import Candidate, Rows


class NarrativeContext:
    """Pre-indexed retained data used by narrative recipe rules."""

    def __init__(
        self,
        *,
        metric_rows: Rows,
        path_rows: Rows,
        referrer_rows: Rows,
        event_rows: Rows,
        release_asset_rows: Rows,
        issue_pr_rows: Rows,
        issue_label_rows: Rows,
        endpoint_rows: Rows,
        collection_day_rows: Rows,
        growth: Candidate,
    ) -> None:
        self.paths_by_repo = latest_snapshot_by_repo(path_rows)
        self.referrers_by_repo = latest_snapshot_by_repo(referrer_rows)
        self.events_by_repo = rows_by_repo(event_rows)
        self.release_assets_by_release = release_assets_by_release(release_asset_rows)
        self.latest_issue_pr = latest_row_by_repo(issue_pr_rows)
        self.latest_labels = latest_label_buckets(issue_label_rows)
        self.endpoint_status = rows_by_repo(endpoint_rows)
        self.collection_day_rows = collection_day_rows
        self.growth = growth
        self.community = latest_repo_community_profiles(metric_rows)
