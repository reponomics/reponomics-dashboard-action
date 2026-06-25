# Dashboard Narrative Insights

The HTML dashboard should not ask maintainers to care about traffic charts in
isolation. Most repositories have quiet, low-amplitude traffic most of the time.
The useful product move is to join ordinary metric movement to repository
context and present it as inspectable evidence: what changed, what was nearby,
and why the maintainer might want to look now.

The dashboard should use cautious language. These recipes detect correlation and
context, not causality. Preferred phrasing is "near", "after", "aligned with",
"during", "suggests", and "worth inspecting".

## Framework

Each recipe should produce a small narrative card with the same contract:

- `recipe`: stable machine name for the pattern.
- `repo`: repository full name, when the card is repo-specific.
- `title`: one sentence describing the pattern.
- `summary`: maintainer-facing explanation with cautious causal language.
- `tone`: `positive`, `warning`, `neutral`, or `attention`.
- `anchor_date`: date the story is centered on, when known.
- `evidence`: compact label/value/detail facts used to justify the card.
- `events`: nearby code/project events, with title, date, classification, and
  URL when available.
- `action`: suggested next inspection step.

Ranking should favor:

1. Cross-signal cards over single-metric cards.
2. Recent cards over old cards.
3. Cards with explicit code/project events over generic traffic movement.
4. Diversity across recipes and repositories, so the panel does not become a
   list of five variations of the same spike.

The first implementation can use deterministic heuristics. Later, the same
contract can support more advanced scoring or LLM-written summaries.

## Narrative Recipes

### 1. Attention Conversion Gap

Signal: a repository has meaningful visitors/views in the selected recent
window, but stars, watchers, and forks barely moved.

Data used:

- `traffic-daily.csv`: recent views and visitors.
- `repo-metrics.csv`: star, watcher, and fork deltas from retained snapshots.
- Optional community profile fields for readiness context.

Maintainer story:

> People are looking, but visible downstream interest is not moving yet.

This is useful for the common "lots of visitors, no contributors" case. The
action is to inspect whether the README, examples, contribution path, or install
path gives visitors a next step.

### 2. Event-Aligned Attention

Signal: a local traffic peak or sharp recent lift occurs near a commit or
release in `repo-event-index.csv`.

Data used:

- `traffic-daily.csv`: peak day, recent baseline, and delta.
- `repo-event-index.csv`: nearby commit/release event, classification, title,
  magnitude, URL.
- `repo-commits.csv` and `repo-releases.csv` indirectly through the event spine.

Maintainer story:

> The dashboard can point at what was happening in the repository when attention
> changed.

This should be phrased as context, not proof. A docs commit two days before a
visitor lift is a useful clue even when it is not the only cause.

### 3. Release Adoption Lift

Signal: a release event is present in or near the current window, and clone,
fork, or release-asset activity is visible.

Data used:

- `repo-releases.csv`: release publication, tag/name, asset counts/downloads.
- `traffic-daily.csv`: clone and cloner totals.
- `repo-metrics.csv`: fork delta.
- `repo-event-index.csv`: normalized release event for timeline display.

Maintainer story:

> Adoption may be showing up as clone or fork behavior after a release, even if
> page views are ordinary.

This handles repositories where users install or clone directly without
producing dramatic traffic swings.

### 4. Attention Before Readiness

Signal: a repository is receiving attention while community profile fields show
missing contributor affordances or low health.

Data used:

- `traffic-daily.csv`: recent views/visitors.
- `repo-metrics.csv`: community health percentage and presence of README,
  license, contributing guide, issue template, PR template, code of conduct.

Maintainer story:

> The repo is being inspected before it is fully ready to receive contributors.

This turns otherwise bland traffic into a practical next step: tighten the
on-ramp while people are already looking.

### 5. Maintenance Pressure

Signal: user attention or adoption is visible while issue/PR snapshots show a
growing or substantial maintenance queue.

Data used:

- `traffic-daily.csv`: visitors, views, clones.
- `repo-issue-pr-snapshots.csv`: open issues, open PRs, stale or unanswered
  counts when available.
- `repo-issue-label-snapshots.csv`: optional bug/help-wanted/question label
  pressure.

Maintainer story:

> More users may be arriving while the support surface is already carrying load.

This is especially valuable for maintainers because it connects attention to
workload, not vanity metrics.

### 6. Code Churn Context

Signal: code-frequency or commit events show heavy internal change while traffic
is flat, down, or just beginning to react.

Data used:

- `repo-code-frequency-weekly.csv`: additions/deletions by week.
- `repo-commits.csv` / `repo-event-index.csv`: classified commits.
- `traffic-daily.csv`: recent trend or quiet baseline.

Maintainer story:

> The repo was changing internally during a quiet or shifting attention period.

This avoids over-reading a dip. A refactor-heavy week may explain why there was
no user-facing lift yet.

### 7. Contributor Concentration

Signal: repository attention/adoption is visible, but contributor activity is
concentrated in one person or very few people.

Data used:

- `repo-contributor-activity-weekly.csv`: active contributor count, commits,
  additions, deletions.
- `traffic-daily.csv`: visitors and clones.
- `repo-metrics.csv`: growth counters.

Maintainer story:

> Interest is reaching the repository, but maintenance capacity may still be
> concentrated.

This can motivate contributor docs, issue labeling, or a release note asking for
specific help.

### 8. Discovery And Positioning Signal

Signal: referrers, popular paths, topics, and language composition line up
around a visible attention pattern.

Data used:

- `traffic-referrers.csv`: latest per-repo referrers.
- `traffic-paths.csv`: README/docs/releases/issues path interest.
- `repo-topics.csv`: repository topics.
- `repo-languages.csv`: dominant language.
- `traffic-daily.csv`: current visitor context.

Maintainer story:

> The traffic has a discoverability shape, not just a volume shape.

For example, search traffic plus docs path views and a clear language/topic
profile suggests the repository may be attracting a specific audience.

## Implementation Notes

The dashboard payload should include a derived `narratives` array. The renderer
should compute it server-side from retained CSVs so plaintext, encrypted,
standalone, and lazy dashboards share the same stories. The browser should only
filter and render the already-ranked cards.

The UI should show a short "Stories to inspect" panel near the top of the
dashboard, before detailed controls and charts. The panel should not replace
charts or tables; it should give maintainers a reason to inspect them.
