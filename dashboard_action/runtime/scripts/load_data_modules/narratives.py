"""Deterministic contextual narrative recipes for dashboard insights."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median
from typing import Any

from load_data_modules.portfolio_profile import build_portfolio_profile
from load_data_modules.repo_metrics import latest_repo_community_profiles
from load_data_modules.types import Candidate, Rows

DEFAULT_WINDOW_DAYS = 14
EVENT_NEAR_DAYS = 3
RELEASE_NEAR_DAYS = 21


def narrative_insights_structured(
    daily_rows: Rows,
    metric_rows: Rows,
    *,
    path_rows: Rows | None = None,
    referrer_rows: Rows | None = None,
    event_rows: Rows | None = None,
    release_asset_rows: Rows | None = None,
    issue_pr_rows: Rows | None = None,
    issue_label_rows: Rows | None = None,
    endpoint_rows: Rows | None = None,
    collection_day_rows: Rows | None = None,
    language_rows: Rows | None = None,
    topic_rows: Rows | None = None,
    code_frequency_rows: Rows | None = None,
    contributor_activity_rows: Rows | None = None,
    growth: Candidate | None = None,
    portfolio_profile: Candidate | None = None,
    limit: int = 5,
) -> list[Candidate]:
    """Return ranked, rules-based narrative cards from retained context tables."""
    del issue_label_rows, endpoint_rows, collection_day_rows, contributor_activity_rows
    if limit <= 0 or not daily_rows:
        return []

    latest_date = max((str(row.get("ts") or "") for row in daily_rows), default="")
    window_days = _int((growth or {}).get("window_days")) or DEFAULT_WINDOW_DAYS
    profile = portfolio_profile or build_portfolio_profile(
        daily_rows,
        metric_rows,
        issue_pr_rows=issue_pr_rows or [],
        event_rows=event_rows or [],
        growth=growth or {},
        window_days=window_days,
    )
    traffic_by_repo = {
        repo: _traffic_stats(rows, latest_date, window_days)
        for repo, rows in _rows_by_repo(daily_rows).items()
    }
    attention_floor = _attention_floor(row["views"] for row in traffic_by_repo.values())
    context = _context_by_repo(
        traffic_by_repo=traffic_by_repo,
        metric_rows=metric_rows,
        path_rows=path_rows or [],
        referrer_rows=referrer_rows or [],
        event_rows=event_rows or [],
        release_asset_rows=release_asset_rows or [],
        issue_pr_rows=issue_pr_rows or [],
        language_rows=language_rows or [],
        topic_rows=topic_rows or [],
        code_frequency_rows=code_frequency_rows or [],
        growth=growth or {},
        portfolio_profile=profile,
        latest_date=latest_date,
        attention_floor=attention_floor,
    )

    candidates: list[Candidate] = []
    for repo in sorted(context):
        row = context[repo]
        _event_aligned_attention(candidates, row)
        _release_adoption_lift(candidates, row)
        _docs_or_examples_found_audience(candidates, row)
        _solo_launch_positioning(candidates, row)
        _quiet_day_reactivation(candidates, row)
        _steady_attention_next_step(candidates, row)
        _discovery_surface_next_step(candidates, row)
        _attention_without_readiness(candidates, row)
        _maintenance_pressure(candidates, row)
        _code_churn_context(candidates, row)
        _positioning_shift(candidates, row)
    _portfolio_attention_concentration(candidates, context, profile)
    _maintainer_triage_sweep(candidates, context, profile)
    _published_set_curation(candidates, profile)

    candidates.sort(key=lambda item: float(item.get("score", 0)), reverse=True)
    return [_strip_score(item) for item in _diversified(candidates, limit)]


def _context_by_repo(
    *,
    traffic_by_repo: dict[str, Candidate],
    metric_rows: Rows,
    path_rows: Rows,
    referrer_rows: Rows,
    event_rows: Rows,
    release_asset_rows: Rows,
    issue_pr_rows: Rows,
    language_rows: Rows,
    topic_rows: Rows,
    code_frequency_rows: Rows,
    growth: Candidate,
    portfolio_profile: Candidate,
    latest_date: str,
    attention_floor: int,
) -> dict[str, Candidate]:
    community = latest_repo_community_profiles(metric_rows)
    return {
        repo: {
            "repo": repo,
            "traffic": traffic,
            "growth": (growth.get("per_repo", {}) if isinstance(growth, dict) else {}).get(
                repo, {}
            ),
            "portfolio_profile": portfolio_profile,
            "community": community.get(repo, {}),
            "events": _rows_by_repo(event_rows).get(repo, []),
            "release_assets": _release_assets_by_release(release_asset_rows),
            "issues": _latest_row_by_repo(issue_pr_rows).get(repo, {}),
            "languages": _latest_snapshot_by_repo(language_rows).get(repo, []),
            "previous_languages": _previous_snapshot_by_repo(language_rows).get(repo, []),
            "topics": _latest_snapshot_by_repo(topic_rows).get(repo, []),
            "previous_topics": _previous_snapshot_by_repo(topic_rows).get(repo, []),
            "code_frequency": _recent_code_frequency(code_frequency_rows, repo, latest_date),
            "referrers": _latest_snapshot_by_repo(referrer_rows).get(repo, []),
            "paths": _latest_snapshot_by_repo(path_rows).get(repo, []),
            "attention_floor": attention_floor,
            "latest_date": latest_date,
        }
        for repo, traffic in traffic_by_repo.items()
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

    all_views = [_int(row.get("views_count")) for row in ordered]
    peak_row = max(recent or ordered, key=lambda row: _int(row.get("views_count")), default={})
    baseline_values = all_views[:-1] if len(all_views) > 1 else all_views
    baseline = median(baseline_values) if baseline_values else 0
    return {
        "window_days": window_days,
        "views": sum(_int(row.get("views_count")) for row in recent),
        "visitors": sum(_int(row.get("views_uniques")) for row in recent),
        "clones": sum(_int(row.get("clones_count")) for row in recent),
        "cloners": sum(_int(row.get("clones_uniques")) for row in recent),
        "prior_views": sum(_int(row.get("views_count")) for row in prior),
        "sample_count": len(recent),
        "active_days": sum(1 for row in recent if _int(row.get("views_count")) > 0),
        "peak_date": str(peak_row.get("ts") or ""),
        "peak_views": _int(peak_row.get("views_count")),
        "baseline_views": float(baseline),
    }


def _event_aligned_attention(candidates: list[Candidate], context: Candidate) -> None:
    traffic = context["traffic"]
    peak_views = _int(traffic.get("peak_views"))
    baseline = float(traffic.get("baseline_views") or 0)
    if peak_views < max(8, baseline * 1.75):
        return
    event = _nearest_event(context["events"], str(traffic.get("peak_date") or ""))
    if not event:
        return
    gap = _days_between(str(traffic.get("peak_date") or ""), event.get("event_date", ""))
    event_label = _event_label(event)
    _add_candidate(
        candidates,
        context,
        subtype="event_aligned_attention",
        tone="opportunity",
        title="Repository activity lines up with an attention peak",
        summary=(
            f"{_short_repo(context['repo'])} reached {_fmt(peak_views)} views on "
            + f"{traffic['peak_date']}, {_near_phrase(gap)} {event_label}. "
            + "That makes the event a useful place to inspect the follow-on traffic."
        ),
        score=peak_views * 1.6 + _int(event.get("magnitude")) + 35,
        anchor_date=str(traffic.get("peak_date") or ""),
        evidence=[
            _evidence("Peak day", _fmt(peak_views), str(traffic.get("peak_date") or "")),
            _evidence("Baseline", _fmt(round(baseline)), "trailing median"),
            _evidence("Nearby event", event_label, str(event.get("event_date") or "")),
        ],
        nearby_context=[_display_event(event), *_positioning_context(context)[:2]],
        action="Compare paths, referrers, and follow-on growth around that event.",
    )


def _release_adoption_lift(candidates: list[Candidate], context: Candidate) -> None:
    release = _latest_recent_release(context["events"], context["latest_date"])
    if not release:
        return
    traffic = context["traffic"]
    growth = context["growth"].get("deltas", {})
    clones = _int(traffic.get("clones"))
    cloners = _int(traffic.get("cloners"))
    forks_delta = _int(growth.get("forks_delta"))
    asset_downloads = _release_downloads(context["release_assets"], release)
    if clones < 3 and cloners < 2 and forks_delta <= 0 and asset_downloads <= 0:
        return
    _add_candidate(
        candidates,
        context,
        subtype="release_adoption_lift",
        tone="opportunity",
        title="A release window has adoption signals",
        summary=(
            f"{_event_label(release)} is in the recent window for "
            + f"{_short_repo(context['repo'])}; the same window shows "
            + f"{_fmt(clones)} clones, {_fmt(cloners)} cloners, and "
            + f"{_signed(forks_delta)} forks."
        ),
        score=clones * 4 + cloners * 3 + max(0, forks_delta) * 20 + asset_downloads + 30,
        anchor_date=str(release.get("event_date") or ""),
        evidence=[
            _evidence("Release", _event_label(release), str(release.get("event_date") or "")),
            _evidence("Clones", _fmt(clones), f"{traffic['window_days']}d window"),
            _evidence("Forks", _signed(forks_delta), "same window"),
            _evidence("Asset downloads", _fmt(asset_downloads), "latest release snapshot"),
        ],
        nearby_context=[_display_event(release)],
        action="Use release notes and install docs as the next comparison point.",
    )


def _docs_or_examples_found_audience(candidates: list[Candidate], context: Candidate) -> None:
    docs_event = _latest_classified_event(context["events"], {"docs"})
    traffic = context["traffic"]
    top_path = _top_row(context["paths"], "count")
    top_referrer = _top_row(context["referrers"], "count")
    if not docs_event or _int(traffic["views"]) < max(8, context["attention_floor"] // 2):
        return
    path_label = str(top_path.get("title") or top_path.get("path") or "popular content")
    if not _looks_like_docs(path_label) and not _looks_like_docs(str(top_path.get("path") or "")):
        path_label = ""
    _add_candidate(
        candidates,
        context,
        subtype="docs_found_audience",
        tone="opportunity",
        title="Documentation work has audience context",
        summary=(
            f"{_short_repo(context['repo'])} has docs/example activity in the retained event trail "
            + f"and {_fmt(traffic['views'])} views in the selected window."
        ),
        score=_int(traffic["views"]) + _int(top_path.get("count")) * 2 + 24,
        anchor_date=str(docs_event.get("event_date") or ""),
        evidence=[
            _evidence("Docs event", _event_label(docs_event), str(docs_event.get("event_date") or "")),
            _evidence("Views", _fmt(traffic["views"]), f"{traffic['window_days']}d window"),
            _evidence("Top content", path_label or "not docs-specific", str(top_path.get("count") or "")),
            _evidence("Top referrer", str(top_referrer.get("referrer") or "unknown"), str(top_referrer.get("count") or "")),
        ],
        nearby_context=[_display_event(docs_event), *_positioning_context(context)[:2]],
        action="Check whether the docs page or README explains the next step clearly.",
    )


def _solo_launch_positioning(candidates: list[Candidate], context: Candidate) -> None:
    profile = context.get("portfolio_profile", {})
    if profile.get("id") not in {"first_app_launch", "focused_builder"}:
        return
    traffic = context["traffic"]
    views = _int(traffic.get("views"))
    visitors = _int(traffic.get("visitors"))
    clones = _int(traffic.get("clones"))
    if views + clones < 4 or visitors < 2:
        return
    missing = _missing_readiness(context["community"])
    downstream = _downstream_delta(context)
    top_path = _top_row(context["paths"], "count")
    _add_candidate(
        candidates,
        context,
        subtype="solo_launch_positioning",
        tone="opportunity",
        title="Early attention needs launch-positioning clarity",
        summary=(
            f"{_short_repo(context['repo'])} is part of a small published set and "
            + f"has {_fmt(visitors)} visitors in the selected window. This is a good "
            + "moment to make the first-visit path explicit."
        ),
        score=views * 0.35 + visitors * 1.6 + clones * 2 + len(missing) * 12 + 18,
        evidence=[
            _evidence("Visitors", _fmt(visitors), f"{traffic['window_days']}d window"),
            _evidence("Clones", _fmt(clones), f"{traffic['window_days']}d window"),
            _evidence("Downstream", _signed(downstream), "stars + watchers + forks"),
            _evidence("Top content", _content_label(top_path) or "unknown", str(top_path.get("count") or "")),
        ],
        nearby_context=_positioning_context(context)[:3],
        action="Make the README opening answer who it is for, the first command, and the first success state.",
    )


def _quiet_day_reactivation(candidates: list[Candidate], context: Candidate) -> None:
    profile = context.get("portfolio_profile", {})
    if profile.get("id") not in {"first_app_launch", "focused_builder", "builder_portfolio"}:
        return
    traffic = context["traffic"]
    sample_count = _int(traffic.get("sample_count"))
    active_days = _int(traffic.get("active_days"))
    quiet_days = max(0, sample_count - active_days)
    if sample_count < 7 or quiet_days < max(4, round(sample_count * 0.55)):
        return
    if _int(traffic.get("views")) + _int(traffic.get("clones")) <= 0:
        return
    _add_candidate(
        candidates,
        context,
        subtype="quiet_day_reactivation",
        tone="opportunity",
        title="Quiet days can become a shipping rhythm",
        summary=(
            f"{_short_repo(context['repo'])} had {_fmt(quiet_days)} quiet days in a "
            + f"{_fmt(sample_count)} day window. Use the quiet pattern to plan a "
            + "small reason for people to return."
        ),
        score=quiet_days * 15 + _int(traffic.get("visitors")) * 2 + 28,
        evidence=[
            _evidence("Quiet days", _fmt(quiet_days), f"{sample_count}d sample"),
            _evidence("Active days", _fmt(active_days), f"{traffic['window_days']}d window"),
            _evidence("Views", _fmt(traffic.get("views")), f"{traffic['window_days']}d window"),
        ],
        nearby_context=_event_context(context)[:3],
        action="Ship one visible follow-up: an example, release note, screenshot, or README path that gives visitors a reason to return.",
    )


def _steady_attention_next_step(candidates: list[Candidate], context: Candidate) -> None:
    traffic = context["traffic"]
    views = _int(traffic["views"])
    visitors = _int(traffic["visitors"])
    downstream = _downstream_delta(context)
    baseline = float(traffic.get("baseline_views") or 0)
    peak = _int(traffic.get("peak_views"))
    is_steady = peak <= max(18, baseline * 1.65)
    if (
        views < max(18, context["attention_floor"] // 2)
        or visitors < 6
        or _int(traffic.get("active_days")) < 5
        or downstream > 1
        or not is_steady
    ):
        return
    top_path = _top_row(context["paths"], "count")
    top_referrer = _top_row(context["referrers"], "count")
    content = _content_label(top_path)
    _add_candidate(
        candidates,
        context,
        subtype="steady_attention_next_step",
        tone="opportunity",
        title="Steady attention needs a clearer next step",
        summary=(
            f"{_short_repo(context['repo'])} drew {_fmt(visitors)} visitors across "
            + f"{_fmt(traffic['active_days'])} active days with {_signed(downstream)} "
            + "stars/watchers/forks in the selected window."
        ),
        score=views * 0.95 + visitors * 2.0 + _int(top_path.get("count")) + 42,
        evidence=[
            _evidence("Visitors", _fmt(visitors), f"{traffic['window_days']}d window"),
            _evidence("Downstream", _signed(downstream), "stars + watchers + forks"),
            _evidence("Top content", content or "unknown", str(top_path.get("count") or "")),
            _evidence("Top referrer", str(top_referrer.get("referrer") or "unknown"), str(top_referrer.get("count") or "")),
        ],
        nearby_context=_positioning_context(context)[:3],
        action="Add a short README path from problem to install command to first result.",
    )


def _discovery_surface_next_step(candidates: list[Candidate], context: Candidate) -> None:
    traffic = context["traffic"]
    views = _int(traffic["views"])
    if views <= 0 or _int(traffic.get("active_days")) < 3:
        return
    topics = [str(row.get("topic") or "") for row in context["topics"] if row.get("topic")]
    languages = [str(row.get("language") or "") for row in context["languages"] if row.get("language")]
    if len(topics) >= 3 or not (topics or languages):
        return
    top_referrer = _top_row(context["referrers"], "count")
    _add_candidate(
        candidates,
        context,
        subtype="discovery_surface_next_step",
        tone="opportunity",
        title="Discovery surface is still lightweight",
        summary=(
            f"{_short_repo(context['repo'])} has {_fmt(views)} views in the selected "
            + f"window and {len(topics)} retained topic"
            + ("" if len(topics) == 1 else "s")
            + "."
        ),
        score=views * 0.65 + max(0, 3 - len(topics)) * 28,
        evidence=[
            _evidence("Views", _fmt(views), f"{traffic['window_days']}d window"),
            _evidence("Topics", _join_labels(topics[:3]) or "none retained", "latest snapshot"),
            _evidence("Language", _join_labels(languages[:2]) or "unknown", "latest snapshot"),
            _evidence("Top referrer", str(top_referrer.get("referrer") or "unknown"), str(top_referrer.get("count") or "")),
        ],
        nearby_context=_positioning_context(context)[:3],
        action="Add 3-5 GitHub topics and make the README opening sentence problem-shaped.",
    )


def _attention_without_readiness(candidates: list[Candidate], context: Candidate) -> None:
    traffic = context["traffic"]
    missing = _missing_readiness(context["community"])
    if not missing:
        return
    if _int(traffic["views"]) < context["attention_floor"] or _int(traffic["visitors"]) < 5:
        return
    _add_candidate(
        candidates,
        context,
        subtype="attention_without_readiness",
        tone="watch",
        title="Attention is arriving while setup files are incomplete",
        summary=(
            f"{_short_repo(context['repo'])} drew {_fmt(traffic['visitors'])} visitors, "
            + "while the community profile is still missing "
            + _join_labels(missing[:3])
            + "."
        ),
        score=_int(traffic["views"]) + len(missing) * 35,
        evidence=[
            _evidence("Visitors", _fmt(traffic["visitors"]), f"{traffic['window_days']}d window"),
            _evidence("Missing", _join_labels(missing[:3]), "community profile"),
            _evidence("Health", _health_label(context["community"]), "latest snapshot"),
        ],
        nearby_context=_positioning_context(context)[:3],
        action="Make the next visit easier by adding the highest-impact missing files.",
    )


def _maintenance_pressure(candidates: list[Candidate], context: Candidate) -> None:
    issues = context["issues"]
    open_items = _int(issues.get("open_issues_count")) + _int(issues.get("open_prs_count"))
    if open_items < 8 or _int(context["traffic"]["views"]) < max(8, context["attention_floor"] // 2):
        return
    _add_candidate(
        candidates,
        context,
        subtype="maintenance_pressure",
        tone="watch",
        title="Audience attention is paired with maintenance load",
        summary=(
            f"{_short_repo(context['repo'])} has {_fmt(open_items)} open issues/PRs "
            + f"while drawing {_fmt(context['traffic']['views'])} views in the selected window."
        ),
        score=open_items * 12 + _int(context["traffic"]["views"]),
        evidence=[
            _evidence("Open issues", _fmt(_int(issues.get("open_issues_count"))), "latest sample"),
            _evidence("Open PRs", _fmt(_int(issues.get("open_prs_count"))), "latest sample"),
            _evidence("Views", _fmt(context["traffic"]["views"]), f"{context['traffic']['window_days']}d window"),
        ],
        nearby_context=_positioning_context(context)[:2],
        action="Triage labels and contribution docs before the next traffic bump.",
    )


def _code_churn_context(candidates: list[Candidate], context: Candidate) -> None:
    traffic = context["traffic"]
    prior = _int(traffic.get("prior_views"))
    current = _int(traffic.get("views"))
    churn = _int(context["code_frequency"].get("additions")) + _int(
        context["code_frequency"].get("deletions")
    )
    if prior <= 0 or current >= prior * 0.85 or churn < 250:
        return
    pct = round(((current - prior) / prior) * 100)
    _add_candidate(
        candidates,
        context,
        subtype="code_churn_context",
        tone="explain",
        title="A traffic dip overlaps with code churn",
        summary=(
            f"{_short_repo(context['repo'])} views are {pct}% versus the prior window, "
            + f"while {_fmt(churn)} lines changed in recent code-frequency data."
        ),
        score=abs(pct) * 5 + min(churn, 2000) / 4,
        evidence=[
            _evidence("Views", f"{_fmt(prior)} -> {_fmt(current)}", "two windows"),
            _evidence("Code churn", _fmt(churn), "additions + deletions"),
        ],
        nearby_context=_event_context(context)[:3],
        action="Use the churn window as a starting point when reviewing the dip.",
    )


def _positioning_shift(candidates: list[Candidate], context: Candidate) -> None:
    added_topics = _added_values(context["topics"], context["previous_topics"], "topic")
    language_shift = _language_shift(context["languages"], context["previous_languages"])
    if not added_topics and not language_shift:
        return
    top_referrer = _top_row(context["referrers"], "count")
    if _int(context["traffic"]["views"]) < max(8, context["attention_floor"] // 3):
        return
    change = (
        "new topics " + _join_labels(added_topics[:3])
        if added_topics
        else "language mix changed toward " + language_shift
    )
    _add_candidate(
        candidates,
        context,
        subtype="positioning_shift",
        tone="opportunity",
        title="Repository positioning changed while people were arriving",
        summary=(
            f"{_short_repo(context['repo'])} shows {change}; top referrer context is "
            + str(top_referrer.get("referrer") or "not yet available")
            + "."
        ),
        score=_int(context["traffic"]["views"]) + _int(top_referrer.get("count")) * 3 + 20,
        evidence=[
            _evidence("Positioning", change, "latest context snapshot"),
            _evidence("Top referrer", str(top_referrer.get("referrer") or "unknown"), str(top_referrer.get("count") or "")),
            _evidence("Views", _fmt(context["traffic"]["views"]), f"{context['traffic']['window_days']}d window"),
        ],
        nearby_context=_positioning_context(context)[:4],
        action="Make sure README keywords and examples match the audience being attracted.",
    )


def _portfolio_attention_concentration(
    candidates: list[Candidate],
    context_by_repo: dict[str, Candidate],
    profile: Candidate,
) -> None:
    signals = profile.get("signals", {})
    repo_count = _int(profile.get("repo_count"))
    if repo_count < 3:
        return
    top_repo = str(signals.get("top_repo") or "")
    share = float(signals.get("top_attention_share") or 0)
    if not top_repo or share < 0.55:
        return
    top_context = context_by_repo.get(top_repo, {})
    readiness_gap_repos = _int(signals.get("readiness_gap_repos"))
    downstream = _int(signals.get("downstream_delta"))
    _add_global_candidate(
        candidates,
        subtype="portfolio_attention_concentration",
        tone="opportunity",
        title="One repo is carrying most of the published attention",
        summary=(
            f"{_short_repo(top_repo)} has about {round(share * 100)}% of visible "
            + "attention in this published set. Use it as the comparison point for "
            + "which repo deserves the next positioning pass."
        ),
        score=share * 140 + readiness_gap_repos * 18 + max(0, downstream) * 4,
        evidence=[
            _evidence("Top repo", _short_repo(top_repo), f"{round(share * 100)}% attention"),
            _evidence("Published repos", _fmt(repo_count), str(profile.get("bucket") or "")),
            _evidence("Readiness gaps", _fmt(readiness_gap_repos), "repos"),
            _evidence("Downstream", _signed(downstream), "stars + watchers + forks"),
        ],
        nearby_context=_positioning_context(top_context)[:3] if top_context else [],
        action="Compare the top repo README, topics, and referrers against one quieter repo, then make one concrete positioning change.",
    )


def _maintainer_triage_sweep(
    candidates: list[Candidate],
    context_by_repo: dict[str, Candidate],
    profile: Candidate,
) -> None:
    if profile.get("id") != "maintainer_portfolio":
        return
    signals = profile.get("signals", {})
    maintenance_items = _int(signals.get("maintenance_items"))
    readiness_gap_repos = _int(signals.get("readiness_gap_repos"))
    event_count = _int(signals.get("recent_event_count"))
    if maintenance_items < 8 and readiness_gap_repos < 2 and event_count < 4:
        return
    open_rows = sorted(
        (
            (
                _int(row.get("issues", {}).get("open_issues_count"))
                + _int(row.get("issues", {}).get("open_prs_count")),
                repo,
            )
            for repo, row in context_by_repo.items()
        ),
        reverse=True,
    )
    top_repo = open_rows[0][1] if open_rows and open_rows[0][0] > 0 else ""
    _add_global_candidate(
        candidates,
        subtype="maintainer_triage_sweep",
        tone="watch",
        title="Maintainer mode needs lightweight structure",
        summary=(
            "This published set has enough code, release, or issue context to make "
            + "maintenance structure a useful follow-up."
        ),
        score=maintenance_items * 5 + readiness_gap_repos * 26 + event_count * 8 + 45,
        evidence=[
            _evidence("Open issues/PRs", _fmt(maintenance_items), "latest snapshots"),
            _evidence("Readiness gaps", _fmt(readiness_gap_repos), "repos"),
            _evidence("Recent events", _fmt(event_count), f"{profile.get('window_days')}d window"),
            _evidence("Highest load", _short_repo(top_repo) if top_repo else "none", "repo"),
        ],
        nearby_context=_positioning_context(context_by_repo.get(top_repo, {}))[:3]
        if top_repo
        else [],
        action="Start with labels, issue templates, PR templates, and contributing docs before the next release or traffic spike.",
    )


def _published_set_curation(candidates: list[Candidate], profile: Candidate) -> None:
    signals = profile.get("signals", {})
    if not signals.get("selected_set_full"):
        return
    _add_global_candidate(
        candidates,
        subtype="published_set_curation",
        tone="explain",
        title="The published set is at the eight-repo limit",
        summary=(
            "This dashboard is showing a full curated publish set. Repos outside "
            + "the selected set should be rotated in when they become the current "
            + "campaign, release, or maintenance focus."
        ),
        score=58,
        evidence=[
            _evidence("Published repos", _fmt(profile.get("repo_count")), "selected set"),
            _evidence("Active repos", _fmt(signals.get("active_repos")), f"{profile.get('window_days')}d window"),
            _evidence("Profile", str(profile.get("label") or ""), str(profile.get("bucket") or "")),
        ],
        nearby_context=[],
        action="Use the eight slots as an editorial choice: keep active projects visible and rotate quieter repos out until they need attention.",
    )


def _add_candidate(
    candidates: list[Candidate],
    context: Candidate,
    *,
    subtype: str,
    tone: str,
    title: str,
    summary: str,
    score: float,
    evidence: list[Candidate],
    action: str,
    anchor_date: str = "",
    nearby_context: list[Candidate] | None = None,
) -> None:
    candidates.append(
        {
            "kind": "narrative",
            "repo": context["repo"],
            "subtype": subtype,
            "tone": tone,
            "title": title,
            "summary": summary,
            "score": score,
            "anchor_date": anchor_date,
            "confidence": "medium",
            "evidence": [item for item in evidence if item.get("value")],
            "nearby_context": nearby_context or [],
            "action": action,
        }
    )


def _add_global_candidate(
    candidates: list[Candidate],
    *,
    subtype: str,
    tone: str,
    title: str,
    summary: str,
    score: float,
    evidence: list[Candidate],
    action: str,
    nearby_context: list[Candidate] | None = None,
) -> None:
    candidates.append(
        {
            "kind": "narrative",
            "repo": "",
            "subtype": subtype,
            "tone": tone,
            "title": title,
            "summary": summary,
            "score": score,
            "anchor_date": "",
            "confidence": "medium",
            "evidence": [item for item in evidence if item.get("value")],
            "nearby_context": nearby_context or [],
            "action": action,
        }
    )


def _diversified(candidates: list[Candidate], limit: int) -> list[Candidate]:
    selected: list[Candidate] = []
    seen_repos: set[str] = set()
    seen_subtypes: set[str] = set()
    for item in candidates:
        repo = str(item.get("repo") or "")
        subtype = str(item.get("subtype") or "")
        if repo in seen_repos or subtype in seen_subtypes:
            continue
        selected.append(item)
        seen_repos.add(repo)
        seen_subtypes.add(subtype)
        if len(selected) >= limit:
            return selected
    for item in candidates:
        if item not in selected:
            selected.append(item)
        if len(selected) >= limit:
            return selected
    return selected


def _strip_score(item: Candidate) -> Candidate:
    return {key: value for key, value in item.items() if key != "score"}


def _rows_by_repo(rows: Rows) -> dict[str, Rows]:
    by_repo: defaultdict[str, Rows] = defaultdict(list)
    for row in rows:
        repo = str(row.get("repo") or "")
        if repo:
            by_repo[repo].append(row)
    return dict(by_repo)


def _latest_row_by_repo(rows: Rows) -> dict[str, Candidate]:
    latest: dict[str, Candidate] = {}
    for row in rows:
        repo = str(row.get("repo") or "")
        captured = str(row.get("captured_at") or row.get("ts") or "")
        if repo and captured >= str(latest.get(repo, {}).get("captured_at") or ""):
            latest[repo] = row
    return latest


def _latest_snapshot_by_repo(rows: Rows) -> dict[str, Rows]:
    latest_capture = {
        repo: max(str(row.get("captured_at") or "") for row in repo_rows)
        for repo, repo_rows in _rows_by_repo(rows).items()
        if repo_rows
    }
    return {
        repo: [row for row in repo_rows if str(row.get("captured_at") or "") == latest_capture[repo]]
        for repo, repo_rows in _rows_by_repo(rows).items()
        if repo in latest_capture
    }


def _previous_snapshot_by_repo(rows: Rows) -> dict[str, Rows]:
    out: dict[str, Rows] = {}
    for repo, repo_rows in _rows_by_repo(rows).items():
        captures = sorted({str(row.get("captured_at") or "") for row in repo_rows if row.get("captured_at")})
        if len(captures) < 2:
            continue
        previous = captures[-2]
        out[repo] = [row for row in repo_rows if str(row.get("captured_at") or "") == previous]
    return out


def _release_assets_by_release(rows: Rows) -> dict[str, Rows]:
    by_release: defaultdict[str, Rows] = defaultdict(list)
    for row in rows:
        release_id = str(row.get("release_id") or "")
        if release_id:
            by_release[release_id].append(row)
    return dict(by_release)


def _recent_code_frequency(rows: Rows, repo: str, latest_date: str) -> Candidate:
    cutoff = _date_offset(latest_date, -35) if latest_date else ""
    scoped = [
        row
        for row in rows
        if row.get("repo") == repo and (not cutoff or str(row.get("week_start") or "") >= cutoff)
    ]
    return {
        "additions": sum(_int(row.get("additions")) for row in scoped),
        "deletions": sum(_int(row.get("deletions")) for row in scoped),
        "weeks": len({str(row.get("week_start") or "") for row in scoped}),
    }


def _attention_floor(values: Any) -> int:
    positive = sorted(_int(value) for value in values if _int(value) > 0)
    if not positive:
        return 25
    return max(25, positive[len(positive) // 2])


def _nearest_event(events: Rows, date: str) -> Candidate | None:
    dated = [
        (abs(_days_between(date, str(row.get("event_date") or ""))), row)
        for row in events
        if row.get("event_date")
    ]
    dated = [(distance, row) for distance, row in dated if distance <= EVENT_NEAR_DAYS]
    if not dated:
        return None
    return sorted(dated, key=lambda item: (item[0], -_int(item[1].get("magnitude"))))[0][1]


def _latest_recent_release(events: Rows, latest_date: str) -> Candidate | None:
    releases = [
        row
        for row in events
        if row.get("event_type") == "release"
        and abs(_days_between(latest_date, str(row.get("event_date") or ""))) <= RELEASE_NEAR_DAYS
    ]
    if not releases:
        return None
    return sorted(releases, key=lambda row: str(row.get("event_date") or ""), reverse=True)[0]


def _latest_classified_event(events: Rows, classifications: set[str]) -> Candidate | None:
    matches = [
        row
        for row in events
        if str(row.get("classification") or "").lower() in classifications
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda row: str(row.get("event_date") or ""), reverse=True)[0]


def _release_downloads(assets_by_release: dict[str, Rows], release: Candidate) -> int:
    rows = assets_by_release.get(str(release.get("release_id") or ""), [])
    return sum(_int(row.get("download_count")) for row in rows)


def _top_row(rows: Rows, key: str) -> Candidate:
    return max(rows, key=lambda row: _int(row.get(key)), default={})


def _event_context(context: Candidate) -> list[Candidate]:
    return [_display_event(row) for row in sorted(
        context["events"],
        key=lambda item: str(item.get("event_date") or ""),
        reverse=True,
    )[:4]]


def _positioning_context(context: Candidate) -> list[Candidate]:
    items = _event_context(context)
    top_path = _top_row(context["paths"], "count")
    top_referrer = _top_row(context["referrers"], "count")
    if top_path:
        items.append(
            {
                "type": "path",
                "date": str(top_path.get("captured_at") or "")[:10],
                "label": str(top_path.get("title") or top_path.get("path") or "Popular content"),
                "detail": _fmt(top_path.get("count")) + " views",
                "url": "",
            }
        )
    if top_referrer:
        items.append(
            {
                "type": "referrer",
                "date": str(top_referrer.get("captured_at") or "")[:10],
                "label": str(top_referrer.get("referrer") or "Referrer"),
                "detail": _fmt(top_referrer.get("count")) + " views",
                "url": "",
            }
        )
    return items


def _content_label(row: Candidate) -> str:
    return str(row.get("title") or row.get("path") or "").strip()


def _display_event(event: Candidate) -> Candidate:
    return {
        "type": str(event.get("classification") or event.get("event_type") or "event"),
        "date": str(event.get("event_date") or ""),
        "label": _event_label(event),
        "detail": str(event.get("title") or ""),
        "url": str(event.get("url") or ""),
    }


def _event_label(event: Candidate) -> str:
    event_type = str(event.get("event_type") or "event").replace("_", " ")
    classification = str(event.get("classification") or "").replace("_", " ")
    title = str(event.get("title") or "").strip()
    label = classification if classification and classification != "unknown" else event_type
    return f"{label}: {title}" if title else label


def _missing_readiness(community: Candidate) -> list[str]:
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


def _downstream_delta(context: Candidate) -> int:
    deltas = context["growth"].get("deltas", {})
    return (
        _int(deltas.get("stargazers_delta") or deltas.get("stars_delta"))
        + _int(deltas.get("subscribers_delta"))
        + _int(deltas.get("forks_delta"))
    )


def _added_values(latest: Rows, previous: Rows, key: str) -> list[str]:
    prior = {str(row.get(key) or "") for row in previous}
    return sorted(
        value
        for value in {str(row.get(key) or "") for row in latest}
        if value and value not in prior
    )


def _language_shift(latest: Rows, previous: Rows) -> str:
    if not latest or not previous:
        return ""
    latest_top = max(latest, key=lambda row: _float(row.get("share")))
    previous_top = max(previous, key=lambda row: _float(row.get("share")))
    if latest_top.get("language") == previous_top.get("language"):
        return ""
    return str(latest_top.get("language") or "")


def _looks_like_docs(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in ("readme", "docs", "documentation", "example"))


def _health_label(community: Candidate) -> str:
    health = community.get("health_percentage")
    if health is None:
        return "unknown"
    return f"{_int(health)}%"


def _join_labels(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + ", and " + values[-1]


def _short_repo(repo: str) -> str:
    return repo.rsplit("/", 1)[-1]


def _near_phrase(days_after: int) -> str:
    if days_after == 0:
        return "on the same day as"
    if days_after > 0:
        return f"{days_after}d after"
    return f"{abs(days_after)}d before"


def _date_offset(value: str, days: int) -> str:
    parsed = _parse_date(value)
    if not parsed:
        return ""
    return (parsed + timedelta(days=days)).date().isoformat()


def _days_between(a: str, b: str) -> int:
    left = _parse_date(a)
    right = _parse_date(b)
    if not left or not right:
        return 10_000
    return (left.date() - right.date()).days


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _evidence(label: str, value: Any, detail: str = "") -> Candidate:
    return {"label": label, "value": str(value), "detail": detail}


def _fmt(value: Any) -> str:
    return f"{_int(value):,}"


def _signed(value: Any) -> str:
    parsed = _int(value)
    return f"{parsed:+,}"


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
