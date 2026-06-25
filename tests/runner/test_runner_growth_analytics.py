from __future__ import annotations


from dashboard_action import run

from runner_support import (
    _daily_row,
    _metric_row,
)


def test_growth_analytics_totals_deltas_and_visitor_conversion() -> None:
    daily_rows = [
        _daily_row("demo/high", "2026-05-01", 40, 10, 4),
        _daily_row("demo/high", "2026-05-02", 60, 15, 6),
        _daily_row("demo/fallback", "2026-05-02", 12, 0, 1),
    ]
    metric_rows = [
        _metric_row("demo/high", "2026-05-01", 10, 2, 1),
        _metric_row("demo/high", "2026-05-02", 15, 5, 2),
        _metric_row("demo/fallback", "2026-05-01", 1, 0, 0),
        _metric_row("demo/fallback", "2026-05-02", 3, 0, 0),
    ]

    growth = run.load_data.growth_analytics(daily_rows, metric_rows, recent_days=2)

    assert growth["totals"]["total_stargazers"] == 18
    assert growth["totals"]["total_subscribers"] == 5
    assert growth["totals"]["total_forks"] == 2
    assert growth["totals"]["total_stargazers_delta"] == 7
    assert growth["totals"]["total_subscribers_delta"] == 3
    assert growth["totals"]["total_forks_delta"] == 1
    assert growth["per_repo"]["demo/high"]["conversion"]["stargazers"] == {
        "value": 0.2,
        "denominator": 25,
        "denominator_metric": "visitors",
    }
    assert growth["per_repo"]["demo/fallback"]["conversion"]["stargazers"] == {
        "value": 2 / 12,
        "denominator": 12,
        "denominator_metric": "views",
    }


def test_growth_series_uses_latest_repo_per_day_snapshot() -> None:
    metric_rows = [
        _metric_row("demo/reponomics", "2026-05-01", 10, 2, 1, "09:00:00Z"),
        _metric_row("demo/reponomics", "2026-05-01", 12, 3, 1, "18:00:00Z"),
        _metric_row("demo/reponomics", "2026-05-02", 13, 3, 2),
    ]

    series = run.load_data.repo_growth_series(metric_rows)

    assert series["demo/reponomics"]["dates"] == ["2026-05-01", "2026-05-02"]
    assert series["demo/reponomics"]["stargazers"] == [12, 13]
    assert series["demo/reponomics"]["subscribers"] == [3, 3]
    assert series["demo/reponomics"]["forks"] == [1, 2]


def test_growth_missing_history_has_zero_deltas_and_no_ratio() -> None:
    daily_rows = [_daily_row("demo/new", "2026-05-02", 4, 2)]
    metric_rows = [_metric_row("demo/new", "2026-05-02", 10, 1, 0)]

    growth = run.load_data.growth_analytics(daily_rows, metric_rows, recent_days=14)
    repo = growth["per_repo"]["demo/new"]

    assert repo["deltas"]["sample_count"] == 1
    assert repo["deltas"]["stargazers_delta"] == 0
    assert repo["deltas"]["subscribers_delta"] == 0
    assert repo["deltas"]["forks_delta"] == 0
    assert repo["conversion"]["stargazers"] == {
        "value": None,
        "denominator": 0,
        "denominator_metric": None,
    }
    assert run.load_data.actionable_insights(daily_rows, metric_rows) == []


def test_growth_deltas_ignore_migrated_blank_counter_baselines() -> None:
    daily_rows = [_daily_row("demo/reponomics", "2026-05-16", 80, 20, 4)]
    migrated = _metric_row("demo/reponomics", "2026-05-03", 43895, 0, 3751)
    migrated["subscribers_count"] = ""
    current = _metric_row("demo/reponomics", "2026-05-16", 43967, 298, 3766)

    growth = run.load_data.growth_analytics(daily_rows, [migrated, current], recent_days=14)
    repo = growth["per_repo"]["demo/reponomics"]

    assert repo["deltas"]["stars_delta"] == 72
    assert repo["deltas"]["subscribers_delta"] == 0
    assert repo["deltas"]["forks_delta"] == 15
    assert repo["deltas"]["current_subscribers"] == 298
    assert growth["totals"]["total_subscribers"] == 298
    assert growth["totals"]["total_subscribers_delta"] == 0


def test_growth_insights_select_top_defensible_candidate() -> None:
    daily_rows = []
    metric_rows = []
    for day in range(1, 5):
        ts = f"2026-05-0{day}"
        daily_rows.append(_daily_row("demo/attention", ts, 35, 12, 4))
        daily_rows.append(_daily_row("demo/tiny", ts, 1, 1, 0))
    metric_rows.extend(
        [
            _metric_row("demo/attention", "2026-05-01", 10, 2, 1),
            _metric_row("demo/attention", "2026-05-04", 10, 2, 1),
            _metric_row("demo/tiny", "2026-05-01", 0, 0, 0),
            _metric_row("demo/tiny", "2026-05-04", 1, 0, 0),
        ]
    )

    insights = run.load_data.actionable_insights_structured(
        daily_rows,
        metric_rows,
        limit=1,
    )

    assert len(insights) == 1
    assert insights[0]["repo"] == "demo/attention"
    assert insights[0]["subtype"] in {
        "high_attention_low_interest",
        "traffic_without_downstream_growth",
    }
