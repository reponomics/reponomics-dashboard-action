"""Portfolio-level dashboard profile heuristics."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median
from typing import Any

from load_data_modules.repo_metrics import (
    latest_repo_community_profiles,
    latest_repo_metadata,
)
from load_data_modules.types import Candidate, Rows

DEFAULT_WINDOW_DAYS = 14


def build_portfolio_profile(
    daily_rows: Rows,
    metric_rows: Rows,
    *,
    issue_pr_rows: Rows | None = None,
    event_rows: Rows | None = None,
    growth: Candidate | None = None,
    window_days: int | None = None,
) -> Candidate:
    """Build the deterministic data profile used to tune dashboard guidance."""
    if not daily_rows:
        return _empty_profile()

    latest_date = max((str(row.get("ts") or "") for row in daily_rows), default="")
    window = _int(window_days) or _int((growth or {}).get("window_days")) or DEFAULT_WINDOW_DAYS
    traffic_by_repo = {
        repo: _traffic_stats(rows, latest_date, window)
        for repo, rows in _rows_by_repo(daily_rows).items()
    }
    repos = sorted(traffic_by_repo)
    repo_count = len(repos)
    total_views = sum(_int(row.get("views")) for row in traffic_by_repo.values())
    total_visitors = sum(_int(row.get("visitors")) for row in traffic_by_repo.values())
    total_clones = sum(_int(row.get("clones")) for row in traffic_by_repo.values())
    active_repos = sum(
        1
        for row in traffic_by_repo.values()
        if _int(row.get("views")) + _int(row.get("clones")) > 0
    )
    quiet_repos = sum(1 for row in traffic_by_repo.values() if row.get("quiet"))
    top_repo, top_share = _top_attention_share(traffic_by_repo, total_views + total_clones)
    community = latest_repo_community_profiles(metric_rows)
    metadata = latest_repo_metadata(metric_rows)
    readiness_gap_repos = sum(1 for repo in repos if _missing_readiness(community.get(repo, {})))
    avg_health = _average_health(community.get(repo, {}) for repo in repos)
    young_repos = sum(
        1 for repo in repos if _repo_age_days(metadata.get(repo, {}), latest_date) <= 180
    )
    maintenance_items = _maintenance_items(issue_pr_rows or [])
    recent_event_count = _recent_event_count(event_rows or [], latest_date, window)
    downstream_delta = _downstream_delta(growth or {})
    profile_id = _classify_profile(
        repo_count=repo_count,
        young_repos=young_repos,
        active_repos=active_repos,
        maintenance_items=maintenance_items,
        recent_event_count=recent_event_count,
    )

    return {
        "id": profile_id,
        "label": _profile_label(profile_id),
        "bucket": _repo_count_bucket(repo_count),
        "repo_count": repo_count,
        "window_days": window,
        "summary": _profile_summary(profile_id, repo_count, active_repos, top_repo, top_share),
        "primary_goal": _primary_goal(profile_id),
        "signals": {
            "total_views": total_views,
            "total_visitors": total_visitors,
            "total_clones": total_clones,
            "active_repos": active_repos,
            "quiet_repos": quiet_repos,
            "young_repos": young_repos,
            "readiness_gap_repos": readiness_gap_repos,
            "avg_community_health": avg_health,
            "maintenance_items": maintenance_items,
            "recent_event_count": recent_event_count,
            "downstream_delta": downstream_delta,
            "top_repo": top_repo,
            "top_attention_share": round(top_share, 3),
            "selected_set_full": repo_count >= 8,
        },
        "guidance": _profile_guidance(profile_id),
        "recipe_emphasis": _recipe_emphasis(profile_id),
        "data_gaps": _data_gaps(),
        "repo_stats": {
            repo: {
                key: value
                for key, value in stats.items()
                if key
                in {
                    "views",
                    "visitors",
                    "clones",
                    "cloners",
                    "active_days",
                    "quiet_days",
                    "sample_count",
                    "attention",
                    "quiet",
                }
            }
            for repo, stats in traffic_by_repo.items()
        },
    }


def _empty_profile() -> Candidate:
    return {
        "id": "empty",
        "label": "Waiting for data",
        "bucket": "empty",
        "repo_count": 0,
        "window_days": DEFAULT_WINDOW_DAYS,
        "summary": "The dashboard needs retained collection rows before it can tune guidance.",
        "primary_goal": "Collect a few runs, then inspect the first visible traffic and readiness signals.",
        "signals": {},
        "guidance": [],
        "recipe_emphasis": [],
        "data_gaps": _data_gaps(),
        "repo_stats": {},
    }


def _traffic_stats(rows: Rows, latest_date: str, window_days: int) -> Candidate:
    ordered = sorted(rows, key=lambda row: str(row.get("ts") or ""))
    cutoff = _date_offset(latest_date, -(window_days - 1)) if latest_date else ""
    recent = [row for row in ordered if not cutoff or str(row.get("ts") or "") >= cutoff]
    if not recent:
        recent = ordered[-window_days:]
    active_days = sum(1 for row in recent if _int(row.get("views_count")) > 0)
    sample_count = len(recent)
    views = sum(_int(row.get("views_count")) for row in recent)
    clones = sum(_int(row.get("clones_count")) for row in recent)
    quiet_days = max(0, sample_count - active_days)
    attention = views + clones
    return {
        "views": views,
        "visitors": sum(_int(row.get("views_uniques")) for row in recent),
        "clones": clones,
        "cloners": sum(_int(row.get("clones_uniques")) for row in recent),
        "active_days": active_days,
        "quiet_days": quiet_days,
        "sample_count": sample_count,
        "attention": attention,
        "quiet": sample_count >= 7 and quiet_days >= max(4, round(sample_count * 0.55)),
    }


def _classify_profile(
    *,
    repo_count: int,
    young_repos: int,
    active_repos: int,
    maintenance_items: int,
    recent_event_count: int,
) -> str:
    if repo_count <= 0:
        return "empty"
    if repo_count == 1:
        return "first_app_launch"
    if repo_count == 2:
        return "focused_builder"
    if repo_count >= 6 or maintenance_items >= 24 or recent_event_count >= repo_count * 3:
        return "maintainer_portfolio"
    if young_repos >= max(1, repo_count // 2) and active_repos <= 3:
        return "builder_portfolio"
    return "product_operator"


def _profile_label(profile_id: str) -> str:
    labels = {
        "empty": "Waiting for data",
        "first_app_launch": "First app launch",
        "focused_builder": "Focused builder",
        "builder_portfolio": "Builder portfolio",
        "product_operator": "Product operator",
        "maintainer_portfolio": "Maintainer portfolio",
    }
    return labels.get(profile_id, "Project portfolio")


def _profile_summary(
    profile_id: str,
    repo_count: int,
    active_repos: int,
    top_repo: str,
    top_share: float,
) -> str:
    short_top = top_repo.rsplit("/", 1)[-1] if top_repo else "the leading repo"
    pct = round(top_share * 100)
    if profile_id == "first_app_launch":
        return "One published repo means the dashboard should behave like a launch console: positioning, first visits, quiet days, and the next public-facing improvement matter most."
    if profile_id == "focused_builder":
        return f"Two published repos make comparison useful, but the work is still mostly about positioning and momentum. {short_top} has about {pct}% of visible attention."
    if profile_id == "builder_portfolio":
        return f"{repo_count} published repos are visible, with {active_repos} active in the selected window. The useful move is to identify which project deserves the next positioning pass."
    if profile_id == "maintainer_portfolio":
        return f"{repo_count} published repos make this a maintenance and awareness view. The dashboard should surface spikes, code events, triage load, and public-readiness gaps."
    return f"{repo_count} published repos make this a product-operator view: compare attention, choose where to tighten the funnel, and keep the next action small."


def _primary_goal(profile_id: str) -> str:
    goals = {
        "first_app_launch": "Turn early attention into a clearer first-visit path.",
        "focused_builder": "Compare the two projects and pick the one next public-facing improvement.",
        "builder_portfolio": "Choose the repo where a small positioning change can create the most momentum.",
        "product_operator": "Rank opportunities across repos without losing the concrete next action.",
        "maintainer_portfolio": "Stay aware of code, release, and maintenance events that deserve a follow-up.",
    }
    return goals.get(profile_id, "Use retained data to pick the next useful project move.")


def _profile_guidance(profile_id: str) -> list[Candidate]:
    if profile_id == "first_app_launch":
        return [
            _guide("Position", "Make the README answer who it is for, what it does, and the first command or demo path."),
            _guide("Rhythm", "Use quiet days as prompts for a docs, release, or example update rather than as a failure signal."),
            _guide("Conversion", "When visitors arrive without stars, forks, or clones, tighten the next step before chasing more traffic."),
        ]
    if profile_id == "focused_builder":
        return [
            _guide("Compare", "Look for the repo that gets attention without a matching next step."),
            _guide("Support", "Use the quieter repo to strengthen docs, examples, or install flow if it supports the main app."),
            _guide("Publish", "Keep the published set small and intentional while the projects are still finding their audience."),
        ]
    if profile_id == "builder_portfolio":
        return [
            _guide("Select", "Pick one repo to polish each cycle instead of spreading attention across the whole set."),
            _guide("Describe", "Make each README opening sentence distinct enough that visitors know which project is for them."),
            _guide("Repeat", "When one project gets traction, copy the working pattern into adjacent repos."),
        ]
    if profile_id == "maintainer_portfolio":
        return [
            _guide("Watch", "Use code and release events as anchors when traffic moves."),
            _guide("Triage", "Fix issue templates, PR templates, and contribution docs before spikes turn into unstructured work."),
            _guide("Curate", "Publish the eight repos that deserve attention this cycle; rotate the set when another project becomes active."),
        ]
    return [
        _guide("Rank", "Use attention and downstream growth together to decide which repo deserves the next pass."),
        _guide("Inspect", "Compare referrers, paths, and code events before changing positioning."),
        _guide("Act", "Prefer one small public-facing improvement per repo over broad interpretation."),
    ]


def _recipe_emphasis(profile_id: str) -> list[str]:
    emphasis = {
        "first_app_launch": [
            "solo_launch_positioning",
            "quiet_day_reactivation",
            "steady_attention_next_step",
            "attention_without_readiness",
        ],
        "focused_builder": [
            "solo_launch_positioning",
            "portfolio_attention_concentration",
            "discovery_surface_next_step",
        ],
        "builder_portfolio": [
            "portfolio_attention_concentration",
            "discovery_surface_next_step",
            "positioning_shift",
        ],
        "product_operator": [
            "portfolio_attention_concentration",
            "release_adoption_lift",
            "steady_attention_next_step",
        ],
        "maintainer_portfolio": [
            "maintainer_triage_sweep",
            "event_aligned_attention",
            "code_churn_context",
            "maintenance_pressure",
        ],
    }
    return emphasis.get(profile_id, [])


def _data_gaps() -> list[Candidate]:
    return [
        {
            "key": "readme_content",
            "label": "README content snapshot",
            "reason": "Community profile tells whether a README exists, but not whether it explains audience, setup, examples, or next steps.",
            "candidate_table": "repo-readme-snapshots.csv",
        }
    ]


def _guide(label: str, text: str) -> Candidate:
    return {"label": label, "text": text}


def _repo_count_bucket(repo_count: int) -> str:
    if repo_count <= 0:
        return "empty"
    if repo_count == 1:
        return "solo"
    if repo_count == 2:
        return "pair"
    if repo_count <= 5:
        return "small_portfolio"
    if repo_count <= 8:
        return "published_portfolio"
    return "large_portfolio"


def _top_attention_share(
    traffic_by_repo: dict[str, Candidate],
    denominator: int,
) -> tuple[str, float]:
    if not traffic_by_repo or denominator <= 0:
        return "", 0.0
    repo, stats = max(
        traffic_by_repo.items(),
        key=lambda item: (_int(item[1].get("attention")), item[0]),
    )
    return repo, _int(stats.get("attention")) / denominator


def _average_health(values: Any) -> int | None:
    health_values = [
        _int(value.get("health_percentage"))
        for value in values
        if value.get("health_percentage") is not None
    ]
    if not health_values:
        return None
    return round(median(health_values))


def _missing_readiness(community: Candidate) -> list[str]:
    keys = [
        "has_readme",
        "has_license",
        "has_contributing",
        "has_issue_template",
        "has_pull_request_template",
        "has_code_of_conduct",
    ]
    return [key for key in keys if community.get(key) is False]


def _maintenance_items(rows: Rows) -> int:
    latest = _latest_row_by_repo(rows)
    return sum(
        _int(row.get("open_issues_count")) + _int(row.get("open_prs_count"))
        for row in latest.values()
    )


def _recent_event_count(rows: Rows, latest_date: str, window_days: int) -> int:
    if not latest_date:
        return 0
    cutoff = _date_offset(latest_date, -(window_days - 1))
    return sum(1 for row in rows if str(row.get("event_date") or "")[:10] >= cutoff)


def _downstream_delta(growth: Candidate) -> int:
    per_repo = growth.get("per_repo", {}) if isinstance(growth, dict) else {}
    total = 0
    for row in per_repo.values():
        deltas = row.get("deltas", {}) if isinstance(row, dict) else {}
        total += (
            _int(deltas.get("stargazers_delta") or deltas.get("stars_delta"))
            + _int(deltas.get("subscribers_delta"))
            + _int(deltas.get("forks_delta"))
        )
    return total


def _repo_age_days(metadata: Candidate, latest_date: str) -> int:
    created_at = str(metadata.get("created_at") or "")[:10]
    if not created_at or not latest_date:
        return 999_999
    return abs(_days_between(latest_date, created_at))


def _rows_by_repo(rows: Rows) -> dict[str, Rows]:
    grouped: defaultdict[str, Rows] = defaultdict(list)
    for row in rows:
        repo = str(row.get("repo") or "")
        if repo:
            grouped[repo].append(row)
    return dict(grouped)


def _latest_row_by_repo(rows: Rows) -> dict[str, Candidate]:
    latest: dict[str, Candidate] = {}
    for row in rows:
        repo = str(row.get("repo") or "")
        captured = str(row.get("captured_at") or row.get("ts") or "")
        if repo and captured >= str(latest.get(repo, {}).get("captured_at") or ""):
            latest[repo] = row
    return latest


def _date_offset(date_text: str, days: int) -> str:
    try:
        return (datetime.strptime(date_text[:10], "%Y-%m-%d") + timedelta(days=days)).date().isoformat()
    except ValueError:
        return ""


def _days_between(a: str, b: str) -> int:
    try:
        return (
            datetime.strptime(a[:10], "%Y-%m-%d").date()
            - datetime.strptime(b[:10], "%Y-%m-%d").date()
        ).days
    except ValueError:
        return 0


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0
