"""Shared deterministic dashboard data scenarios for renderer tests and labs."""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from functools import cached_property
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SCRIPTS_DIR = ROOT / "dashboard_action" / "runtime" / "scripts"
DEFAULT_FIXTURE_DATA_DIR = ROOT / "tests" / "fixtures" / "collection_quality_preview" / "data"

if str(RUNTIME_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SCRIPTS_DIR))

import load_data  # noqa: E402
import readme_assets  # noqa: E402
import storage  # noqa: E402
import traffic_reporting  # noqa: E402


@dataclass(frozen=True)
class ScenarioDataset:
    key: str
    title: str
    description: str
    daily_rows: list[dict[str, str]]
    referrer_rows: list[dict[str, str]]
    path_rows: list[dict[str, str]]
    metric_rows: list[dict[str, str]]
    status_rows: list[dict[str, str]]

    @cached_property
    def totals(self) -> dict[str, Any]:
        return load_data.aggregate_totals(self.daily_rows)

    @cached_property
    def per_repo(self) -> list[dict[str, Any]]:
        return load_data.aggregate_per_repo(self.daily_rows)

    @cached_property
    def readme_asset_data(self) -> dict[str, Any]:
        return readme_assets.build_readme_asset_data(
            self.daily_rows,
            self.per_repo,
            totals=self.totals,
        )

    @cached_property
    def top_referrers(self) -> list[dict[str, Any]]:
        return load_data.top_referrers(self.referrer_rows, limit=10)

    @cached_property
    def top_paths(self) -> list[dict[str, Any]]:
        return load_data.top_paths(self.path_rows, limit=10)

    @cached_property
    def growth(self) -> dict[str, Any]:
        return load_data.growth_analytics(self.daily_rows, self.metric_rows)

    @cached_property
    def collection_quality(self) -> dict[str, Any]:
        return load_data.collection_quality(self.status_rows)

    @cached_property
    def collection_day_rows(self) -> list[dict[str, Any]]:
        return traffic_reporting.collection_day_rows(self.status_rows)

    @cached_property
    def traffic_coverage_rows(self) -> list[dict[str, Any]]:
        return traffic_reporting.traffic_coverage_rows(self.daily_rows, self.status_rows)


def _row(
    repo: str,
    day: date,
    *,
    views: int,
    uniques: int,
    clones: int,
    cloners: int,
) -> dict[str, str]:
    ts = day.isoformat()
    return {
        "repo": repo,
        "ts": ts,
        "views_count": str(max(0, views)),
        "views_uniques": str(max(0, uniques)),
        "clones_count": str(max(0, clones)),
        "clones_uniques": str(max(0, cloners)),
        "captured_at": f"{ts}T12:00:00Z",
        "source": "dashboard-scenario",
        "schema_version": storage.SCHEMA_VERSION,
    }


def _read_csv_rows(data_dir: Path, filename: str) -> list[dict[str, str]]:
    path = data_dir / filename
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _latest_day(rows: list[dict[str, str]]) -> str:
    return max((row.get("ts", "") for row in rows if row.get("ts")), default="")


def _all_dates(rows: list[dict[str, str]]) -> list[str]:
    return sorted({row["ts"] for row in rows if row.get("ts")})


def _repos(rows: list[dict[str, str]]) -> list[str]:
    return sorted({row["repo"] for row in rows if row.get("repo")})


def _latest_capture(rows: list[dict[str, str]]) -> str:
    latest = _latest_day(rows)
    return f"{latest}T12:00:00Z" if latest else ""


def _repo_daily_views(rows: list[dict[str, str]]) -> dict[tuple[str, str], int]:
    totals: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row.get("repo", ""), row.get("ts", ""))
        totals[key] = totals.get(key, 0) + int(row.get("views_count", 0) or 0)
    return totals


def _synthetic_referrers(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    captured_at = _latest_capture(rows)
    referrers = [
        ("github.com", 0.36),
        ("google.com", 0.22),
        ("docs.github.com", 0.14),
        ("news.ycombinator.com", 0.10),
        ("reddit.com", 0.07),
        ("stackoverflow.com", 0.04),
    ]
    result: list[dict[str, str]] = []
    for repo_row in load_data.aggregate_per_repo(rows)[:8]:
        repo = repo_row["repo"]
        total_views = int(repo_row["total_views"])
        for referrer, ratio in referrers:
            count = max(1, int(total_views * ratio / 4))
            result.append({
                "repo": repo,
                "captured_at": captured_at,
                "referrer": referrer,
                "count": str(count),
                "uniques": str(max(1, int(count * 0.62))),
                "schema_version": storage.SCHEMA_VERSION,
            })
    return result


def _synthetic_paths(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    captured_at = _latest_capture(rows)
    path_templates = [
        ("", "Repository overview", 0.45),
        ("/blob/main/README.md", "README", 0.18),
        ("/releases", "Releases", 0.12),
        ("/tree/main/docs", "Documentation", 0.10),
        ("/issues", "Issues", 0.07),
    ]
    result: list[dict[str, str]] = []
    for repo_row in load_data.aggregate_per_repo(rows)[:8]:
        repo = repo_row["repo"]
        total_views = int(repo_row["total_views"])
        for suffix, title, ratio in path_templates:
            path = f"/{repo}{suffix}"
            count = max(1, int(total_views * ratio / 5))
            result.append({
                "repo": repo,
                "captured_at": captured_at,
                "path": path,
                "title": title,
                "count": str(count),
                "uniques": str(max(1, int(count * 0.58))),
                "schema_version": storage.SCHEMA_VERSION,
            })
    return result


def _synthetic_metrics(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    dates = _all_dates(rows)
    view_totals = _repo_daily_views(rows)
    result: list[dict[str, str]] = []
    for repo_index, repo in enumerate(_repos(rows)):
        cumulative_views = 0
        for day_index, ts in enumerate(dates):
            views = view_totals.get((repo, ts), 0)
            cumulative_views += views
            stars = 24 + repo_index * 11 + cumulative_views // 420 + day_index // 12
            watchers = 5 + repo_index * 3 + cumulative_views // 1400 + day_index // 24
            forks = 3 + repo_index * 2 + cumulative_views // 1900 + day_index // 30
            health = 96 - ((repo_index * 9) % 36)
            result.append({
                "repo": repo,
                "repo_id": str(1000 + repo_index),
                "node_id": f"R_SCENARIO_{repo_index}",
                "ts": ts,
                "captured_at": f"{ts}T12:00:00Z",
                "stargazers_count": str(stars),
                "subscribers_count": str(watchers),
                "forks_count": str(forks),
                "open_issues_count": str(2 + repo_index % 5),
                "size_kb": str(220 + repo_index * 64),
                "created_at": "2025-01-01T00:00:00Z",
                "pushed_at": f"{ts}T11:00:00Z",
                "updated_at": f"{ts}T11:30:00Z",
                "language": "Python" if repo_index % 2 == 0 else "TypeScript",
                "visibility": "public",
                "default_branch": "main",
                "has_pages": "False",
                "has_discussions": "True",
                "archived": "False",
                "disabled": "False",
                "community_health_percentage": str(health),
                "community_documentation": "README.md",
                "community_updated_at": f"{ts}T11:30:00Z",
                "community_content_reports_enabled": "True",
                "community_has_code_of_conduct": "True",
                "community_has_contributing": "True" if repo_index % 3 != 0 else "False",
                "community_has_issue_template": "True",
                "community_has_pull_request_template": "True",
                "community_has_readme": "True",
                "community_has_license": "True",
                "source": "dashboard-scenario",
                "schema_version": storage.SCHEMA_VERSION,
            })
    return result


def _synthetic_status(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for row in rows:
        views = int(row.get("views_count", 0) or 0)
        clones = int(row.get("clones_count", 0) or 0)
        status = "ok_with_data" if views > 0 or clones > 0 else "ok_zero_data"
        result.append({
            "repo": row.get("repo", ""),
            "ts": row.get("ts", ""),
            "captured_at": row.get("captured_at", ""),
            "run_id": "dashboard-scenario",
            "status": status,
            "metric_source": "traffic-daily.csv",
            "traffic_days": "1",
            "referrer_rows": "0",
            "path_rows": "0",
            "error_type": "",
            "error_message": "",
            "schema_version": storage.SCHEMA_VERSION,
        })
    return result


def _scenario_from_daily(
    *,
    key: str,
    title: str,
    description: str,
    daily_rows: list[dict[str, str]],
) -> ScenarioDataset:
    return ScenarioDataset(
        key=key,
        title=title,
        description=description,
        daily_rows=daily_rows,
        referrer_rows=_synthetic_referrers(daily_rows),
        path_rows=_synthetic_paths(daily_rows),
        metric_rows=_synthetic_metrics(daily_rows),
        status_rows=_synthetic_status(daily_rows),
    )


def _fixture_scenario(data_dir: Path) -> ScenarioDataset:
    daily_rows = _read_csv_rows(data_dir, "traffic-daily.csv")
    return ScenarioDataset(
        key="fixture_baseline",
        title="Fixture baseline",
        description="Current repository fixture data, matching the publish preview fixture.",
        daily_rows=daily_rows,
        referrer_rows=_read_csv_rows(data_dir, "traffic-referrers.csv"),
        path_rows=_read_csv_rows(data_dir, "traffic-paths.csv"),
        metric_rows=_read_csv_rows(data_dir, "repo-metrics.csv"),
        status_rows=_read_csv_rows(data_dir, "collection-status.csv")
        or _synthetic_status(daily_rows),
    )


def _portfolio_rows() -> list[dict[str, str]]:
    repos = [
        ("reponomics/action", 72),
        ("reponomics/dashboard-template", 54),
        ("reponomics/docs-site", 39),
        ("reponomics/collector", 34),
        ("reponomics/examples", 26),
        ("reponomics/infra", 21),
        ("reponomics/cli", 17),
        ("reponomics/charts", 15),
        ("reponomics/playground", 12),
        ("reponomics/schema", 9),
        ("reponomics/archive-reader", 6),
        ("reponomics/release-tools", 4),
    ]
    start = date(2026, 2, 25)
    rows: list[dict[str, str]] = []
    for offset in range(90):
        day = start + timedelta(days=offset)
        weekend_factor = 0.62 if day.weekday() >= 5 else 1.0
        for repo_index, (repo, base) in enumerate(repos):
            wave = ((offset + 3) * (repo_index + 5)) % 29
            launch_lift = 28 if 52 <= offset <= 60 and repo_index in {0, 1, 3} else 0
            views = int((base + wave + launch_lift) * weekend_factor)
            rows.append(
                _row(
                    repo,
                    day,
                    views=views,
                    uniques=max(1, int(views * 0.57)),
                    clones=max(0, int(views * 0.09)),
                    cloners=max(0, int(views * 0.045)),
                )
            )
    return rows


def _spike_rows() -> list[dict[str, str]]:
    start = date(2026, 3, 1)
    rows: list[dict[str, str]] = []
    for offset in range(90):
        day = start + timedelta(days=offset)
        baseline = 11 + offset % 5
        spike = 470 if offset == 68 else 0
        afterglow = 96 - ((offset - 69) * 12) if 69 <= offset <= 75 else 0
        views = baseline + max(0, spike + afterglow)
        rows.append(
            _row(
                "demo/sudden-breakout",
                day,
                views=views,
                uniques=max(1, int(views * 0.64)),
                clones=max(0, int(views * 0.12)),
                cloners=max(0, int(views * 0.07)),
            )
        )
        rows.append(
            _row(
                "demo/steady-companion",
                day,
                views=8 + (offset % 7),
                uniques=5 + (offset % 3),
                clones=1 + (offset % 2),
                cloners=1,
            )
        )
    return rows


def _long_label_rows() -> list[dict[str, str]]:
    repos = [
        ("enterprise-observability-labs/reponomics-dashboard-super-long-private-mirror", 65),
        ("research-platform-team/collector-migration-compatibility-fixtures", 47),
        ("developer-experience/release-note-policy-validation-toolkit", 31),
        ("platform-infra/plain-artifact-export-verification-service", 24),
        ("maintainer-tools/community-health-profile-snapshotter", 18),
        ("archive/really-small-but-noisy-repo", 7),
    ]
    start = date(2026, 4, 1)
    rows: list[dict[str, str]] = []
    for offset in range(45):
        day = start + timedelta(days=offset)
        for repo_index, (repo, base) in enumerate(repos):
            views = base + ((offset * (repo_index + 2)) % 19)
            rows.append(
                _row(
                    repo,
                    day,
                    views=views,
                    uniques=max(1, int(views * 0.55)),
                    clones=max(0, int(views * 0.08)),
                    cloners=max(0, int(views * 0.04)),
                )
            )
    return rows


def _large_corpus_rows(repo_count: int = 200, day_count: int = 30) -> list[dict[str, str]]:
    start = date(2026, 4, 26)
    rows: list[dict[str, str]] = []
    for offset in range(day_count):
        day = start + timedelta(days=offset)
        weekend_factor = 0.68 if day.weekday() >= 5 else 1.0
        for repo_index in range(repo_count):
            repo = f"reponomics-scale/repo-{repo_index + 1:03d}"
            base = 4 + (repo_index % 37)
            wave = ((offset + 5) * (repo_index + 11)) % 23
            views = int((base + wave) * weekend_factor)
            rows.append(
                _row(
                    repo,
                    day,
                    views=views,
                    uniques=max(1, int(views * 0.56)),
                    clones=max(0, int(views * 0.08)),
                    cloners=max(0, int(views * 0.04)),
                )
            )
    return rows


def large_corpus_scenario() -> ScenarioDataset:
    """Return the deterministic ADR 16 scale scenario without snapshot fan-out."""
    return _scenario_from_daily(
        key="large_corpus_200",
        title="Large corpus",
        description="Two hundred repositories for encrypted chunking and scale checks.",
        daily_rows=_large_corpus_rows(),
    )


def _upstream_lag_rows() -> list[dict[str, str]]:
    start = date(2026, 6, 1)
    repos = ["demo/api-monitor", "demo/docs-site", "demo/toolkit"]
    rows: list[dict[str, str]] = []
    for repo_index, repo in enumerate(repos):
        for offset in range(8):
            rows.append(
                _row(
                    repo,
                    start + timedelta(days=offset),
                    views=12 + repo_index * 4 + offset,
                    uniques=7 + repo_index * 2,
                    clones=2 + repo_index,
                    cloners=1 + repo_index,
                )
            )
    return rows


def _upstream_lag_scenario() -> ScenarioDataset:
    daily_rows = _upstream_lag_rows()
    status_rows = [
        {
            "repo": repo,
            "ts": "2026-06-11",
            "captured_at": "2026-06-11T12:00:00Z",
            "run_id": "dashboard-scenario",
            "status": "ok_with_data",
            "metric_source": "repo-detail",
            "traffic_days": "14",
            "referrer_rows": "1",
            "path_rows": "1",
            "error_type": "",
            "error_message": "",
            "schema_version": storage.SCHEMA_VERSION,
        }
        for repo in _repos(daily_rows)
    ]
    return ScenarioDataset(
        key="upstream_traffic_lag",
        title="Upstream traffic lag",
        description="Collection is current but GitHub traffic reporting is three days behind.",
        daily_rows=daily_rows,
        referrer_rows=_synthetic_referrers(daily_rows),
        path_rows=_synthetic_paths(daily_rows),
        metric_rows=_synthetic_metrics(daily_rows),
        status_rows=status_rows,
    )


def build_scenarios(fixture_data_dir: Path = DEFAULT_FIXTURE_DATA_DIR) -> list[ScenarioDataset]:
    """Return deterministic full-data scenarios for visual iteration and edge checks."""
    return [
        _fixture_scenario(fixture_data_dir),
        _scenario_from_daily(
            key="portfolio_growth",
            title="Portfolio growth",
            description=(
                "Dense multi-repository history with referrers, content paths, " +
                "growth counters, and quality status."
            ),
            daily_rows=_portfolio_rows(),
        ),
        _scenario_from_daily(
            key="single_repo_spike",
            title="Single-repo spike",
            description="One dominant repository with an outlier traffic day.",
            daily_rows=_spike_rows(),
        ),
        _scenario_from_daily(
            key="long_labels",
            title="Long labels",
            description=(
                "Long organization and repository names that stress labels, " +
                "legends, tables, and bars."
            ),
            daily_rows=_long_label_rows(),
        ),
        _scenario_from_daily(
            key="empty_state",
            title="Empty state",
            description="No retained traffic yet; every component should still render usefully.",
            daily_rows=[],
        ),
        _upstream_lag_scenario(),
    ]
