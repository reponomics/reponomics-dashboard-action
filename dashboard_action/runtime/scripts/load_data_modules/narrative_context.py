"""Pre-indexed context object for narrative insight recipes."""

from __future__ import annotations

from load_data_modules.narrative_grouping import (
    latest_label_buckets,
    latest_row_by_repo,
    latest_snapshot_by_repo,
    previous_snapshot_by_repo,
    release_assets_by_release,
    rows_by_repo_week,
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
        daily_rows: Rows,
        path_rows: Rows,
        referrer_rows: Rows,
        event_rows: Rows,
        release_asset_rows: Rows,
        issue_pr_rows: Rows,
        issue_label_rows: Rows,
        endpoint_rows: Rows,
        collection_day_rows: Rows,
        language_rows: Rows,
        topic_rows: Rows,
        code_frequency_rows: Rows,
        contributor_activity_rows: Rows,
        growth: Candidate,
    ) -> None:
        self.daily_by_repo = rows_by_repo(daily_rows)
        self.paths_by_repo = latest_snapshot_by_repo(path_rows)
        self.referrers_by_repo = latest_snapshot_by_repo(referrer_rows)
        self.events_by_repo = rows_by_repo(event_rows)
        self.release_assets_by_release = release_assets_by_release(release_asset_rows)
        self.latest_issue_pr = latest_row_by_repo(issue_pr_rows)
        self.latest_labels = latest_label_buckets(issue_label_rows)
        self.endpoint_status = rows_by_repo(endpoint_rows)
        self.collection_day_rows = collection_day_rows
        self.latest_languages = latest_snapshot_by_repo(language_rows)
        self.previous_languages = previous_snapshot_by_repo(language_rows)
        self.latest_topics = latest_snapshot_by_repo(topic_rows)
        self.previous_topics = previous_snapshot_by_repo(topic_rows)
        self.code_frequency_by_repo = rows_by_repo_week(code_frequency_rows)
        self.contributor_activity_by_repo = rows_by_repo_week(contributor_activity_rows)
        self.growth = growth
        self.community = latest_repo_community_profiles(metric_rows)
