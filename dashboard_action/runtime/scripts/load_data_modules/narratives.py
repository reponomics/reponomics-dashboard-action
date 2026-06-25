"""Narrative insight recipes that join traffic with repository context."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median
from typing import Any

from load_data_modules.repo_metrics import latest_repo_community_profiles
from load_data_modules.types import Candidate, Rows


DEFAULT_WINDOW_DAYS = 14
EVENT_NEAR_DAYS = 3


def narrative_insights(
    daily_rows: Rows,
    metric_rows: Rows | None = None,
    *,
    growth: Candidate | None = None,
    event_rows: Rows | None = None,
    release_rows: Rows | None = None,
    issue_pr_rows: Rows | None = None,
    language_rows: Rows | None = None,
    topic_rows: Rows | None = None,
    code_frequency_rows: Rows | None = None,
    contributor_activity_rows: Rows | None = None,
    referrer_rows: Rows | None = None,
    path_rows: Rows | None = None,
    limit: int = 6,
) -> list[Candidate]:
    """Return ranked contextual narrative cards for the dashboard."""
    if limit <= 0:
        return []

    daily_by_repo = _rows_by_repo(daily_rows)
    if not daily_by_repo:
        return []

    latest_date = max((str(row.get("ts") or "") for row in daily_rows), default="")
    window_days = _int((growth or {}).get("window_days")) or DEFAULT_WINDOW_DAYS
    traffic = {
        repo: _traffic_stats(rows, latest_date, window_days)
        for repo, rows in daily_by_repo.items()
    }
    attention_floor = _attention_floor([row["views"] for row in traffic.values()])
    context = _build_context(
        traffic,
        metric_rows or [],
        growth or {},
        event_rows or [],
        release_rows or [],
        issue_pr_rows or [],
        language_rows or [],
        topic_rows or [],
        code_frequency_rows or [],
        contributor_activity_rows or [],
        referrer_rows or [],
        path_rows or [],
        attention_floor,
        latest_date,
    )

    candidates: list[Candidate] = []
    for repo in sorted(context):
        repo_context = context[repo]
        _attention_conversion_gap(candidates, repo_context)
        _event_aligned_attention(candidates, repo_context)
        _release_adoption_lift(candidates, repo_context)
        _attention_before_readiness(candidates, repo_context)
        _maintenance_pressure(candidates, repo_context)
        _code_churn_context(candidates, repo_context)
        _contributor_concentration(candidates, repo_context)
        _discovery_positioning_signal(candidates, repo_context)

    candidates.sort(key=lambda item: (-float(item.get("score", 0)), item["recipe"], item["repo"]))
    return [_strip_score(item) for item in _diversified(candidates, limit)]


def _build_context(
    traffic: dict[str, Candidate],
    metric_rows: Rows,
    growth: Candidate,
    event_rows: Rows,
    release_rows: Rows,
    issue_pr_rows: Rows,
    language_rows: Rows,
    topic_rows: Rows,
    code_frequency_rows: Rows,
    contributor_activity_rows: Rows,
    referrer_rows: Rows,
    path_rows: Rows,
    attention_floor: int,
    latest_date: str,
) -> dict[str, Candidate]:
    community = latest_repo_community_profiles(metric_rows)
    metric_context = _latest_metric_context(metric_rows)
    events = _events_by_repo(event_rows)
    releases = _release_events_by_repo(release_rows)
    issues = _latest_rows_by_repo(issue_pr_rows)
    languages = _latest_languages_by_repo(language_rows)
    topics = _latest_topics_by_repo(topic_rows)
    code = _code_frequency_by_repo(code_frequency_rows, latest_date)
    contributors = _contributors_by_repo(contributor_activity_rows, latest_date)
    referrers = _latest_snapshot_rows_by_repo(referrer_rows)
    paths = _latest_snapshot_rows_by_repo(path_rows)
    per_repo_growth = growth.get("per_repo", {}) if isinstance(growth, dict) else {}

    return {
        repo: {
            "repo": repo,
            "traffic": traffic_row,
            "growth": per_repo_growth.get(repo, {}),
            "community": community.get(repo, {}),
            "metrics": metric_context.get(repo, {}),
            "events": events.get(repo, []),
            "releases": releases.get(repo, []),
            "issues": issues.get(repo, {}),
            "languages": languages.get(repo, []),
            "topics": topics.get(repo, []),
            "code": code.get(repo, {}),
            "contributors": contributors.get(repo, {}),
            "referrers": referrers.get(repo, []),
            "paths": paths.get(repo, []),
            "attention_floor": attention_floor,
        }
        for repo, traffic_row in traffic.items()
    }


def _traffic_stats(rows: Rows, latest_date: str, window_days: int) -> Candidate:
    ordered = sorted(rows, key=lambda row: str(row.get("ts") or ""))
    cutoff = _date_offset(latest_date, -(window_days - 1)) if latest_date else ""
    prior_cutoff = _date_offset(cutoff, -window_days) if cutoff else ""
    recent = [row for row in ordered if not cutoff or str(row.get("ts") or "") >= cutoff]
    prior = [
        row
        for row in ordered
        if prior_cutoff <= str(row.get("ts") or "") < cutoff
    ] if cutoff and prior_cutoff else []
    if not recent:
        recent = ordered[-window_days:]

    recent_views = [_int(row.get("views_count")) for row in recent]
    all_views = [_int(row.get("views_count")) for row in ordered]
    peak_row = max(recent or ordered, key=lambda row: _int(row.get("views_count")), default={})
    baseline_values = all_views[:-1] if len(all_views) > 1 else all_views
    baseline = median(baseline_values) if baseline_values else 0
    return {
        "window_days": window_days,
        "views": sum(recent_views),
        "visitors": sum(_int(row.get("views_uniques")) for row in recent),
        "clones": sum(_int(row.get("clones_count")) for row in recent),
        "cloners": sum(_int(row.get("clones_uniques")) for row in recent),
        "prior_views": sum(_int(row.get("views_count")) for row in prior),
        "prior_visitors": sum(_int(row.get("views_uniques")) for row in prior),
        "sample_count": len(recent),
        "peak_date": str(peak_row.get("ts") or ""),
        "peak_views": _int(peak_row.get("views_count")),
        "baseline_views": float(baseline),
        "latest_date": latest_date,
    }


def _attention_conversion_gap(candidates: list[Candidate], context: Candidate) -> None:
    traffic = context["traffic"]
    growth = context["growth"].get("deltas", {})
    downstream = _downstream_delta(growth)
    visitors = _int(traffic.get("visitors"))
    views = _int(traffic.get("views"))
    if visitors < 5 or views < context["attention_floor"] or downstream > 0:
        return
    candidates.append(
        _candidate(
            context,
            recipe="attention_conversion_gap",
            tone="attention",
            title="Attention is not turning into visible community movement",
            summary=(
                f"{context['repo']} drew {_fmt(visitors)} visitors in the last "
                + f"{traffic['window_days']}d, while stars, watchers, and forks moved "
                + f"by {_signed(downstream)} in total."
            ),
            score=views + visitors * 1.4 + max(0, 8 - downstream) * 8,
            evidence=[
                _evidence("Visitors", _fmt(visitors), f"{traffic['window_days']}d window"),
                _evidence("Views", _fmt(views), "attention"),
                _evidence("Downstream", _signed(downstream), "stars + watchers + forks"),
            ],
            action="Inspect the README, examples, and contribution path before chasing more reach.",
        )
    )


def _event_aligned_attention(candidates: list[Candidate], context: Candidate) -> None:
    traffic = context["traffic"]
    peak_views = _int(traffic.get("peak_views"))
    baseline = float(traffic.get("baseline_views") or 0)
    if peak_views < max(6, baseline * 1.75):
        return
    event = _nearest_event(context.get("events", []), str(traffic.get("peak_date") or ""))
    if not event:
        return
    gap = _days_between(str(traffic.get("peak_date") or ""), event.get("event_date", ""))
    relation = _near_phrase(gap)
    event_label = _event_label(event)
    candidates.append(
        _candidate(
            context,
            recipe="event_aligned_attention",
            tone="positive",
            title="A repository event lines up with the attention peak",
            summary=(
                f"{context['repo']} hit {_fmt(peak_views)} views on {traffic['peak_date']}, "
                + f"{relation} {event_label}. Treat this as nearby evidence, not proof of cause."
            ),
            score=peak_views * 1.6 + _int(event.get("magnitude")) + 35,
            anchor_date=str(traffic.get("peak_date") or ""),
            evidence=[
                _evidence("Peak day", _fmt(peak_views), str(traffic.get("peak_date") or "")),
                _evidence("Baseline", _fmt(round(baseline)), "trailing median"),
                _evidence("Nearby event", event.get("classification") or event.get("event_type") or "event", event.get("event_date", "")),
            ],
            events=[_display_event(event)],
            action="Open the event and compare surrounding referrers, paths, and follow-on growth.",
        )
    )


def _release_adoption_lift(candidates: list[Candidate], context: Candidate) -> None:
    traffic = context["traffic"]
    release = _latest_recent_event(
        [*context.get("releases", []), *[e for e in context.get("events", []) if e.get("event_type") == "release"]],
        str(traffic.get("latest_date") or ""),
        max(21, _int(traffic.get("window_days"))),
    )
    if not release:
        return
    clones = _int(traffic.get("clones"))
    cloners = _int(traffic.get("cloners"))
    forks_delta = _int(context["growth"].get("deltas", {}).get("forks_delta"))
    release_magnitude = _int(release.get("magnitude") or release.get("asset_download_count"))
    if clones < 3 and forks_delta <= 0 and release_magnitude <= 0:
        return
    candidates.append(
        _candidate(
            context,
            recipe="release_adoption_lift",
            tone="positive",
            title="Release activity is paired with adoption signals",
            summary=(
                f"{_event_label(release)} is in the recent window for {context['repo']}; "
                + f"the same window shows {_fmt(clones)} clones, {_fmt(cloners)} cloners, "
                + f"and {_signed(forks_delta)} forks."
            ),
            score=clones * 4 + cloners * 3 + max(0, forks_delta) * 20 + release_magnitude + 30,
            anchor_date=str(release.get("event_date") or ""),
            evidence=[
                _evidence("Release", release.get("title") or release.get("tag_name") or "release", release.get("event_date", "")),
                _evidence("Clones", _fmt(clones), f"{traffic['window_days']}d window"),
                _evidence("Forks", _signed(forks_delta), "counter delta"),
            ],
            events=[_display_event(release)],
            action="Check release notes, package assets, and clone/fork follow-through.",
        )
    )


def _attention_before_readiness(candidates: list[Candidate], context: Candidate) -> None:
    traffic = context["traffic"]
    views = _int(traffic.get("views"))
    visitors = _int(traffic.get("visitors"))
    if views < context["attention_floor"] or visitors < 5:
        return
    community = context.get("community", {})
    missing = _missing_community_files(community)
    health = community.get("health_percentage")
    health_int = _int(health) if health is not None else None
    if not missing and (health_int is None or health_int >= 70):
        return
    missing_text = ", ".join(missing[:3]) if missing else "low community-health score"
    candidates.append(
        _candidate(
            context,
            recipe="attention_before_readiness",
            tone="warning",
            title="Attention is arriving before the repo looks contributor-ready",
            summary=(
                f"{context['repo']} has {_fmt(visitors)} recent visitors, but "
                + f"{missing_text} may make the next step less obvious."
            ),
            score=views + visitors + len(missing) * 18 + max(0, 75 - (health_int or 75)),
            evidence=[
                _evidence("Visitors", _fmt(visitors), f"{traffic['window_days']}d window"),
                _evidence("Community", f"{health_int}%" if health_int is not None else "unknown", "health score"),
                _evidence("Missing", str(len(missing)), ", ".join(missing[:4]) or "none"),
            ],
            action="Tighten contributor affordances while the repo is already being inspected.",
        )
    )


def _maintenance_pressure(candidates: list[Candidate], context: Candidate) -> None:
    issue_row = context.get("issues", {})
    if not issue_row:
        return
    traffic = context["traffic"]
    visitors = _int(traffic.get("visitors"))
    clones = _int(traffic.get("clones"))
    open_issues = _int(issue_row.get("open_issues_count"))
    open_prs = _int(issue_row.get("open_prs_count"))
    stale = _int(issue_row.get("stale_open_issues_count")) + _int(issue_row.get("stale_open_prs_count"))
    unanswered = _int(issue_row.get("unanswered_issue_count"))
    pressure = open_issues + open_prs + stale + unanswered
    if pressure < 5 or (visitors + clones) < 8:
        return
    candidates.append(
        _candidate(
            context,
            recipe="maintenance_pressure",
            tone="warning",
            title="User attention is meeting an active maintenance queue",
            summary=(
                f"{context['repo']} has {_fmt(visitors)} recent visitors and {_fmt(clones)} "
                + f"clones while {_fmt(open_issues)} issues and {_fmt(open_prs)} PRs are open."
            ),
            score=pressure * 12 + visitors + clones * 2,
            evidence=[
                _evidence("Visitors", _fmt(visitors), f"{traffic['window_days']}d window"),
                _evidence("Open issues", _fmt(open_issues), "latest snapshot"),
                _evidence("Open PRs", _fmt(open_prs), "latest snapshot"),
            ],
            action="Use labels, templates, or release notes to steer incoming user work.",
        )
    )


def _code_churn_context(candidates: list[Candidate], context: Candidate) -> None:
    code = context.get("code", {})
    if not code:
        return
    traffic = context["traffic"]
    changes = _int(code.get("additions")) + _int(code.get("deletions"))
    views = _int(traffic.get("views"))
    prior = _int(traffic.get("prior_views"))
    if changes < 200 or (views > prior and views >= context["attention_floor"]):
        return
    direction = "quiet" if views < context["attention_floor"] else "flat"
    candidates.append(
        _candidate(
            context,
            recipe="code_churn_context",
            tone="neutral",
            title="Internal code churn gives context for a quiet traffic window",
            summary=(
                f"{context['repo']} had {_fmt(changes)} lines changed recently while "
                + f"attention stayed {direction} at {_fmt(views)} views."
            ),
            score=changes / 8 + max(0, prior - views) + 20,
            evidence=[
                _evidence("Code changes", _fmt(changes), "additions + deletions"),
                _evidence("Views", _fmt(views), f"{traffic['window_days']}d window"),
                _evidence("Prior views", _fmt(prior), "previous comparable window"),
            ],
            action="Look for whether the churn was user-facing, refactor-heavy, or release preparation.",
        )
    )


def _contributor_concentration(candidates: list[Candidate], context: Candidate) -> None:
    contributors = context.get("contributors", {})
    if not contributors:
        return
    traffic = context["traffic"]
    active = _int(contributors.get("active_contributors"))
    commits = _int(contributors.get("commits"))
    visitors = _int(traffic.get("visitors"))
    clones = _int(traffic.get("clones"))
    if active != 1 or (visitors + clones) < max(8, context["attention_floor"] // 2):
        return
    candidates.append(
        _candidate(
            context,
            recipe="contributor_concentration",
            tone="attention",
            title="Interest is visible while contribution is concentrated",
            summary=(
                f"{context['repo']} has {_fmt(visitors)} visitors and {_fmt(clones)} clones "
                + "recently, but the contributor activity sample is concentrated in one author."
            ),
            score=visitors + clones * 3 + commits * 2 + 25,
            evidence=[
                _evidence("Active contributors", _fmt(active), "recent weekly sample"),
                _evidence("Commits", _fmt(commits), "recent weekly sample"),
                _evidence("Clones", _fmt(clones), f"{traffic['window_days']}d window"),
            ],
            action="Consider marking good first issues or asking for help in the next release note.",
        )
    )


def _discovery_positioning_signal(candidates: list[Candidate], context: Candidate) -> None:
    traffic = context["traffic"]
    visitors = _int(traffic.get("visitors"))
    if visitors < 5:
        return
    top_referrer = _top_row(context.get("referrers", []), "count")
    top_path = _top_row(context.get("paths", []), "count")
    languages = context.get("languages", [])
    topics = context.get("topics", [])
    referrer_name = str(top_referrer.get("referrer") or "")
    path_title = str(top_path.get("title") or top_path.get("path") or "")
    is_discovery_referrer = referrer_name and referrer_name not in {"github.com", "api.github.com"}
    is_docs_path = any(token in path_title.lower() for token in ("readme", "docs", "documentation", "release"))
    if not ((is_discovery_referrer or is_docs_path) and (languages or topics)):
        return
    descriptor = _positioning_descriptor(languages, topics)
    candidates.append(
        _candidate(
            context,
            recipe="discovery_positioning_signal",
            tone="neutral",
            title="Discovery has a content and positioning shape",
            summary=(
                f"{context['repo']} is drawing {_fmt(visitors)} visitors with "
                + f"{referrer_name or 'repository content'} and {path_title or 'popular paths'} "
                + f"pointing toward {descriptor}."
            ),
            score=visitors + _int(top_referrer.get("count")) * 2 + _int(top_path.get("count")) + 18,
            evidence=[
                _evidence("Top referrer", referrer_name or "unknown", _fmt(_int(top_referrer.get("count")))),
                _evidence("Top content", path_title or "unknown", _fmt(_int(top_path.get("count")))),
                _evidence("Positioning", descriptor, "language/topic context"),
            ],
            action="Inspect whether README, docs, topics, and release copy match the audience finding the repo.",
        )
    )


def _candidate(
    context: Candidate,
    *,
    recipe: str,
    tone: str,
    title: str,
    summary: str,
    score: float,
    evidence: list[Candidate],
    action: str,
    anchor_date: str = "",
    events: list[Candidate] | None = None,
) -> Candidate:
    return {
        "recipe": recipe,
        "repo": context["repo"],
        "tone": tone,
        "title": title,
        "summary": summary,
        "anchor_date": anchor_date,
        "evidence": evidence,
        "events": events or [],
        "action": action,
        "score": round(float(score), 3),
    }


def _evidence(label: str, value: str, detail: str = "") -> Candidate:
    return {"label": label, "value": value, "detail": detail}


def _rows_by_repo(rows: Rows) -> dict[str, Rows]:
    grouped: defaultdict[str, Rows] = defaultdict(list)
    for row in rows:
        repo = str(row.get("repo") or "")
        if repo:
            grouped[repo].append(row)
    return dict(grouped)


def _latest_rows_by_repo(rows: Rows) -> dict[str, Candidate]:
    result = {}
    for repo, repo_rows in _rows_by_repo(rows).items():
        result[repo] = max(
            repo_rows,
            key=lambda row: (str(row.get("ts") or ""), str(row.get("captured_at") or "")),
        )
    return result


def _latest_snapshot_rows_by_repo(rows: Rows) -> dict[str, Rows]:
    result = {}
    for repo, repo_rows in _rows_by_repo(rows).items():
        latest = max((str(row.get("captured_at") or "") for row in repo_rows), default="")
        result[repo] = [row for row in repo_rows if str(row.get("captured_at") or "") == latest]
    return result


def _latest_metric_context(metric_rows: Rows) -> dict[str, Candidate]:
    fields = {
        "open_issues_count",
        "size_kb",
        "language",
        "visibility",
        "default_branch",
        "has_pages",
        "has_discussions",
        "archived",
        "disabled",
    }
    latest = _latest_rows_by_repo(metric_rows)
    return {
        repo: {field: row.get(field, "") for field in fields}
        for repo, row in latest.items()
    }


def _events_by_repo(event_rows: Rows) -> dict[str, Rows]:
    return {
        repo: sorted(rows, key=lambda row: (str(row.get("event_date") or ""), str(row.get("event_id") or "")))
        for repo, rows in _rows_by_repo(event_rows).items()
    }


def _release_events_by_repo(release_rows: Rows) -> dict[str, Rows]:
    grouped: defaultdict[str, Rows] = defaultdict(list)
    for row in release_rows:
        repo = str(row.get("repo") or "")
        release_id = str(row.get("release_id") or "")
        if not repo or not release_id:
            continue
        event_ts = str(row.get("published_at") or row.get("created_at") or row.get("captured_at") or "")
        grouped[repo].append(
            {
                "event_id": f"release:{release_id}",
                "event_type": "release",
                "event_date": event_ts[:10],
                "title": row.get("name") or row.get("tag_name") or f"Release {release_id}",
                "classification": "release",
                "magnitude": _int(row.get("asset_download_count")) or _int(row.get("asset_count")),
                "url": row.get("html_url", ""),
            }
        )
    return {repo: sorted(rows, key=lambda row: str(row.get("event_date") or "")) for repo, rows in grouped.items()}


def _latest_languages_by_repo(rows: Rows) -> dict[str, list[str]]:
    result = {}
    for repo, repo_rows in _rows_by_repo(rows).items():
        latest = max((str(row.get("captured_at") or "") for row in repo_rows), default="")
        latest_rows = [row for row in repo_rows if str(row.get("captured_at") or "") == latest]
        latest_rows.sort(key=lambda row: _float(row.get("share")), reverse=True)
        result[repo] = [str(row.get("language") or "") for row in latest_rows[:3] if row.get("language")]
    return result


def _latest_topics_by_repo(rows: Rows) -> dict[str, list[str]]:
    result = {}
    for repo, repo_rows in _rows_by_repo(rows).items():
        latest = max((str(row.get("captured_at") or "") for row in repo_rows), default="")
        result[repo] = sorted(
            str(row.get("topic") or "")
            for row in repo_rows
            if str(row.get("captured_at") or "") == latest and row.get("topic")
        )[:5]
    return result


def _code_frequency_by_repo(rows: Rows, latest_date: str) -> dict[str, Candidate]:
    cutoff = _date_offset(latest_date, -35) if latest_date else ""
    result = {}
    for repo, repo_rows in _rows_by_repo(rows).items():
        recent = [row for row in repo_rows if not cutoff or str(row.get("week_start") or "") >= cutoff]
        if not recent:
            continue
        result[repo] = {
            "additions": sum(_int(row.get("additions")) for row in recent),
            "deletions": sum(_int(row.get("deletions")) for row in recent),
            "weeks": len({str(row.get("week_start") or "") for row in recent}),
        }
    return result


def _contributors_by_repo(rows: Rows, latest_date: str) -> dict[str, Candidate]:
    cutoff = _date_offset(latest_date, -35) if latest_date else ""
    result = {}
    for repo, repo_rows in _rows_by_repo(rows).items():
        recent = [row for row in repo_rows if not cutoff or str(row.get("week_start") or "") >= cutoff]
        if not recent:
            continue
        authors = {str(row.get("author_login") or row.get("author_id") or "") for row in recent}
        authors.discard("")
        result[repo] = {
            "active_contributors": len(authors),
            "commits": sum(_int(row.get("commits")) for row in recent),
            "additions": sum(_int(row.get("additions")) for row in recent),
            "deletions": sum(_int(row.get("deletions")) for row in recent),
        }
    return result


def _attention_floor(values: list[int]) -> int:
    nonzero = sorted(value for value in values if value > 0)
    if not nonzero:
        return 8
    idx = min(len(nonzero) - 1, max(0, int(round((len(nonzero) - 1) * 0.65))))
    return max(8, nonzero[idx])


def _downstream_delta(deltas: Candidate) -> int:
    return (
        _int(deltas.get("stargazers_delta") or deltas.get("stars_delta"))
        + _int(deltas.get("subscribers_delta"))
        + _int(deltas.get("forks_delta"))
    )


def _missing_community_files(community: Candidate) -> list[str]:
    checks = [
        ("has_readme", "README"),
        ("has_license", "license"),
        ("has_contributing", "contributing guide"),
        ("has_issue_template", "issue template"),
        ("has_pull_request_template", "PR template"),
        ("has_code_of_conduct", "code of conduct"),
    ]
    missing = []
    for key, label in checks:
        value = community.get(key)
        if value is False:
            missing.append(label)
    return missing


def _nearest_event(events: Rows, anchor_date: str) -> Candidate | None:
    if not anchor_date:
        return None
    nearby = [
        (abs(_days_between(anchor_date, str(event.get("event_date") or ""))), event)
        for event in events
        if event.get("event_date")
    ]
    nearby = [item for item in nearby if item[0] <= EVENT_NEAR_DAYS]
    if not nearby:
        return None
    nearby.sort(key=lambda item: (item[0], -_int(item[1].get("magnitude"))))
    return nearby[0][1]


def _latest_recent_event(events: Rows, latest_date: str, max_age_days: int) -> Candidate | None:
    if not latest_date:
        return None
    recent = [
        event
        for event in events
        if event.get("event_date") and 0 <= _days_between(latest_date, str(event.get("event_date"))) <= max_age_days
    ]
    if not recent:
        return None
    return max(recent, key=lambda event: (str(event.get("event_date") or ""), _int(event.get("magnitude"))))


def _display_event(event: Candidate) -> Candidate:
    return {
        "date": str(event.get("event_date") or ""),
        "title": str(event.get("title") or event.get("event_id") or "Repository event"),
        "type": str(event.get("event_type") or ""),
        "classification": str(event.get("classification") or ""),
        "url": str(event.get("url") or ""),
    }


def _event_label(event: Candidate) -> str:
    title = str(event.get("title") or event.get("event_id") or "a repository event")
    classification = str(event.get("classification") or event.get("event_type") or "event")
    return f"{classification} event \"{title}\""


def _near_phrase(day_gap: int) -> str:
    if day_gap == 0:
        return "on the same day as"
    if day_gap > 0:
        return f"{day_gap}d after"
    return f"{abs(day_gap)}d before"


def _top_row(rows: Rows, field: str) -> Candidate:
    return max(rows, key=lambda row: _int(row.get(field)), default={})


def _positioning_descriptor(languages: list[str], topics: list[str]) -> str:
    parts = []
    if languages:
        parts.append(languages[0])
    if topics:
        parts.append(", ".join(topics[:2]))
    return " / ".join(parts) if parts else "repository positioning"


def _diversified(candidates: list[Candidate], limit: int) -> list[Candidate]:
    selected: list[Candidate] = []
    seen_recipes: set[str] = set()
    seen_repos: set[str] = set()
    for item in candidates:
        if item["recipe"] in seen_recipes or item["repo"] in seen_repos:
            continue
        selected.append(item)
        seen_recipes.add(item["recipe"])
        seen_repos.add(item["repo"])
        if len(selected) >= limit:
            return selected
    for item in candidates:
        if item in selected:
            continue
        selected.append(item)
        if len(selected) >= limit:
            return selected
    return selected


def _strip_score(item: Candidate) -> Candidate:
    return {key: value for key, value in item.items() if key != "score"}


def _date_offset(value: str, days: int) -> str:
    try:
        parsed = datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return ""
    return (parsed + timedelta(days=days)).isoformat()


def _days_between(a: str, b: str) -> int:
    try:
        da = datetime.strptime(a[:10], "%Y-%m-%d").date()
        db = datetime.strptime(b[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return 999999
    return (da - db).days


def _int(value: Any) -> int:
    try:
        return int(float(str(value).strip() or 0))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(str(value).strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def _fmt(value: int | float) -> str:
    return f"{int(round(float(value))):,}"


def _signed(value: int) -> str:
    return f"{value:+,}"
