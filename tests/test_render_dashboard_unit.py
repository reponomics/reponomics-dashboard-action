from __future__ import annotations

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
