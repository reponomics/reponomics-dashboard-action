# Dashboard Insight Methodology

This document describes how Reponomics identifies dashboard "Next moves" and
other insight-like prompts from retained GitHub repository data.

The methodology is intentionally deterministic. The dashboard does not call an
analyst service, language model, or live GitHub endpoint while rendering. It
loads retained artifacts, derives candidate observations from named recipes,
scores those candidates, diversifies the final set, and renders the selected
items with evidence and a suggested next action.

## Product Intent

Reponomics works with small-to-medium GitHub projects where raw traffic, clone,
star, and fork counts are often too plain to be useful on their own. The insight
layer should help maintainers answer:

- What deserves a closer look?
- Which public-facing improvement is most likely to help right now?
- Where did codebase activity, project presentation, and audience attention sit
  near each other?
- What should I inspect next in the raw tables?

The output should read as practical maintainer guidance. It should not pretend
to be a business intelligence system or a statistical causal model.

## Data Boundary

Insight generation uses retained artifact data restored during publish/render.
The renderer should not fetch live context while building dashboard payloads.

Primary retained inputs:

| Input | Used for |
| --- | --- |
| `traffic-daily.csv` | Recent views, visitors, clones, cloners, active days, peaks, prior windows |
| `traffic-paths.csv` | Popular entry pages and content surfaces |
| `traffic-referrers.csv` | Discovery sources and referrer context |
| `repo-metrics.csv` | Stars, watchers/subscribers, forks, community profile fields |
| `repo-event-index.csv` | Normalized commit and release event spine |
| `repo-release-assets.csv` | Release asset count/download context |
| `repo-issue-pr-snapshots.csv` | Open issue/PR load and recent triage context |
| `repo-languages.csv` | Latest and previous language snapshots |
| `repo-topics.csv` | Latest and previous topic snapshots |
| `repo-code-frequency-weekly.csv` | Recent additions/deletions context |

`repo-event-index.csv` is derived from retained event source tables. Today it is
populated from `repo-commits.csv` and `repo-releases.csv`. It is the preferred
join surface for event-aware recipes because future event sources can be added
without changing the dashboard payload shape.

## Pipeline

1. **Build per-repo context**
   - Group retained rows by repo.
   - Restrict dashboard-facing surfaces to the published repo set.
   - Compute recent-window traffic statistics.
   - Load latest community, topic, language, issue/PR, path, referrer, and
     event context.

2. **Generate candidates**
   - Run every named recipe against each repo context.
   - Each recipe either emits a normalized candidate or returns nothing.
   - Recipes use volume floors, sample guards, time-window checks, and missing
     data checks to avoid low-signal cards.

3. **Score candidates**
   - Scores are heuristic weights, not probabilities.
   - Scores should reflect actionability and salience:
     - more current attention usually increases priority;
     - stronger downstream growth can increase priority;
     - missing readiness files can increase priority when attention exists;
     - event magnitude or release asset activity can increase event cards;
     - context-only candidates should remain below stronger evidence bundles.

4. **Diversify**
   - Sort candidates by score.
   - Prefer distinct repos first so one high-volume repo does not consume the
     whole feed.
   - Backfill with remaining high-scoring candidates when the diverse pass does
     not fill the requested limit.

5. **Render with evidence**
   - Every narrative card should include:
     - a subtype;
     - a tone such as `opportunity`, `watch`, or `explain`;
     - a title and concise summary;
     - evidence rows with labels, values, and context;
     - nearby context when useful;
     - a concrete "Try next" action.

## Current Recipe Catalog

### Narrative Next Moves

Implemented in
`dashboard_action/runtime/scripts/load_data_modules/narratives.py`.

| Recipe subtype | Trigger shape | Example next action |
| --- | --- | --- |
| `event_aligned_attention` | A peak day is meaningfully above trailing baseline and near a retained commit or release event. | Compare paths, referrers, and follow-on growth around that event. |
| `release_adoption_lift` | A recent release window has clones, cloners, fork movement, or release asset downloads. | Use release notes and install docs as the next comparison point. |
| `docs_found_audience` | Docs/example activity exists and the selected window has meaningful views. | Check whether the docs page or README explains the next step clearly. |
| `steady_attention_next_step` | A repo has steady attention, enough visitors and active days, but little downstream movement. | Add a short README path from problem to install command to first result. |
| `discovery_surface_next_step` | A repo has traffic but a lightweight discovery surface, such as few retained topics. | Add GitHub topics and make the README opening sentence problem-shaped. |
| `attention_without_readiness` | A repo has attention while known community/readiness files are missing. | Add the highest-impact missing files. |
| `maintenance_pressure` | A repo has audience attention and enough open issue/PR load to warrant triage structure. | Triage labels and contribution docs before the next traffic bump. |
| `code_churn_context` | Views are down versus the prior window while recent code-frequency churn is high. | Use the churn window as a starting point when reviewing the dip. |
| `positioning_shift` | Topics or language mix changed and the repo has enough attention to inspect positioning. | Check whether repo description, topics, and README match the audience now arriving. |

### Metric and Growth Fallbacks

Implemented in:

- `dashboard_action/runtime/scripts/load_data_modules/insights.py`
- `dashboard_action/runtime/scripts/load_data_modules/trend_insights.py`
- `dashboard_action/runtime/scripts/load_data_modules/growth/`

These are simpler fallback candidates used when contextual narrative cards are
not available or when they score lower.

| Recipe family | Trigger shape |
| --- | --- |
| Window change | 7-day-over-7-day views or clones change with minimum floors. |
| Spike/drop | Latest day differs from a trailing median/MAD baseline enough to be notable. |
| High attention, low interest | Views and visitors are meaningful while stars/watchers/forks do not move. |
| Quiet resonance | Downstream growth appears on comparatively low traffic. |
| Clone-heavy, star-light | Clone volume is high relative to views without matching star movement. |
| Fork/watcher/counter movement | Repository counters move enough to become visible in the selected window. |
| Downstream without traffic spike | Stars/watchers/forks move while traffic stays comparatively low. |

### Readiness Queue

Implemented in
`dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/readiness-queue.js`.

This is a client-side recipe over the visible published repos. It ranks known
community-health gaps by:

- missing readiness signals;
- selected-window views plus clones;
- community health percentage when available.

Tracked readiness signals:

- README
- License
- Contributing guide
- Issue template
- Pull request template
- Code of conduct

### Opportunity Map

Implemented in
`dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/opportunity-map.js`.

This is not a "Next move" recipe, but it uses the same principle of simple,
inspectable heuristics:

- x-axis: attention score from views plus visitors;
- y-axis: downstream growth score from stars/watchers/forks;
- mark size: clone activity from clones plus unique cloners;
- quadrant labels: seed discovery, clarify next step, protect niche pull,
  amplify.

### Code Event Graph

Implemented in
`dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/event-graph.js`.

The graph is a navigation and inspection surface over `event_graph`, which is
built from `repo-event-index.csv`. It displays retained commit and release
markers in the selected traffic window, with nearby traffic counts attached to
the event metadata.

## Copy Rules

Insight language should be clear, active, and useful.

Prefer:

- "near"
- "during"
- "in the same window"
- "has audience context"
- "use as the next comparison point"
- "check whether"
- "try next"

Avoid:

- overclaiming intent, causation, or business impact;
- defensive disclaimers on every card;
- academic uncertainty phrasing that makes the product feel timid;
- vague advice such as "monitor this" without a concrete inspection path.

The dashboard itself should make the evidence visible. Methodological caveats
belong in documentation, not repeated inside every product surface.

## Extension Checklist

When adding or changing a recipe:

1. **Name the subtype**
   - Use a stable snake-case subtype.
   - Add it to this document.

2. **Declare required data**
   - Identify which retained CSV fields are required.
   - Specify behavior when data is absent, stale, or partial.

3. **Add guards**
   - Use minimum sample counts, volume floors, or date-window checks.
   - Avoid surfacing cards for one-off zeros or tiny movements.

4. **Define scoring**
   - Explain what raises the score.
   - Keep scores comparable enough that diversification produces sensible
     mixed feeds.

5. **Attach evidence**
   - Include at least two evidence rows for narrative cards when possible.
   - Prefer values already visible elsewhere in the dashboard.

6. **Write a concrete action**
   - The action should tell the maintainer what to inspect or improve next.
   - It should be feasible without an analyst or external service.

7. **Test with scenarios**
   - Add or update dashboard scenario data for high-signal and flat-curve cases.
   - Include at least one case where the recipe should not fire.

8. **Review copy in the UI**
   - Check that the card reads well in the lead story, queue, and mobile layout.
   - Confirm the copy does not imply more than the evidence supports.

## Evaluation Notes

The current methodology should be evaluated against two portfolio shapes:

- **High-signal demos:** sharp peaks, visible releases, obvious traffic changes.
- **Flatter real projects:** modest traffic, small counter movement, incomplete
  project readiness, and long quiet periods.

For public release, flat-curve behavior is especially important. The strongest
recipes are often not "what explains the spike?" but "what should the maintainer
do next to make existing attention easier to convert into useful adoption or
contribution?"

## Related Documents

- `docs/adr/028-contextual-data-packet-and-collection-model.md`
- `docs/RETAINED_DATA_ERD.md`
- `docs/CSV_EXPORT.md`
- `docs/promotional/dashboard-guide/index.html`
