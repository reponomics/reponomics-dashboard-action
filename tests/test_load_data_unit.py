from __future__ import annotations

import os
from pathlib import Path

import pytest

from traffic_report_action import run


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


def test_repo_metric_deltas_ignore_unobserved_counter_baselines() -> None:
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


def test_spike_candidate_detects_latest_spike_after_stable_baseline() -> None:
    assert load_data._spike_candidate("demo/app", "views", [10] * 7) is None

    candidate = load_data._spike_candidate("demo/app", "views", [10] * 7 + [40])

    assert candidate is not None
    assert candidate["direction"] == "spiked"
    assert candidate["baseline"] == 10
    assert candidate["delta"] == 30


def test_compute_momentum_handles_rows_without_parseable_dates() -> None:
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
