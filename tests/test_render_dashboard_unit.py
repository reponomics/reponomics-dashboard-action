from __future__ import annotations

import json

from dashboard_action import run


render_dashboard = run.render_dashboard


def test_pad_metric_series_appends_only_trailing_unreported_dates() -> None:
    dates, series = render_dashboard._pad_metric_series(
        ["2026-06-01", "2026-06-03"],
        {"views": [10, 30], "clones": [1, 3]},
        "2026-06-05",
    )

    assert dates == ["2026-06-01", "2026-06-03", "2026-06-04", "2026-06-05"]
    assert series == {
        "views": [10, 30, None, None],
        "clones": [1, 3, None, None],
    }


def test_standalone_dashboard_json_is_script_safe() -> None:
    title = "</script><script>alert('x')</script>"
    dashboard_data = {
        "summary": {
            "generated_at": "2026-06-14T12:00:00Z",
            "totals": {
                "repo_count": 1,
                "total_views": 0,
                "total_uniques": 0,
                "total_clones": 0,
                "total_clone_uniques": 0,
                "days_tracked": 1,
            },
        },
        "event_graph": {
            "repos": [
                {
                    "repo": "demo/app",
                    "events": [{"title": title}],
                }
            ]
        },
    }

    rendered = render_dashboard.dashboard_html.build_public_html(dashboard_data, "")
    marker = '<script id="plaintext-dashboard-data" type="application/json">'
    start = rendered.index(marker) + len(marker)
    end = rendered.index("</script>", start)
    embedded_json = rendered[start:end]

    assert "</script>" not in embedded_json.lower()
    assert "\\u003c/script\\u003e" in embedded_json
    assert json.loads(embedded_json)["event_graph"]["repos"][0]["events"][0]["title"] == title


def test_event_graph_compacts_published_events_with_nearby_traffic() -> None:
    daily_rows = [
        {
            "repo": "demo/app",
            "ts": "2026-06-10",
            "views_count": "4",
            "views_uniques": "2",
        },
        {
            "repo": "demo/app",
            "ts": "2026-06-11",
            "views_count": "6",
            "views_uniques": "3",
        },
        {
            "repo": "demo/hidden",
            "ts": "2026-06-11",
            "views_count": "90",
            "views_uniques": "45",
        },
    ]
    event_rows = [
        {
            "repo": "demo/app",
            "event_id": "commit:a",
            "event_date": "2026-06-09",
            "event_type": "commit",
            "classification": "docs",
            "title": "Document install flow",
            "primary_sha": "abc123456789",
            "magnitude": "9",
        },
        {
            "repo": "demo/app",
            "event_id": "release:b",
            "event_date": "2026-06-11",
            "event_type": "release",
            "classification": "release",
            "title": "v1.2.0",
            "magnitude": "4",
        },
        {
            "repo": "demo/hidden",
            "event_id": "commit:hidden",
            "event_date": "2026-06-11",
            "event_type": "commit",
            "title": "Private work",
        },
    ]

    graph = render_dashboard._build_event_graph(
        event_rows,
        daily_rows,
        [{"repo": "demo/app"}],
        per_repo_limit=2,
    )

    assert graph["event_count"] == 2
    assert graph["repos"][0]["repo"] == "demo/app"
    assert [event["id"] for event in graph["repos"][0]["events"]] == [
        "commit:a",
        "release:b",
    ]
    assert graph["repos"][0]["events"][0]["traffic"] == {
        "nearby_views": 4,
        "nearby_visitors": 2,
        "event_day_views": 0,
    }
    assert graph["repos"][0]["events"][1]["traffic"] == {
        "nearby_views": 10,
        "nearby_visitors": 5,
        "event_day_views": 6,
    }
