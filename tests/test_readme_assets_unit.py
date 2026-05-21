from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from dashboard_action import run


import readme_assets as assets  # noqa: E402

_ = run


def test_build_readme_asset_data_aggregates_and_limits_chart_inputs() -> None:
    start = date(2026, 1, 1)
    daily_rows = [
        {
            "ts": (start + timedelta(days=offset)).isoformat(),
            "views_count": str(offset + 1),
        }
        for offset in range(95)
    ]
    latest_date = (start + timedelta(days=94)).isoformat()
    daily_rows.extend([
        {"ts": latest_date, "views_count": "5"},
        {"ts": latest_date, "views_count": "7"},
    ])
    per_repo = [
        {"repo": f"demo/repo-{idx}", "total_views": idx}
        for idx in range(12)
    ]
    totals = {"total_views": 123, "repos": ["demo/repo-0"]}

    data = assets.build_readme_asset_data(daily_rows, per_repo, totals=totals)

    assert data["daily_30_dates"] == [
        (start + timedelta(days=offset)).isoformat()
        for offset in range(65, 95)
    ]
    assert data["daily_30_views"][-1] == 95 + 5 + 7
    assert data["daily_90_dates"][0] == "2026-01-06"
    assert len(data["daily_90_dates"]) == 90
    assert data["top_repo_labels"] == [f"demo/repo-{idx}" for idx in range(10)]
    assert data["top_repo_views"] == list(range(10))
    assert data["share_repo_labels"] == [f"demo/repo-{idx}" for idx in range(6)]
    assert data["share_repo_views"] == list(range(6))
    assert data["totals"] is totals


def test_write_svg_pair_writes_dark_and_light_variant_paths(tmp_path: Path) -> None:
    calls: list[tuple[assets.Theme, tuple[object, ...], dict[str, object]]] = []

    def fake_generator(
        *args: object,
        theme: assets.Theme,
        **kwargs: object,
    ) -> str:
        calls.append((theme, args, kwargs))
        return f"<svg>{theme.bg}:{args}:{kwargs}</svg>"

    dark_path, light_path = assets._write_svg_pair(
        tmp_path,
        "sparkline",
        fake_generator,
        [1, 2, 3],
        dates=["2026-01-01", "2026-01-02"],
    )

    assert dark_path == tmp_path / "sparkline.svg"
    assert light_path == tmp_path / "sparkline-light.svg"
    assert dark_path.read_text(encoding="utf-8").startswith(f"<svg>{assets.DARK.bg}")
    assert light_path.read_text(encoding="utf-8").startswith(f"<svg>{assets.LIGHT.bg}")
    assert calls == [
        (assets.DARK, ([1, 2, 3],), {"dates": ["2026-01-01", "2026-01-02"]}),
        (assets.LIGHT, ([1, 2, 3],), {"dates": ["2026-01-01", "2026-01-02"]}),
    ]


def test_write_readme_svg_assets_creates_expected_dark_and_light_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: dict[str, list[dict[str, Any]]] = {}

    def stub(name: str) -> Callable[..., str]:
        def _generator(
            *args: object,
            theme: assets.Theme,
            **kwargs: object,
        ) -> str:
            calls.setdefault(name, []).append({
                "args": args,
                "kwargs": kwargs,
                "theme": theme,
            })
            return f"<svg>{name}:{theme.bg}</svg>"

        return _generator

    monkeypatch.setattr(assets, "svg_hero_stats", stub("hero"))
    monkeypatch.setattr(assets, "svg_sparkline", stub("sparkline"))
    monkeypatch.setattr(assets, "svg_bar_chart", stub("bar_chart"))
    monkeypatch.setattr(assets, "svg_activity_graph", stub("activity"))
    monkeypatch.setattr(assets, "svg_donut_chart", stub("donut"))

    output_dir = tmp_path / "nested" / "assets"
    asset_data = {
        "daily_30_dates": ["2026-01-01", "2026-01-02"],
        "daily_30_views": [4, 9],
        "daily_90_dates": ["2026-01-01"],
        "daily_90_views": [4],
        "top_repo_labels": ["demo/alpha"],
        "top_repo_views": [9],
        "share_repo_labels": ["demo/alpha"],
        "share_repo_views": [9],
        "totals": {
            "total_views": 15,
            "total_uniques": 8,
            "total_clones": 5,
            "total_clone_uniques": 3,
            "repos": ["demo/alpha", "demo/beta"],
            "days_tracked": 2,
        },
    }

    returned = assets.write_readme_svg_assets(str(output_dir), asset_data)

    assert returned == {
        key: output_dir / filename
        for key, filename in assets.README_ASSET_FILENAMES.items()
    }
    for key, filename in assets.README_ASSET_FILENAMES.items():
        dark_path = output_dir / filename
        light_path = output_dir / assets._light_filename(filename)
        assert dark_path.read_text(encoding="utf-8") == f"<svg>{key}:{assets.DARK.bg}</svg>"
        assert light_path.read_text(encoding="utf-8") == f"<svg>{key}:{assets.LIGHT.bg}</svg>"

    assert calls["hero"][0]["kwargs"] == {
        "total_views": 15,
        "total_uniques": 8,
        "total_clones": 5,
        "total_clone_uniques": 3,
        "repo_count": 2,
        "days_tracked": 2,
    }
    assert calls["sparkline"][0]["args"] == ([4, 9],)
    assert calls["sparkline"][0]["kwargs"] == {
        "dates": ["2026-01-01", "2026-01-02"],
    }
    assert calls["bar_chart"][0]["args"] == (["demo/alpha"], [9])
    assert calls["activity"][0]["args"] == (["2026-01-01"], [4])
    assert calls["donut"][0]["args"] == (["demo/alpha"], [9])
    assert all(call["theme"] is assets.DARK for call_list in calls.values() for call in call_list[::2])
    assert all(call["theme"] is assets.LIGHT for call_list in calls.values() for call in call_list[1::2])


def test_write_readme_svg_assets_defaults_missing_totals(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    hero_kwargs: list[dict[str, object]] = []

    def fake_hero(*_args: object, theme: assets.Theme, **kwargs: object) -> str:
        hero_kwargs.append(kwargs)
        return f"<svg>hero:{theme.bg}</svg>"

    monkeypatch.setattr(assets, "svg_hero_stats", fake_hero)
    monkeypatch.setattr(assets, "svg_sparkline", lambda *args, theme, **kwargs: "<svg />")
    monkeypatch.setattr(assets, "svg_bar_chart", lambda *args, theme, **kwargs: "<svg />")
    monkeypatch.setattr(assets, "svg_activity_graph", lambda *args, theme, **kwargs: "<svg />")
    monkeypatch.setattr(assets, "svg_donut_chart", lambda *args, theme, **kwargs: "<svg />")

    assets.write_readme_svg_assets(
        tmp_path,
        {
            "daily_30_dates": [],
            "daily_30_views": [],
            "daily_90_dates": [],
            "daily_90_views": [],
            "top_repo_labels": [],
            "top_repo_views": [],
            "share_repo_labels": [],
            "share_repo_views": [],
        },
    )

    assert hero_kwargs[0] == {
        "total_views": 0,
        "total_uniques": 0,
        "total_clones": 0,
        "total_clone_uniques": 0,
        "repo_count": 0,
        "days_tracked": 0,
    }
