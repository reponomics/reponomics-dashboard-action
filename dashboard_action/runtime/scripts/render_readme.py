"""Generate a README.md snapshot from canonical CSV data.

Reads traffic-daily.csv, traffic-referrers.csv, and traffic-paths.csv
via the shared load_data module to produce a markdown summary that
agrees on core totals with the HTML dashboard.
"""

import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from load_data import (
    load_daily, load_referrers, load_paths, load_repo_metrics,
    aggregate_totals, aggregate_per_repo,
    top_referrers, top_paths,
    actionable_insights, compute_momentum, growth_analytics,
)
from readme_assets import (
    build_readme_asset_data, write_readme_svg_assets, LIGHT_SUFFIX,
)

OUTPUT_PATH = "README.md"
ASSET_OUTPUT_DIR = Path("docs") / "assets"
ASSET_DISPLAY_DIR = Path("docs") / "assets"
DEFAULT_REPO_TABLE_LIMIT = 10
UPDATE_NOTICE_ENV = "REPONOMICS_UPDATE_NOTICE_JSON"


def _picture(dark_src: str, alt: str) -> str:
    """Build a <picture> element with prefers-color-scheme for light/dark SVGs."""
    stem, ext = dark_src.rsplit(".", 1)
    light_src = f"{stem}{LIGHT_SUFFIX}.{ext}"
    return (
        "<picture>\n" +
        f'  <source media="(prefers-color-scheme: light)" srcset="{light_src}">\n' +
        f'  <img src="{dark_src}" alt="{alt}">\n' +
        "</picture>"
    )


def _load_update_notice():
    raw = os.environ.get(UPDATE_NOTICE_ENV, "")
    if not raw:
        return None
    try:
        notice = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(notice, dict):
        return None
    version = str(notice.get("version") or "").strip()
    title = str(notice.get("title") or "").strip()
    url = str(notice.get("url") or "").strip()
    summary = str(notice.get("summary") or "").strip()
    if not version or not title or not url:
        return None
    return {"version": version, "title": title, "url": url, "summary": summary}


def _update_notice_lines():
    notice = _load_update_notice()
    if not notice:
        return []
    summary = f" {html.escape(notice['summary'])}" if notice["summary"] else ""
    return [
        "<sub>" +
        f"<strong>{html.escape(notice['title'])}</strong>" +
        f"{summary} " +
        f"<a href=\"{html.escape(notice['url'], quote=True)}\">" +
        f"View {html.escape(notice['version'])}</a>." +
        "</sub>",
        "",
    ]


def _repo_table_lines(rows):
    lines = [
        "| Repository | Views | Visitors | Clones | Cloners |",
        "|------------|------:|---------:|-------:|--------:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['repo']} " +
            f"| {row['total_views']:,} " +
            f"| {row['total_uniques']:,} " +
            f"| {row['total_clones']:,} " +
            f"| {row['total_clone_uniques']:,} |"
        )
    return lines


def _format_delta(value: int) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:,}"


def _growth_line(growth):
    totals = growth.get("totals", {})
    window = growth.get("window_days", 14)
    return (
        f"**Growth ({window}d):** " +
        f"attention **{totals.get('total_views', 0):,} views** / " +
        f"**{totals.get('total_uniques', 0):,} visitors**; " +
        f"interest **{_format_delta(totals.get('total_stars_delta', 0))} stars** / " +
        f"**{_format_delta(totals.get('total_subscribers_delta', 0))} watchers** " +
        f"(now {totals.get('total_stars', 0):,} / {totals.get('total_subscribers', 0):,}); " +
        f"adoption **{totals.get('total_clones', 0):,} clones** / " +
        f"**{_format_delta(totals.get('total_forks_delta', 0))} forks** " +
        f"(now {totals.get('total_forks', 0):,})."
    )


def _repo_growth_table_lines(per_repo_rows, growth):
    growth_rows = growth.get("per_repo", {})
    rows = []
    for row in per_repo_rows:
        repo = row["repo"]
        g = growth_rows.get(repo, {})
        deltas = g.get("deltas", {})
        rows.append({
            "repo": repo,
            "views": row["total_views"],
            "visitors": row["total_uniques"],
            "clones": row["total_clones"],
            "stars_delta": deltas.get("stars_delta", 0),
            "stars": deltas.get("current_stars", 0),
            "subscribers_delta": deltas.get("subscribers_delta", 0),
            "subscribers": deltas.get("current_subscribers", 0),
            "forks_delta": deltas.get("forks_delta", 0),
            "forks": deltas.get("current_forks", 0),
        })
    rows.sort(
        key=lambda item: (
            item["stars_delta"] + item["subscribers_delta"] + item["forks_delta"],
            item["views"],
        ),
        reverse=True,
    )
    lines = [
        "| Repository | Attention | Interest growth | Adoption growth |",
        "|------------|----------:|----------------:|----------------:|",
    ]
    for row in rows[:DEFAULT_REPO_TABLE_LIMIT]:
        lines.append(
            f"| `{row['repo']}` " +
            f"| {row['views']:,} views / {row['visitors']:,} visitors " +
            f"| {_format_delta(row['stars_delta'])} stars ({row['stars']:,}) / " +
            f"{_format_delta(row['subscribers_delta'])} watchers ({row['subscribers']:,}) " +
            f"| {row['clones']:,} clones / {_format_delta(row['forks_delta'])} forks ({row['forks']:,}) |"
        )
    return lines


def _growth_table_source(per_repo_rows, growth):
    if per_repo_rows:
        return per_repo_rows
    rows = []
    for repo, row in growth.get("per_repo", {}).items():
        traffic = row.get("traffic", {})
        rows.append({
            "repo": repo,
            "total_views": traffic.get("views", 0),
            "total_uniques": traffic.get("uniques", 0),
            "total_clones": traffic.get("clones", 0),
            "total_clone_uniques": traffic.get("clone_uniques", 0),
        })
    return rows


def render():
    daily_rows = load_daily()
    referrer_rows = load_referrers()
    path_rows = load_paths()
    metric_rows = load_repo_metrics()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    totals = aggregate_totals(daily_rows)
    growth = growth_analytics(daily_rows, metric_rows)
    growth["totals"]["total_views"] = totals["total_views"]
    growth["totals"]["total_uniques"] = totals["total_uniques"]
    growth["totals"]["total_clones"] = totals["total_clones"]
    per_repo = aggregate_per_repo(daily_rows)
    ref_list = top_referrers(referrer_rows, limit=10)
    path_list = top_paths(path_rows, limit=10)
    asset_files = write_readme_svg_assets(
        ASSET_OUTPUT_DIR,
        build_readme_asset_data(daily_rows, per_repo, totals=totals),
    )
    asset_links = {
        name: (ASSET_DISPLAY_DIR / path.name).as_posix()
        for name, path in asset_files.items()
    }

    lines = [
        "# Reponomics Dashboard",
        "",
        "[![Collect Reponomics Data](../../actions/workflows/collect.yml/badge.svg)]"
        + "(../../actions/workflows/collect.yml)",
        "",
        f"<sub>Last updated: {now}</sub>",
        "",
    ]

    # --- Hero stat banner (replaces markdown summary table) ---
    lines.extend([
        _picture(asset_links["hero"], "Summary"),
        "",
    ])

    # --- Momentum line — owner-glanceable signals ---
    momentum = compute_momentum(daily_rows)
    bits = []
    if momentum.get("best_day") and momentum["best_day"].get("views", 0) > 0:
        streak = momentum.get("streak_days", 0)
        if streak >= 1:
            base = momentum.get("baseline", 0)
            bits.append(
                f"🔥 **{streak}-day streak** above baseline (~{int(base):,}/d)"
            )
        bd = momentum["best_day"]
        days_since = momentum.get("days_since_peak")
        ago = ""
        if days_since == 0:
            ago = "today"
        elif days_since == 1:
            ago = "yesterday"
        elif isinstance(days_since, int):
            ago = f"{days_since}d ago"
        bits.append(
            f"⭐ Best overall day: **{bd['views']:,} views** "
            + (f"({ago})" if ago else f"on {bd['date']}")
        )
        top = momentum.get("top_single_day")
        if top and top.get("views", 0) > 0:
            short = top["repo"].split("/", 1)[-1] if "/" in top.get("repo", "") else top.get("repo", "")
            bits.append(
                f"🏆 Best single-repo day: **`{short}`** {top['views']:,} on {top['date']}"
            )
    if bits:
        lines.extend([
            "<sub>" + " &nbsp;·&nbsp; ".join(bits) + "</sub>",
            "",
        ])

    if metric_rows:
        lines.extend([
            "<sub>" + _growth_line(growth) + "</sub>",
            "",
        ])

    # --- Charts: sparkline + activity always visible, bar + donut in disclosure ---
    if totals["total_views"] > 0:
        lines.extend([
            "### Views Trend",
            "",
            _picture(asset_links["sparkline"], "Views per day (last 30 days)"),
            "",
            "### Activity",
            "",
            _picture(asset_links["activity"], "Activity heatmap (last 90 days)"),
            "",
        ])

        # Bar chart and donut in a disclosure to save space
        lines.extend([
            "<details><summary><strong>Top Repositories &amp; Share</strong></summary>",
            "",
            _picture(asset_links["bar_chart"], "Top repositories by views"),
            "",
            _picture(asset_links["donut"], "View share across repos"),
            "",
            "</details>",
            "",
        ])

    # --- Insights (visible — these are the actionable bits) ---
    insights = actionable_insights(daily_rows, metric_rows, limit=3, growth=growth)
    if insights:
        lines.extend([
            "### Insights",
            "",
        ])
        for insight in insights:
            lines.append(f"- {insight}")
        lines.append("")

    # --- Per-repo breakdown (disclosure) ---
    if len(per_repo) > 1:
        # Always show top repos, collapse the rest
        default_rows = per_repo[:DEFAULT_REPO_TABLE_LIMIT]
        remaining_rows = per_repo[DEFAULT_REPO_TABLE_LIMIT:]

        lines.extend([
            "<details><summary><strong>Repositories</strong> " +
            f"&mdash; top {len(default_rows)} of {len(per_repo)}</summary>",
            "",
        ])
        lines.extend(_repo_table_lines(default_rows))
        lines.append("")

        if remaining_rows:
            lines.extend([
                f"<details><summary>Show all {len(per_repo)} repositories</summary>",
                "",
            ])
            lines.extend(_repo_table_lines(per_repo))
            lines.extend([
                "",
                "</details>",
            ])

        lines.extend([
            "",
            "</details>",
            "",
        ])

    growth_table_rows = _growth_table_source(per_repo, growth)
    if metric_rows and growth_table_rows:
        lines.extend([
            "<details><summary><strong>Repository Growth</strong> " +
            f"&mdash; top {min(DEFAULT_REPO_TABLE_LIMIT, len(growth_table_rows))} by growth</summary>",
            "",
        ])
        lines.extend(_repo_growth_table_lines(growth_table_rows, growth))
        lines.extend(["", "</details>", ""])

    # --- Referrers (disclosure) ---
    if ref_list:
        lines.extend([
            "<details><summary><strong>Top Referrers</strong> " +
            f"&mdash; {len(ref_list)} sources</summary>",
            "",
            "| Referrer | Views | Uniques |",
            "|----------|------:|--------:|",
        ])
        for r in ref_list:
            lines.append(
                f"| {r['referrer']} | {r['count']:,} | {r['uniques']:,} |"
            )
        lines.extend([
            "",
            "</details>",
            "",
        ])

    # --- Popular Content (disclosure) ---
    if path_list:
        lines.extend([
            "<details><summary><strong>Popular Content</strong> " +
            f"&mdash; top {len(path_list)} paths</summary>",
            "",
            "| Repository | Content | Views | Uniques |",
            "|------------|---------|------:|--------:|",
        ])
        for p in path_list:
            repo = p.get("repo", "")
            content = p.get("content") or p.get("title") or p["path"]
            lines.append(
                f"| `{repo}` | {content} | {p['count']:,} | {p['uniques']:,} |"
            )
        lines.extend([
            "",
            "</details>",
            "",
        ])

    # --- Footer ---
    lines.extend([
        "---",
        "",
    ])
    lines.extend(_update_notice_lines())
    lines.extend([
        "[Setup & Docs](docs/README.md)",
        "",
        "<sub>Generated by "
        + "[Reponomics Dashboard Template]"
        + "(https://github.com/reponomics/reponomics-dashboard)"
        + "</sub>",
        "",
    ])

    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(lines))

    print(f"README.md updated ({len(daily_rows)} daily rows, " +
          f"{len(totals['repos'])} repos, " +
          f"{len(ref_list)} referrers, {len(path_list)} paths, " +
          f"{len(asset_files)} SVG assets)")


if __name__ == "__main__":
    render()
