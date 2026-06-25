---
name: DASHBOARD_NARRATIVE_RECIPES.md
description: Narrative insight recipe framework for the HTML dashboard.
created: 2026-06-25
last_modified: 2026-06-25
---

# Dashboard Narrative Recipes

The HTML dashboard should become more than a traffic chart. Most maintainers
will not see dramatic daily traffic movement, and even when they do, traffic
alone rarely explains what the maintainer should do next. The dashboard should
therefore use the retained data packet to build small, evidence-backed stories:
what changed, what repository context was nearby, why it may matter, and what
is worth watching next.

This document defines a first recipe framework for that work. It is meant to
bridge the current dashboard surface and the richer contextual packet introduced
in ADR 028.

## Available Evidence

The retained packet can preserve these durable evidence families:

| Evidence family | Tables or payload fields | Narrative use |
| --- | --- | --- |
| Traffic | `traffic-daily.csv`, `traffic-snapshots.csv`, per-repo `repo_series`, summary `daily` | Attention spikes, drops, quiet streaks, weekday rhythm. |
| Discovery surface | `traffic-referrers.csv`, `traffic-paths.csv` | Where attention came from and which page absorbed it. |
| Growth counters | `repo-metrics.csv`, growth analytics, `summary.growth`, `insights_v2` | Interest and adoption movement through stars, watchers, forks, clones. |
| Community posture | `repo-metrics.csv` community fields, repository table `community` object | Readiness for new contributors, issue flow, and support. |
| Code and project events | `repo-commits.csv`, `repo-releases.csv`, `repo-release-assets.csv`, `repo-event-index.csv` | Nearby commits, docs changes, releases, and release assets that explain metric movement. |
| Codebase shape | `repo-languages.csv`, `repo-topics.csv`, `repo-code-frequency-weekly.csv` | Language/topic positioning and churn context. |
| Contributor shape | `repo-contributor-activity-weekly.csv` | Whether activity is broadening, narrowing, or over-concentrated. |
| Maintenance load | `repo-issue-pr-snapshots.csv`, `repo-issue-label-snapshots.csv` | Issue pressure, help-wanted/good-first-issue readiness, bug/support load. |
| Collection quality | `collection-days.csv`, `traffic-coverage.csv`, `collection-endpoints.csv`, `data_quality` | Whether silence is real, missing, delayed, or unsupported. |

The current UI already has useful placement points:

- the growth model cards: attention, interest, adoption;
- the momentum strip;
- the `What's moving` insight feed;
- the traffic overview and selected window model;
- referrer and popular-content tables;
- the repositories table, including community health;
- the collection-health calendar.

The first implementation should not replace these surfaces. It should make the
`What's moving` feed richer, add a contextual `What changed nearby` panel for
the selected repo/window, and add a compact repository timeline that combines
traffic, releases, commits, and maintenance load.

## Current Projection Gap

The richer context tables are canonical retained data, but most of them are not
yet projected into the dashboard JSON consumed by the browser. Today the visible
renderer primarily loads traffic, referrers, paths, repo metrics, collection
status, collection days, and traffic coverage. It exposes:

- summary-level totals, daily series, weekday series, repositories, referrers,
  paths, growth summary, `insights`, `insights_v2`, `data_quality`, and
  `traffic_reporting`;
- per-repository chunks containing `repo_series`, `repo_weekday`,
  `repo_referrers`, `repo_paths`, and per-repo growth analytics;
- repository summary rows with traffic totals, profile dates, and community
  health fields.

The first narrative implementation therefore needs a payload projection step.
Large per-repository evidence should live in repo chunks, while the summary
payload should carry only ranked portfolio-level highlights and enough metadata
to render the feed without loading every repo. The browser data-provider is
strict about chunk shape, so adding commits, releases, event rows, languages,
topics, contributor activity, code frequency, or issue labels requires explicit
loader, payload, validation, and scenario snapshot work.

The event index is the right join surface, but the first materialized version is
commit/release-derived. Topic changes, language shifts, issue load, pull request
load, contributor shifts, and code-frequency events still need explicit
derivation before recipes should treat them as event-spine rows.

Narrative rules should operate on the rendered scope by default. Repositories
excluded by configuration may remain in retained/exported CSV history, but they
should not produce visible insight cards unless the user has explicitly opted
into a full-retained-packet diagnostic view.

## Recipe Contract

Each narrative recipe should emit a structured candidate, not only prose.

Recommended fields:

| Field | Purpose |
| --- | --- |
| `id` | Stable recipe id, such as `attention_without_readiness`. |
| `repo` | Repository full name, or blank for portfolio-wide observations. |
| `window` | Date range the observation was scored against. |
| `headline` | Short user-facing story. |
| `body` | One to two sentences of conservative explanation. |
| `tone` | `opportunity`, `risk`, `watch`, `explain`, or `data_quality`. |
| `score` | Ranking score used for feed ordering. |
| `confidence` | `low`, `medium`, or `high`, based on sample size and evidence count. |
| `primary_metric` | Metric that moved or failed to move. |
| `evidence` | Linked facts: metric windows, events, paths, referrers, community fields, issue labels. |
| `missing_evidence` | Optional context gaps from endpoint status or unavailable tables. |
| `next_action` | Optional maintainer action, phrased as a suggestion, not an instruction. |

The language standard is deliberately cautious. Reponomics should say "near",
"aligned with", "followed", "during", and "may suggest" unless the data
actually proves causality. The product value is not certainty; it is putting the
right facts next to each other.

## Scoring Posture

The recipe scorer should prefer stories that are both notable and explainable.

Base scoring:

1. Detect a metric condition: spike, drop, sustained streak, conversion gap,
   clone-heavy pattern, downstream movement, maintenance increase, or quality
   gap.
2. Join nearby events within a configurable window:
   - same day for traffic/referrer/path observations;
   - 1-7 days for commits, docs changes, issue/PR snapshots, topics, and
     releases;
   - 1-14 days for release asset downloads, contributor activity, and weekly
     code-frequency data.
3. Boost score when two or more independent evidence families agree.
4. Penalize score when the selected window has poor traffic coverage or when a
   required endpoint is missing.
5. Diversify the feed by recipe type and repository so the dashboard does not
   show five variants of the same traffic spike.

Confidence guidance:

- `high`: the metric condition clears volume/sample floors, collection quality
  is healthy, and at least two context families support the story.
- `medium`: the metric condition is clear, but the story has only one context
  family or mild collection gaps.
- `low`: the observation is interesting but sparse, or it is mainly a watchlist
  item.

## Narrative Recipes

### 1. Attention Without Contribution Readiness

**Story:** A repository is getting meaningful attention, but its community setup
is weak, so visitor interest may not turn into contribution.

**Trigger:**

- views or visitors are above the repository's trailing baseline, or the repo is
  in the top quartile for portfolio attention in the selected window;
- stars, watchers, forks, or clones do not move much;
- community health is low or key files are missing: contributing guide, issue
  template, pull request template, README, license, or code of conduct.

**Evidence join:**

- traffic: views, visitors, referrers, paths;
- growth: star/watcher/fork deltas and conversion denominators;
- repository context: community fields from `repo-metrics.csv`;
- maintenance context: open issues/PRs and `help_wanted` or
  `good_first_issue` label counts when available.

**Example copy:**

`demo/widgets` drew 320 visitors this month, mostly to the README, but did not
gain contributors or forks. The repo is missing a contributing guide and issue
template, so new attention may not have an obvious path into participation.

**UI placement:**

- `What's moving` feed as an opportunity/risk card;
- repository table community column detail;
- selected-repo `What changed nearby` panel with the missing file signals.

**Fallback:**

If community profile data is unavailable, downgrade to a weaker
`attention_without_downstream_growth` story and show the endpoint gap.

### 2. Release Pulled Attention Forward

**Story:** A release or release asset appears near a traffic, clone, fork, or
referrer shift.

**Trigger:**

- a release was published within 7 days before a metric lift;
- clones, cloners, forks, release asset downloads, or release-page path views
  increased after the release;
- a new referrer appears or an existing referrer gains share during the same
  window.

**Evidence join:**

- event spine: `release` rows from `repo-event-index.csv`;
- releases/assets: tag name, release URL, asset count, asset download count;
- traffic: views, clones, cloners, referrers, paths;
- growth: fork/star/watcher deltas.

**Example copy:**

`demo/cli` shipped `v1.4.0` three days before clones rose above baseline. The
traffic did not spike much, but release assets and clone activity both moved,
which looks more like adoption than casual browsing.

**UI placement:**

- selected-repo timeline with release marker;
- `What's moving` feed when the release aligns with a metric lift;
- top referrers table row decoration for referrers that appear after the
  release.

**Fallback:**

If release rows exist but asset rows are empty, still tell the release story but
avoid asset-download claims. If releases endpoint failed, do not infer releases
from tags or commit subjects in the first pass.

### 3. Docs Or Example Change Found An Audience

**Story:** A documentation, example, or README change is followed by increased
views, search/referrer traffic, or popular-content concentration.

**Trigger:**

- an event-index commit classified as `docs`, `feature`, or `unknown` with a
  docs-like subject lands within 1-7 days before attention increases;
- popular paths include README, docs, examples, issues, discussions, or a
  specific content page;
- referrers include search, GitHub, docs site, package registry, or project
  website sources.

**Evidence join:**

- event spine: commit title, classification, URL, date, magnitude;
- traffic paths: README/docs/examples path rows;
- referrers: source and unique visitor counts;
- traffic trend: visitor or view lift versus trailing median.

**Example copy:**

`demo/sdk` updated examples on May 12, then README and docs paths became the
top viewed content for the week. Search traffic also rose, so the attention
looks tied to discovery material rather than a general repo browse.

**UI placement:**

- `What changed nearby` panel under the traffic chart;
- popular-content table with event chips for nearby docs/example commits;
- `What's moving` feed when the traffic lift clears baseline.

**Fallback:**

If commit classification is unavailable, use path/referrer evidence alone and
phrase the story as "documentation paths are carrying attention" rather than
"the documentation change caused attention."

### 4. Clone-Heavy, Star-Light Adoption

**Story:** Users are cloning the repository without starring, watching, or
forking it. This can be a practical adoption signal, not a popularity signal.

**Trigger:**

- clones or unique cloners are high relative to views;
- stars/watchers/forks remain flat;
- release, package, docs, or example events are nearby;
- repository has a tool/library language or topic profile.

**Evidence join:**

- traffic: clone counts, unique cloners, views;
- growth: star/watcher/fork deltas;
- event spine: release, docs, feature, dependency, or fix commits;
- topics/languages: CLI, library, SDK, action, package-manager, or framework
  positioning.

**Example copy:**

`demo/action-tools` had 44 clones from 18 visitors but no star movement. That is
not a failed traffic week; paired with recent release and GitHub Actions topics,
it may be quiet utility adoption.

**UI placement:**

- growth model adoption card;
- `What's moving` feed as an explain/opportunity card;
- repository comparison sort for adoption efficiency.

**Fallback:**

If topic/language context is missing, still show the metric pattern but avoid
guessing why users are cloning.

### 5. Maintenance Pressure Is Rising With Attention

**Story:** User attention is increasing while issue or pull request load is
also increasing, especially if support/bug labels dominate.

**Trigger:**

- views, visitors, clones, or stars rise across the selected window;
- open issues or open PRs increase, or sampled labels show more `bug`,
  `question`, `support`, or `stale` buckets;
- community health is weak, or issue/PR templates are missing.

**Evidence join:**

- traffic/growth: attention and interest deltas;
- issue/PR snapshots: open issue and PR counts;
- label snapshots: label buckets and sample sizes;
- community profile: issue template, pull request template, contributing guide;
- endpoint telemetry: whether issue sampling was complete enough to trust.

**Example copy:**

`demo/server` gained 90 visitors and 8 stars while open issues rose from 12 to
21. Most sampled labels are bugs or support questions, and there is no issue
template, so the repo may be attracting users faster than it is shaping intake.

**UI placement:**

- `What's moving` feed as a risk/watch card;
- selected-repo timeline with issue-load markers;
- repositories table secondary sort or badge for maintenance pressure.

**Fallback:**

If only `open_issues_count` from `repo-metrics.csv` exists, show a lower
confidence issue-load observation and omit label-specific language.

### 6. Contributor Concentration Risk

**Story:** Repository activity is highly dependent on one contributor while
attention, adoption, or maintenance demand is rising.

**Trigger:**

- contributor activity shows one contributor producing most commits/additions
  in recent weeks;
- traffic, clones, issues, or PR load increases;
- community contribution files are missing or there are few help-wanted or
  good-first-issue signals.

**Evidence join:**

- contributor activity: active contributor count, top contributor share,
  weekly commits/additions/deletions;
- traffic/growth: views, clones, stars, forks;
- community/labels: contributing guide, help-wanted/good-first-issue labels;
- code frequency: churn volume during the same period.

**Example copy:**

`demo/parser` is seeing more visitors and open issues, but the last four weeks
of commits are almost entirely from one maintainer. Without contribution
guidance or good-first-issue labeling, the project may have attention but little
collaboration surface.

**UI placement:**

- repository timeline and maintainer-load panel;
- `What's moving` feed only when paired with traffic or issue movement;
- portfolio overview as a "single-maintainer pressure" watchlist.

**Fallback:**

If GitHub contributor statistics are pending or unsupported, use
`collection-endpoints.csv` to explain the missing contributor context rather
than treating absence as one-contributor risk.

### 7. Code Churn Explains A Traffic Dip

**Story:** A traffic or interest dip appears during a high-churn refactor,
dependency migration, or deletion-heavy week, so the dip may be related to
internal work rather than loss of demand.

**Trigger:**

- views, visitors, clones, stars, or watchers drop below trailing baseline;
- code-frequency additions/deletions are high, especially deletion-heavy;
- commits are classified as `refactor`, `dependency`, `ci`, `tests`, or
  `unknown` rather than release/docs/feature;
- no release or docs event happened near the dip.

**Evidence join:**

- traffic/growth: metric drop and baseline;
- code frequency: additions/deletions and week start;
- event spine: commit classifications and commit titles;
- releases: absence of a nearby user-facing release.

**Example copy:**

`demo/core` views dipped during a deletion-heavy refactor week. There was no
release nearby, so this looks more like internal maintenance work than a clear
loss of user attention.

**UI placement:**

- traffic chart annotation on the dip window;
- selected-repo timeline;
- `What's moving` feed as an explain card, not a warning.

**Fallback:**

If code-frequency statistics are unavailable, use commit classifications alone
with lower confidence.

### 8. Positioning Shift Met A New Audience

**Story:** A topic, language, or referrer change suggests the repository is
being discovered by a different audience.

**Trigger:**

- topics or language shares change between captures;
- referrer mix shifts toward search, package registry, docs site, social, or
  another ecosystem-specific source;
- popular paths align with the new audience, such as docs, examples, releases,
  or package files;
- traffic or downstream counters move enough to clear the noise floor.

**Evidence join:**

- topics/languages: added/removed topics, dominant language share shift;
- referrers/paths: new or rising sources and pages;
- traffic/growth: visitor, clone, star, watcher, or fork movement;
- event spine: docs, release, feature, or language-related commits.

**Example copy:**

`demo/plugin-kit` added automation and GitHub Actions topics before GitHub and
search referrers grew. README traffic carried most of the increase, suggesting
the repo may be reaching a clearer audience.

**UI placement:**

- top referrers and popular-content tables with context chips;
- `What's moving` feed as an opportunity card;
- repository profile drawer or timeline.

**Fallback:**

If only latest topics/languages exist and no prior snapshot is available, show
the current positioning as context but do not call it a shift.

### 9. Silent But Healthy Utility

**Story:** A repository has low visible traffic but steady clones, forks,
watchers, or release asset activity. This helps maintainers avoid underrating
quiet infrastructure repos.

**Trigger:**

- views and visitors are below portfolio median;
- clones, unique cloners, forks, watchers, or release asset downloads are
  stable or rising;
- paths/referrers are sparse but collection quality is healthy;
- code/release activity is low to moderate rather than abandoned.

**Evidence join:**

- traffic/growth: low attention with downstream movement;
- releases/assets: asset downloads or recent release availability;
- contributor/code context: light but recent commits, no severe endpoint gaps;
- collection quality: proves quietness is observed, not missing.

**Example copy:**

`demo/config` is not drawing many visitors, but it keeps getting clones and
watchers. With healthy collection coverage and recent maintenance commits, this
looks like a quiet utility repo rather than a dead one.

**UI placement:**

- portfolio watchlist;
- adoption card;
- `What's moving` feed when downstream movement clears the sample guard.

**Fallback:**

If collection coverage is poor, show a data-quality card instead of a quiet
utility story.

### 10. Data Gap, Not Product Signal

**Story:** A missing or strange metric pattern is better explained by collection
health, GitHub API lag, or unsupported endpoint states than by repository
behavior.

**Trigger:**

- traffic drops to zero across many repositories on the same collection day;
- `collection-days.csv` shows skipped or error repos;
- `traffic-coverage.csv` marks lag or missing reporting;
- `collection-endpoints.csv` shows endpoint `pending`, `unsupported`,
  `no_content`, rate-limit, or permission errors.

**Evidence join:**

- collection days: run count, coverage ratio, skipped/error repos;
- traffic coverage: reported dates and reasons;
- endpoint telemetry: endpoint key, status, HTTP status, retry-after;
- metric observations: affected repo/date range.

**Example copy:**

Traffic appears flat on June 21, but the collection calendar shows partial
coverage and the contributor statistics endpoint was still pending. Treat this
window as incomplete before comparing it to earlier weeks.

**UI placement:**

- collection-health calendar;
- dashboard notice region;
- `What's moving` feed only when a data gap would otherwise create a misleading
  story.

**Fallback:**

This recipe should be allowed to suppress lower-confidence metric stories in
the same window.

## Feed Composition

The dashboard should rank candidates with a two-stage pipeline:

1. Build candidate facts from each recipe.
2. Compose the visible feed using diversity and trust rules.

Recommended composition rules:

- show at most one `data_quality` card unless it suppresses multiple misleading
  metric cards;
- show at most two cards per repository in the default portfolio view;
- prefer cards that include a metric movement plus a nearby event;
- prefer a balanced mix of `opportunity`, `risk`, `watch`, and `explain`;
- show lower-confidence cards only when there are too few medium/high
  confidence cards;
- hide recipes whose required evidence is absent unless the absence itself is
  the point of the card.

For a typical 10-20 repository portfolio, the default feed should aim for:

- 2-3 high-signal narrative cards;
- 1 portfolio-level watchlist item;
- 1 data-quality or quiet-repo explanation when relevant.

## Dashboard UI Direction

The HTML dashboard should keep the current analytical controls and add
narrative context in layers.

### Portfolio View

Use the existing top-level structure:

- growth model cards stay quantitative;
- momentum stays compact;
- `What's moving` becomes the main story feed;
- repository table gains narrative badges only when they summarize a real
  recipe, not as decorative status labels.

### Selected Repository View

When the user focuses a repository, add:

- a `What changed nearby` panel under the primary chart;
- a timeline of metric events, releases, commits, and issue/PR pressure;
- a small evidence list with links to GitHub commits, releases, paths, and
  referrers where available.

### Recipe Card Shape

Each card should answer four questions in order:

1. What happened?
2. What repository context was nearby?
3. Why might the maintainer care?
4. What evidence supports this?

Example card structure:

```text
Release seems to be turning into adoption
demo/cli shipped v1.4.0 three days before clones rose above baseline.
44 clones / 18 visitors; +3 forks; release assets downloaded 21 times.
Evidence: release v1.4.0; clones chart; release assets
```

## Implementation Notes

The current `insights_v2` shape is a good starting point, but contextual
recipes need a richer payload than `kind`, `subtype`, `metric`, and `text`.
The next implementation pass should add a narrative insight module that:

1. reads canonical CSV rows for context families;
2. builds normalized per-repo windows;
3. joins metric candidates to `repo-event-index.csv`;
4. emits structured narrative candidates;
5. lets the existing dashboard renderer consume those candidates before falling
   back to legacy metric-only insights.

The event spine should stay the main join surface for commits and releases, but
not every recipe needs to wait for every source table. Recipes should degrade
cleanly:

- no event index: show metric-only growth insights;
- no community data: do not make readiness claims;
- pending stats endpoints: show data-quality context;
- no historical topic/language snapshots: describe current positioning, not
  change over time.

Commit context is observed from GitHub APIs, not from a cloned/backfilled
repository history. The first collected commit rows may have blank file counts,
path samples, additions, and deletions, so early commit classification should be
treated as subject-line heuristic evidence unless richer commit detail is added.

The demo scenario corpus should include normal, non-spectacular data. At least
one scenario should show each of these patterns without relying on cartoonish
traffic spikes:

- attention without readiness;
- release-driven clone adoption;
- docs path lift;
- maintenance pressure;
- quiet utility adoption;
- data gap suppression.

## Open Questions

- Should narrative recipes be generated entirely in Python during
  `load_data.py`, or should the browser derive some selected-window narratives
  from richer JSON payloads?
- How many event rows should be shipped to the browser for each repo before the
  payload becomes too heavy for larger portfolios?
- Should recipes have stable public ids that appear in CSV export/provenance, or
  are they dashboard-only projections?
- Should the repository table show one top recipe badge per repo, or should all
  narrative exploration happen inside the selected-repo view?
