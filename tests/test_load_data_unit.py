from __future__ import annotations

import os
from pathlib import Path

import pytest

from dashboard_action import run


load_data = run.load_data


def _daily_row(
    repo: str,
    ts: str,
    views: str | int,
    uniques: str | int = 0,
    clones: str | int = 0,
    clone_uniques: str | int = 0,
) -> dict[str, str]:
    return {
        "repo": repo,
        "ts": ts,
        "views_count": str(views),
        "views_uniques": str(uniques),
        "clones_count": str(clones),
        "clones_uniques": str(clone_uniques),
    }


def _metric_row(
    repo: str,
    ts: str,
    stars: str | int,
    subscribers: str | int,
    forks: str | int,
    captured_at: str | None = None,
) -> dict[str, str]:
    return {
        "repo": repo,
        "ts": ts,
        "captured_at": captured_at or f"{ts}T12:00:00Z",
        "stargazers_count": str(stars),
        "subscribers_count": str(subscribers),
        "forks_count": str(forks),
    }


def _status_row(
    repo: str,
    captured_at: str,
    status: str,
    *,
    metric_source: str = "repo-detail",
) -> dict[str, str]:
    return {
        "repo": repo,
        "ts": captured_at[:10],
        "captured_at": captured_at,
        "status": status,
        "metric_source": metric_source,
    }


def test_load_daily_falls_back_to_legacy_log_and_filters_excluded_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def read_csv(path: str) -> list[dict[str, str]]:
        calls.append(os.path.basename(path))
        if path.endswith("traffic-daily.csv"):
            return []
        return [
            _daily_row("demo/public", "2026-05-01", 8, 3),
            _daily_row("demo/private", "2026-05-01", 99, 50),
        ]

    monkeypatch.setattr(load_data.storage, "read_csv", read_csv)
    monkeypatch.setattr(
        load_data,
        "load_repo_config",
        lambda: {"exclude_repos": ["demo/private"]},
    )

    assert load_data.load_daily(str(tmp_path)) == [
        _daily_row("demo/public", "2026-05-01", 8, 3)
    ]
    assert calls == ["traffic-daily.csv", "traffic-log.csv"]


def test_csv_loaders_read_expected_files_and_preserve_rows_without_exclusions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    rows_by_file = {
        "traffic-referrers.csv": [{"repo": "demo/app", "referrer": "github.com"}],
        "traffic-paths.csv": [{"repo": "demo/app", "path": "/demo/app"}],
        "repo-metrics.csv": [_metric_row("demo/app", "2026-05-01", 8, 2, 1)],
        "collection-status.csv": [
            _status_row("demo/app", "2026-05-01T12:00:00Z", "ok_with_data")
        ],
        "collection-days.csv": [{"ts": "2026-05-01", "status": "healthy"}],
        "traffic-coverage.csv": [
            {
                "repo": "demo/app",
                "ts": "2026-05-01",
                "coverage_state": "reported",
            }
        ],
    }

    def read_csv(path: str) -> list[dict[str, str]]:
        return rows_by_file[os.path.basename(path)]

    monkeypatch.setattr(load_data.storage, "read_csv", read_csv)
    monkeypatch.setattr(load_data, "load_repo_config", lambda: {})

    assert load_data.load_referrers(str(tmp_path)) is rows_by_file["traffic-referrers.csv"]
    assert load_data.load_paths(str(tmp_path)) is rows_by_file["traffic-paths.csv"]
    assert load_data.load_repo_metrics(str(tmp_path)) is rows_by_file["repo-metrics.csv"]
    assert load_data.load_collection_status(str(tmp_path)) is rows_by_file[
        "collection-status.csv"
    ]
    assert load_data.load_collection_days(str(tmp_path)) is rows_by_file[
        "collection-days.csv"
    ]
    assert load_data.load_traffic_coverage(str(tmp_path)) is rows_by_file[
        "traffic-coverage.csv"
    ]


def test_load_daily_uses_default_data_dir_when_not_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(load_data.storage, "DATA_DIR", "/tmp/reponomics-data")
    monkeypatch.setattr(load_data, "load_repo_config", lambda: {})

    seen_paths: list[str] = []

    def read_csv(path: str) -> list[dict[str, str]]:
        seen_paths.append(path)
        return [_daily_row("demo/app", "2026-05-01", 1)]

    monkeypatch.setattr(load_data.storage, "read_csv", read_csv)

    assert load_data.load_daily() == [_daily_row("demo/app", "2026-05-01", 1)]
    assert seen_paths == ["/tmp/reponomics-data/traffic-daily.csv"]


def test_latest_repo_metrics_and_aggregate_totals_use_latest_capture() -> None:
    rows = [
        _metric_row("demo/app", "2026-05-01", 8, 2, 1, "2026-05-01T09:00:00Z"),
        _metric_row("demo/app", "2026-05-01", 10, 3, 2, "2026-05-01T18:00:00Z"),
        _metric_row("demo/lib", "2026-05-01", "", "", "", "2026-05-01T12:00:00Z"),
        _metric_row("", "2026-05-01", 99, 99, 99, "2026-05-01T12:00:00Z"),
    ]

    latest = load_data.latest_repo_metrics(rows)
    assert latest["demo/app"]["stargazers_count"] == 10
    assert latest["demo/lib"]["subscribers_count"] == 0

    assert load_data.aggregate_repo_metrics(rows) == {
        "repos": {"demo/app", "demo/lib"},
        "total_stargazers": 10,
        "total_stars": 10,
        "total_subscribers": 3,
        "total_forks": 2,
    }


def test_latest_repo_metadata_uses_latest_capture() -> None:
    rows = [
        {
            **_metric_row("demo/app", "2026-05-01", 8, 2, 1, "2026-05-01T09:00:00Z"),
            "created_at": "2026-01-01T00:00:00Z",
            "pushed_at": "2026-05-01T08:00:00Z",
            "updated_at": "2026-05-01T08:30:00Z",
        },
        {
            **_metric_row("demo/app", "2026-05-01", 10, 3, 2, "2026-05-01T18:00:00Z"),
            "created_at": "2026-01-01T00:00:00Z",
            "pushed_at": "2026-05-01T17:00:00Z",
            "updated_at": "2026-05-01T17:30:00Z",
        },
        {
            **_metric_row("", "2026-05-01", 99, 99, 99, "2026-05-01T12:00:00Z"),
            "updated_at": "2026-05-01T12:00:00Z",
        },
    ]

    assert load_data.latest_repo_metadata(rows) == {
        "demo/app": {
            "captured_at": "2026-05-01T18:00:00Z",
            "created_at": "2026-01-01T00:00:00Z",
            "pushed_at": "2026-05-01T17:00:00Z",
            "updated_at": "2026-05-01T17:30:00Z",
        }
    }


def test_repo_growth_series_projects_normalized_daily_counters() -> None:
    rows = [
        _metric_row("demo/app", "2026-05-02", 10, 3, 2),
        _metric_row("demo/app", "2026-05-01", 8, 2, 1),
    ]

    assert load_data.repo_growth_series(rows) == {
        "demo/app": {
            "dates": ["2026-05-01", "2026-05-02"],
            "stargazers": [8, 10],
            "subscribers": [2, 3],
            "forks": [1, 2],
            "samples": 2,
        }
    }


def test_collection_quality_empty_and_days_skip_incomplete_rows() -> None:
    assert load_data.collection_quality([]) == {
        "available": False,
        "status": "unknown",
        "message": "",
        "latest_captured_at": "",
        "tracked_repos": 0,
        "with_data_repos": 0,
        "zero_traffic_repos": 0,
        "skipped_repos": 0,
        "error_repos": 0,
        "coverage_ratio": 1.0,
        "has_collection_gaps": False,
        "repos": [],
        "days": [],
    }
    assert load_data.collection_quality_days([]) == []
    assert load_data.collection_quality_days(
        [
            {"repo": "demo/app", "ts": "", "captured_at": "2026-05-01T12:00:00Z"},
            {"repo": "demo/lib", "ts": "2026-05-01", "captured_at": ""},
        ]
    ) == []


def test_collection_quality_reports_gaps_for_skipped_and_error_repos() -> None:
    quality = load_data.collection_quality(
        [
            _status_row("demo/one", "2026-05-10T12:00:00Z", "ok_with_data"),
            _status_row("demo/two", "2026-05-10T12:00:00Z", "skipped_unavailable"),
            _status_row("demo/three", "2026-05-10T12:00:00Z", "error"),
            _status_row("demo/old", "2026-05-09T12:00:00Z", "ok_with_data"),
        ]
    )

    assert quality["available"] is True
    assert quality["status"] == "gaps_detected"
    assert quality["has_collection_gaps"] is True
    assert quality["tracked_repos"] == 3
    assert quality["with_data_repos"] == 1
    assert quality["zero_traffic_repos"] == 0
    assert quality["skipped_repos"] == 1
    assert quality["error_repos"] == 1
    assert quality["coverage_ratio"] == pytest.approx(1 / 3, rel=0, abs=1e-4)
    assert "Collection gaps detected" in quality["message"]
    assert [row["repo"] for row in quality["repos"]] == ["demo/three", "demo/two"]


def test_collection_quality_reports_all_zero_without_collection_gaps() -> None:
    quality = load_data.collection_quality(
        [
            _status_row("demo/one", "2026-05-10T12:00:00Z", "ok_zero_data"),
            _status_row("demo/two", "2026-05-10T12:00:00Z", "ok_zero_data"),
        ]
    )

    assert quality["status"] == "all_zero"
    assert quality["has_collection_gaps"] is False
    assert quality["tracked_repos"] == 2
    assert quality["with_data_repos"] == 0
    assert quality["zero_traffic_repos"] == 2
    assert "reported zero traffic" in quality["message"]


def test_collection_quality_days_uses_latest_run_per_day() -> None:
    days = load_data.collection_quality_days(
        [
            _status_row("demo/one", "2026-05-10T08:00:00Z", "ok_with_data"),
            _status_row("demo/two", "2026-05-10T08:00:00Z", "ok_with_data"),
            _status_row("demo/one", "2026-05-10T12:00:00Z", "ok_zero_data"),
            _status_row("demo/two", "2026-05-10T12:00:00Z", "skipped_unavailable"),
            _status_row("demo/one", "2026-05-11T12:00:00Z", "ok_with_data"),
        ]
    )

    assert [day["date"] for day in days] == ["2026-05-10", "2026-05-11"]
    assert days[0]["run_count"] == 2
    assert days[0]["status"] == "gaps_detected"
    assert days[0]["with_data_repos"] == 0
    assert days[0]["zero_traffic_repos"] == 1
    assert days[0]["skipped_repos"] == 1
    assert days[0]["repos"] == [
        {
            "repo": "demo/one",
            "status": "ok_zero_data",
            "metric_source": "repo-detail",
            "error_type": "",
        },
        {
            "repo": "demo/two",
            "status": "skipped_unavailable",
            "metric_source": "repo-detail",
            "error_type": "",
        },
    ]
    assert days[1]["run_count"] == 1
    assert days[1]["status"] == "healthy"


def test_collection_quality_uses_materialized_no_run_days() -> None:
    quality = load_data.collection_quality(
        [_status_row("demo/app", "2026-05-11T12:00:00Z", "ok_with_data")],
        [
            {
                "ts": "2026-05-10",
                "status": "no_run",
                "latest_captured_at": "",
                "run_count": "0",
                "tracked_repos": "0",
                "with_data_repos": "0",
                "zero_traffic_repos": "0",
                "skipped_repos": "0",
                "error_repos": "0",
            },
            {
                "ts": "2026-05-11",
                "status": "healthy",
                "latest_captured_at": "2026-05-11T12:00:00Z",
                "run_count": "1",
                "tracked_repos": "1",
                "with_data_repos": "1",
                "zero_traffic_repos": "0",
                "skipped_repos": "0",
                "error_repos": "0",
            },
        ],
    )

    assert [day["date"] for day in quality["days"]] == ["2026-05-10", "2026-05-11"]
    assert quality["days"][0]["status"] == "no_run"


def test_traffic_reporting_summary_ranges_upstream_lag() -> None:
    summary = load_data.traffic_reporting_summary(
        [
            {
                "repo": "demo/app",
                "ts": "2026-06-08",
                "coverage_state": "reported",
            },
            {
                "repo": "demo/app",
                "ts": "2026-06-09",
                "coverage_state": "not_reported_by_api",
            },
            {
                "repo": "demo/app",
                "ts": "2026-06-10",
                "coverage_state": "not_reported_by_api",
            },
            {
                "repo": "demo/lib",
                "ts": "2026-06-10",
                "coverage_state": "collection_failed",
            },
        ],
        [
            {"ts": "2026-06-08", "status": "healthy"},
            {"ts": "2026-06-09", "status": "healthy"},
            {"ts": "2026-06-10", "status": "healthy"},
        ],
    )

    assert summary["latest_collection_date"] == "2026-06-10"
    assert summary["latest_reported_traffic_date"] == "2026-06-08"
    assert summary["lag_days"] == 2
    assert summary["unreported_start_date"] == "2026-06-09"
    assert summary["unreported_end_date"] == "2026-06-10"
    assert summary["unreported_days"] == 2
    assert summary["affected_repos"] == ["demo/app"]
    assert summary["unreported_ranges"] == [
        {"repo": "demo/app", "start": "2026-06-09", "end": "2026-06-10", "days": 2}
    ]


def test_traffic_reporting_summary_lag_uses_affected_dates_not_global_latest() -> None:
    summary = load_data.traffic_reporting_summary(
        [
            {
                "repo": "demo/current",
                "ts": "2026-06-11",
                "coverage_state": "reported",
            },
            {
                "repo": "demo/lagging",
                "ts": "2026-06-08",
                "coverage_state": "reported",
            },
            {
                "repo": "demo/lagging",
                "ts": "2026-06-09",
                "coverage_state": "not_reported_by_api",
            },
            {
                "repo": "demo/lagging",
                "ts": "2026-06-10",
                "coverage_state": "not_reported_by_api",
            },
            {
                "repo": "demo/lagging",
                "ts": "2026-06-11",
                "coverage_state": "not_reported_by_api",
            },
        ],
        [
            {"ts": "2026-06-11", "status": "healthy"},
        ],
    )

    assert summary["latest_collection_date"] == "2026-06-11"
    assert summary["latest_reported_traffic_date"] == "2026-06-11"
    assert summary["has_lag"] is True
    assert summary["lag_days"] == 3
    assert summary["unreported_start_date"] == "2026-06-09"
    assert summary["unreported_end_date"] == "2026-06-11"
    assert summary["affected_repos"] == ["demo/lagging"]
    assert summary["unreported_ranges"] == [
        {
            "repo": "demo/lagging",
            "start": "2026-06-09",
            "end": "2026-06-11",
            "days": 3,
        }
    ]


def test_latest_repo_metrics_per_day_normalizes_blank_counters_and_skips_incomplete_rows() -> None:
    rows = [
        _metric_row("", "2026-05-01", 1, 1, 1),
        _metric_row("demo/app", "", 1, 1, 1),
        _metric_row("demo/app", "2026-05-01", 8, 2, 1, "2026-05-01T09:00:00Z"),
        _metric_row("demo/app", "2026-05-01", 10, "", 2, "2026-05-01T18:00:00Z"),
        _metric_row("demo/app", "2026-05-02", 11, 5, "", "2026-05-02T12:00:00Z"),
    ]

    per_day = load_data.latest_repo_metrics_per_day(rows)

    assert list(per_day) == ["demo/app"]
    assert per_day["demo/app"] == [
        {
            "repo": "demo/app",
            "ts": "2026-05-01",
            "captured_at": "2026-05-01T18:00:00Z",
            "stargazers_count": 10,
            "subscribers_count": 0,
            "forks_count": 2,
            "stargazers_count_observed": True,
            "subscribers_count_observed": False,
            "forks_count_observed": True,
        },
        {
            "repo": "demo/app",
            "ts": "2026-05-02",
            "captured_at": "2026-05-02T12:00:00Z",
            "stargazers_count": 11,
            "subscribers_count": 5,
            "forks_count": 0,
            "stargazers_count_observed": True,
            "subscribers_count_observed": True,
            "forks_count_observed": False,
        },
    ]


def test_latest_repo_community_profiles_prefers_latest_capture_and_normalizes_types() -> None:
    rows = [
        {
            "repo": "demo/app",
            "captured_at": "2026-05-01T10:00:00Z",
            "community_health_percentage": "",
            "community_documentation": "",
            "community_updated_at": "",
            "community_content_reports_enabled": "",
            "community_has_code_of_conduct": "",
            "community_has_contributing": "",
            "community_has_issue_template": "",
            "community_has_pull_request_template": "",
            "community_has_readme": "",
            "community_has_license": "",
        },
        {
            "repo": "demo/app",
            "captured_at": "2026-05-02T10:00:00Z",
            "community_health_percentage": "71",
            "community_documentation": "https://github.com/docs",
            "community_updated_at": "2026-05-02T09:00:00Z",
            "community_content_reports_enabled": "True",
            "community_has_code_of_conduct": "False",
            "community_has_contributing": "True",
            "community_has_issue_template": "",
            "community_has_pull_request_template": "true",
            "community_has_readme": "1",
            "community_has_license": "0",
        },
    ]

    profiles = load_data.latest_repo_community_profiles(rows)

    assert profiles == {
        "demo/app": {
            "captured_at": "2026-05-02T10:00:00Z",
            "available": True,
            "health_percentage": 71,
            "documentation": "https://github.com/docs",
            "updated_at": "2026-05-02T09:00:00Z",
            "content_reports_enabled": True,
            "has_code_of_conduct": False,
            "has_contributing": True,
            "has_issue_template": None,
            "has_pull_request_template": True,
            "has_readme": True,
            "has_license": False,
        }
    }


def test_repo_metric_deltas_ignore_unobserved_counter_baselines() -> None:
    assert load_data.repo_metric_deltas([]) == {
        "repos": {},
        "total_stargazers_delta": 0,
        "total_stars_delta": 0,
        "total_subscribers_delta": 0,
        "total_forks_delta": 0,
    }

    rows = [
        _metric_row("demo/app", "2026-05-01", 10, "", ""),
        _metric_row("demo/app", "2026-05-02", 11, 4, ""),
        _metric_row("demo/app", "2026-05-03", 13, 7, 2),
    ]

    deltas = load_data.repo_metric_deltas(rows, recent_days=3)

    assert deltas["repos"]["demo/app"]["stargazers_delta"] == 3
    assert deltas["repos"]["demo/app"]["subscribers_delta"] == 3
    assert deltas["repos"]["demo/app"]["forks_delta"] == 0
    assert deltas["total_stargazers_delta"] == 3
    assert deltas["total_subscribers_delta"] == 3
    assert deltas["total_forks_delta"] == 0


def test_growth_analytics_combines_current_counters_deltas_and_traffic_ratios() -> None:
    daily_rows = [
        _daily_row("demo/app", "2026-05-01", 4, 0, 10, 5),
        _daily_row("demo/app", "2026-05-02", 20, 4, 3, 2),
        _daily_row("demo/lib", "2026-05-02", 4, 3, 1, 1),
    ]
    metric_rows = [
        _metric_row("demo/app", "2026-05-01", 10, 2, 1),
        _metric_row("demo/app", "2026-05-02", 14, 5, 3),
        _metric_row("demo/metrics-only", "2026-05-02", 1, 1, 1),
    ]

    growth = load_data.growth_analytics(daily_rows, metric_rows, recent_days=2)

    assert growth["cutoff"] == "2026-05-01"
    assert set(growth["per_repo"]) == {"demo/app", "demo/lib", "demo/metrics-only"}
    assert growth["per_repo"]["demo/app"]["traffic"]["views"] == 24
    assert growth["per_repo"]["demo/app"]["conversion"]["stargazers"] == {
        "value": 4 / 24,
        "denominator": 24,
        "denominator_metric": "views",
    }
    assert growth["per_repo"]["demo/lib"]["conversion"]["stargazers"] == {
        "value": None,
        "denominator": 0,
        "denominator_metric": None,
    }
    assert growth["per_repo"]["demo/metrics-only"]["traffic"] == {
        "views": 0,
        "uniques": 0,
        "clones": 0,
        "clone_uniques": 0,
        "sample_count": 0,
    }
    assert growth["totals"]["total_stargazers_delta"] == 4


def test_traffic_totals_by_repo_applies_cutoff_and_skips_missing_repo() -> None:
    totals = load_data._traffic_totals_by_repo(
        [
            _daily_row("demo/app", "2026-05-01", 100, 50, 12, 6),
            _daily_row("", "2026-05-02", 100, 50, 12, 6),
            _daily_row("demo/app", "2026-05-02", "8", "3", "", ""),
            _daily_row("demo/lib", "2026-05-03", 4, 2, 1, 1),
        ],
        cutoff="2026-05-02",
    )

    assert totals == {
        "demo/app": {
            "views": 8,
            "uniques": 3,
            "clones": 0,
            "clone_uniques": 0,
            "sample_count": 1,
        },
        "demo/lib": {
            "views": 4,
            "uniques": 2,
            "clones": 1,
            "clone_uniques": 1,
            "sample_count": 1,
        },
    }


def test_aggregate_helpers_sum_daily_rows_by_total_date_and_repo() -> None:
    rows = [
        _daily_row("demo/app", "2026-05-01", 8, 3, 2, 1),
        _daily_row("demo/app", "2026-05-02", 4, 2, 1, 1),
        _daily_row("demo/lib", "2026-05-01", 20, 10, 5, 2),
    ]

    assert load_data.aggregate_totals(rows) == {
        "repos": {"demo/app", "demo/lib"},
        "total_views": 32,
        "total_uniques": 15,
        "total_clones": 8,
        "total_clone_uniques": 4,
        "days_tracked": 2,
    }

    dates, series = load_data.aggregate_by_date(rows)
    assert dates == ["2026-05-01", "2026-05-02"]
    assert series == {
        "views": [28, 4],
        "uniques": [13, 2],
        "clones": [7, 1],
        "clone_uniques": [3, 1],
    }

    assert load_data.aggregate_per_repo(rows) == [
        {
            "repo": "demo/lib",
            "total_views": 20,
            "total_uniques": 10,
            "total_clones": 5,
            "total_clone_uniques": 2,
        },
        {
            "repo": "demo/app",
            "total_views": 12,
            "total_uniques": 5,
            "total_clones": 3,
            "total_clone_uniques": 2,
        },
    ]


def test_top_referrers_uses_latest_snapshot_per_repo_without_overcounting() -> None:
    rows = [
        {
            "repo": "demo/app",
            "captured_at": "2026-05-01T12:00:00Z",
            "referrer": "github.com",
            "count": "100",
            "uniques": "40",
        },
        {
            "repo": "demo/app",
            "captured_at": "2026-05-02T12:00:00Z",
            "referrer": "github.com",
            "count": "5",
            "uniques": "3",
        },
        {
            "repo": "demo/lib",
            "captured_at": "2026-05-01T12:00:00Z",
            "referrer": "github.com",
            "count": "7",
            "uniques": "4",
        },
    ]

    assert load_data.top_referrers([]) == []
    assert load_data.top_referrers(rows) == [
        {"referrer": "github.com", "count": 12, "uniques": 7}
    ]


def test_top_paths_labels_repository_overview_and_falls_back_to_path() -> None:
    rows = [
        {
            "repo": "demo/app",
            "captured_at": "2026-05-02T12:00:00Z",
            "path": "/demo/app",
            "title": "ignored root title",
            "count": "8",
            "uniques": "4",
        },
        {
            "repo": "demo/app",
            "captured_at": "2026-05-02T12:00:00Z",
            "path": "/demo/app/issues",
            "title": "",
            "count": "3",
            "uniques": "2",
        },
    ]

    assert load_data.top_paths(rows) == [
        {
            "repo": "demo/app",
            "path": "/demo/app",
            "title": "ignored root title",
            "content": "Repository overview",
            "count": 8,
            "uniques": 4,
        },
        {
            "repo": "demo/app",
            "path": "/demo/app/issues",
            "title": "",
            "content": "/demo/app/issues",
            "count": 3,
            "uniques": 2,
        },
    ]


def test_window_change_candidate_handles_new_activity_and_small_noise() -> None:
    assert load_data._window_change_candidate("demo/app", "views", [1, 2, 3, 4, 5], 10) is None
    assert load_data._window_change_candidate("demo/app", "views", [2, 2, 2, 2, 2, 2], 10) is None
    assert load_data._window_change_candidate("demo/app", "views", [0, 0, 0, 1, 0, 0], 10) is None

    candidate = load_data._window_change_candidate(
        "demo/app",
        "views",
        [0, 0, 0, 2, 2, 2],
        10,
    )

    assert candidate is not None
    assert candidate["window_days"] == 3
    assert candidate["prior"] == 0
    assert candidate["current"] == 6
    assert candidate["delta"] == 6
    assert candidate["pct"] is None
    assert "new activity" in candidate["text"]

    drop = load_data._window_change_candidate(
        "demo/app",
        "views",
        [10, 10, 10, 4, 4, 4],
        10,
    )

    assert drop is not None
    assert drop["pct"] == -60.0
    assert drop["delta"] == -18


def test_spike_candidate_detects_latest_spike_after_stable_baseline() -> None:
    assert load_data._spike_candidate("demo/app", "views", [10] * 6 + [12, 13]) is None

    assert load_data._spike_candidate("demo/app", "views", [10] * 7) is None

    candidate = load_data._spike_candidate("demo/app", "views", [10] * 7 + [40])

    assert candidate is not None
    assert candidate["direction"] == "spiked"
    assert candidate["baseline"] == 10
    assert candidate["delta"] == 30

    drop = load_data._spike_candidate("demo/app", "views", [30, 31, 29, 30, 31, 29, 30, 5])
    assert drop is not None
    assert drop["direction"] == "dropped"
    assert drop["delta"] == -25


def test_compute_momentum_handles_rows_without_parseable_dates() -> None:
    assert load_data.compute_momentum([]) == {
        "best_day": None,
        "streak_days": 0,
        "baseline": 0.0,
        "days_since_peak": None,
        "top_single_day": None,
    }

    no_dated_rows = [
        {"repo": "demo/app", "ts": "", "views_count": "7"},
        {"repo": "demo/lib", "views_count": "9"},
    ]

    assert load_data.compute_momentum(no_dated_rows) == {
        "best_day": None,
        "streak_days": 0,
        "baseline": 0.0,
        "days_since_peak": None,
        "top_single_day": None,
    }

    momentum = load_data.compute_momentum(
        [
            _daily_row("demo/app", "2026-05-01", 4),
            _daily_row("demo/app", "not-a-date", 9),
        ]
    )

    assert momentum["best_day"] == {"date": "not-a-date", "views": 9}
    assert momentum["days_since_peak"] is None


def test_compute_momentum_reports_peak_distance_and_top_single_day() -> None:
    momentum = load_data.compute_momentum(
        [
            _daily_row("demo/app", "2026-05-01", 4),
            _daily_row("demo/lib", "2026-05-01", 7),
            _daily_row("demo/app", "2026-05-02", 20),
            _daily_row("demo/app", "2026-05-03", 8),
        ]
    )

    assert momentum["best_day"] == {"date": "2026-05-02", "views": 20}
    assert momentum["days_since_peak"] == 1
    assert momentum["top_single_day"] == {
        "repo": "demo/app",
        "date": "2026-05-02",
        "views": 20,
    }


def test_growth_insight_candidates_cover_cross_signal_subtypes() -> None:
    growth = {
        "per_repo": {
            "demo/attention": {
                "traffic": {"views": 100, "uniques": 20, "clones": 0, "sample_count": 3},
                "deltas": {
                    "sample_count": 2,
                    "stargazers_delta": 0,
                    "subscribers_delta": 0,
                    "forks_delta": 0,
                },
                "conversion": {},
            },
            "demo/quiet": {
                "traffic": {"views": 20, "uniques": 5, "clones": 0, "sample_count": 3},
                "deltas": {
                    "sample_count": 2,
                    "stargazers_delta": 2,
                    "subscribers_delta": 0,
                    "forks_delta": 0,
                },
                "conversion": {},
            },
            "demo/clone": {
                "traffic": {"views": 40, "uniques": 8, "clones": 15, "sample_count": 3},
                "deltas": {
                    "sample_count": 2,
                    "stargazers_delta": 0,
                    "subscribers_delta": 0,
                    "forks_delta": 0,
                },
                "conversion": {},
            },
            "demo/fork": {
                "traffic": {"views": 60, "uniques": 20, "clones": 0, "sample_count": 3},
                "deltas": {
                    "sample_count": 2,
                    "stargazers_delta": 0,
                    "subscribers_delta": 0,
                    "forks_delta": 3,
                },
                "conversion": {"forks": {"denominator": 20, "value": 0.15}},
            },
            "demo/watchers": {
                "traffic": {"views": 60, "uniques": 20, "clones": 0, "sample_count": 3},
                "deltas": {
                    "sample_count": 2,
                    "stargazers_delta": 0,
                    "subscribers_delta": 4,
                    "forks_delta": 0,
                },
                "conversion": {"subscribers": {"denominator": 20, "value": 0.2}},
            },
            "demo/downstream": {
                "traffic": {"views": 20, "uniques": 6, "clones": 0, "sample_count": 3},
                "deltas": {
                    "sample_count": 2,
                    "stargazers_delta": 3,
                    "subscribers_delta": 0,
                    "forks_delta": 0,
                },
                "conversion": {},
            },
            "demo/negative": {
                "traffic": {"views": 0, "uniques": 0, "clones": 0, "sample_count": 0},
                "deltas": {
                    "sample_count": 2,
                    "stargazers_delta": -2,
                    "subscribers_delta": -1,
                    "forks_delta": -1,
                },
                "conversion": {},
            },
        }
    }

    assert load_data._growth_insight_candidates([], metric_rows=None) == []
    candidates = load_data._growth_insight_candidates([], growth=growth)
    subtypes = {candidate["subtype"] for candidate in candidates}

    assert {
        "high_attention_low_interest",
        "quiet_resonance",
        "clone_heavy_star_light",
        "fork_spike",
        "watcher_subscriber_spike",
        "traffic_without_downstream_growth",
        "downstream_without_traffic_spike",
        "negative_counter_movement",
    } <= subtypes


def test_actionable_insights_rank_and_diversify_text_and_structured_outputs() -> None:
    rows = [
        _daily_row("demo/app", "2026-05-01", 1, clones=0),
        _daily_row("demo/app", "2026-05-02", 1, clones=0),
        _daily_row("demo/app", "2026-05-03", 1, clones=0),
        _daily_row("demo/app", "2026-05-04", 10, clones=2),
        _daily_row("demo/app", "2026-05-05", 10, clones=2),
        _daily_row("demo/app", "2026-05-06", 10, clones=2),
    ]

    insights = load_data.actionable_insights(rows, 2)
    assert len(insights) == 2
    assert all("demo/app" in insight for insight in insights)
    assert load_data.actionable_insights(rows, limit=0) == []

    structured = load_data.actionable_insights_structured(rows, 2)
    assert len(structured) == 2
    assert all("score" not in insight for insight in structured)
    assert {insight["metric"] for insight in structured} == {"views", "clones"}
    assert load_data.actionable_insights_structured(rows, limit=0) == []
