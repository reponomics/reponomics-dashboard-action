# ADR 027: Contextual Data Packet And Collection Model

Date: 2026-06-24

## Status

Proposed

## Context

Reponomics is approaching a beta-user milestone. The product has spent recent
development effort hardening release workflows, retained-data security,
template compatibility, provenance, and operational recovery. Those foundations
remain important, but they are no longer enough to make the dashboard feel
valuable to repository owners.

The current dashboard can answer questions such as:

- how many views, visitors, clones, cloners, stars, watchers, and forks changed;
- which repositories, paths, and referrers are currently prominent;
- whether collection and GitHub traffic reporting are healthy.

Those are necessary observations, not a compelling maintainer narrative. Most
repositories do not have dramatic traffic spikes. Growth is often gradual, noisy,
and sparse. A useful dashboard must therefore explain ordinary movement by
joining metric changes to project events and codebase activity:

- What changed in the code when traffic rose or fell?
- Did a release, topic change, documentation push, or issue surge precede a
  referrer change?
- Is attention arriving while maintenance load is growing?
- Is adoption increasing after release assets, examples, or documentation
  changed?
- Which repositories deserve deeper attention because their code/project context
  makes their ambient metrics meaningful?

The previous architecture treated broad collection scale as a major product
goal. That remains technically possible, but it is not the highest-value beta
direction. For most maintainers, a more valuable default is intensive study of a
curated portfolio of roughly 20-30 repositories. Reponomics should collect enough
context to make those repositories narratable, comparable, and actionable rather
than merely chartable.

There are currently no external users. Deliberate breaking changes are therefore
allowed when they produce a better beta product and are recorded in
`template-contract.yml` and release notes. Backwards compatibility should be
preserved when it does not compromise the future product model. It should not
prevent us from establishing a better retained packet now.

## Decision

Adopt a contextual retained data packet organized around four layers:

1. Metric observations.
2. Project/code observations.
3. A derived event spine.
4. Narrative insight projections.

The dashboard's strategic data model is no longer "traffic plus repo counters."
It is a local, portable evidence packet that lets the renderer explain metric
movement through project activity and codebase patterns.

### Product Collection Profile

The default beta profile should be:

- collect fewer repositories by default, with a practical target of 20-30;
- prefer repositories selected by explicit configuration, recent activity, or
  user interest over broad automatic collection;
- collect richer project and code context for each selected repository;
- keep traffic preservation daily because GitHub traffic data has a short
  rolling window;
- collect slower-moving metadata and graph data less frequently when possible;
- make collection cost visible per endpoint family.

This is a product-level default, not a hard storage limit. The retained packet
should still support larger installations, but richer insight quality matters
more than maximizing repository count.

### Data Packet Layers

#### Layer 1: Metric Observations

Existing retained tables stay conceptually valid:

- `traffic-log.csv`
- `traffic-daily.csv`
- `traffic-snapshots.csv`
- `traffic-referrers.csv`
- `traffic-paths.csv`
- `repo-metrics.csv`
- `collection-status.csv`
- `collection-days.csv`
- `traffic-coverage.csv`

These tables answer "what moved?" and "can we trust the collection window?"

#### Collection Cadence, Gaps, And Idempotency

The retained packet must be failure tolerant. It should not assume exactly one
successful collection per day, and it should not hide missing data by filling
synthetic observations. Missed workflow days, token failures, endpoint outages,
rate limits, and GitHub endpoint states such as statistics `pending` are part
of the retained evidence.

Policy:

- Store successful observations at the grain the endpoint naturally supports.
  Tables keyed by `captured_at` can retain multiple runs per day.
- Record collection health separately from observations. Use
  `collection-status.csv` for repo/run-level collection outcome and
  `collection-endpoints.csv` for endpoint-level status, including optional
  endpoint failures and non-ready API states.
- Treat API lag as expected behavior. `captured_at` records when the dashboard
  saw an observation; endpoint-specific event dates such as traffic `ts`,
  commit `committed_at`, release `published_at`, and statistics `week_start`
  record when the observed activity belongs. Traffic endpoints can publish
  delayed data inside their rolling API window, so later runs may legitimately
  improve or replace earlier observations for prior traffic days.
- Prefer idempotent row identities. Re-running the same collection window
  should deduplicate stable facts such as commit SHAs, while per-run observation
  tables should keep distinct `captured_at` rows.
- Do not backfill by default. Backfill may be added later for selected endpoint
  families, but the base model starts accumulating from the first successful
  run that includes the table.
- Do not use artifact retention as a CSV history horizon. Artifact retention is
  backup survival; retained CSV history is cumulative unless an explicit,
  versioned migration changes it.
- Derived daily tables are summaries. They are useful for dashboard views but
  should not be treated as the only authoritative evidence when multiple runs
  occur on the same day.

#### Layer 2: Project And Code Observations

Add retained tables for source events and repository context. These are factual
observations, not final insights.

| Table | Source | Purpose |
| --- | --- | --- |
| `repo-commits.csv` | GitHub commits API | Commit facts observed on the default branch for event correlation. |
| `repo-commit-observations.csv` | GitHub commits API | Per-run default-branch commit window for detecting rewritten history. |
| `repo-releases.csv` | GitHub releases API | Release events, tags, asset totals, and publication state. |
| `repo-release-assets.csv` | GitHub releases API | Per-asset download and packaging signals. |
| `repo-languages.csv` | Repository languages API | Codebase composition snapshots. |
| `repo-topics.csv` | Repository topics API | Discovery and positioning context. |
| `repo-issue-pr-snapshots.csv` | Issues and pull request APIs plus repo detail counters | Maintenance load and collaboration state. |
| `repo-issue-label-snapshots.csv` | Issues API label aggregation | Label-based maintenance pressure signals without issue-level retention. |
| `repo-code-frequency-weekly.csv` | GitHub statistics API | Weekly additions/deletions when available. |
| `repo-contributor-activity-weekly.csv` | GitHub statistics API | Contributor breadth and weekly contribution load when available. |
| `collection-endpoints.csv` | Collector instrumentation | Endpoint status, rate-limit/cache behavior, and unsupported-data states. |

Commit context is intentionally collected from GitHub's commits API instead of
cloning each tracked repository. Cloning would make collection duration scale
poorly for portfolios with many repositories, while storage is comparatively
cheap. The first implementation starts observing commits when the feature is
enabled; it does not perform historical backfill. `repo-commits.csv` stores
commit facts observed at least once, while `repo-commit-observations.csv`
records the default-branch commit window seen during each collection run. This
keeps rewritten branch history honest without mutating or deleting older
observations.

#### Layer 3: Derived Event Spine

Add `repo-event-index.csv` as the normalized join surface for narrative work.

Every meaningful code/project occurrence becomes an event row with a stable
identity and enough metadata to join against traffic and growth windows:

| Column | Meaning |
| --- | --- |
| `repo` | Repository full name. |
| `event_id` | Stable source-derived event id. |
| `event_type` | `commit`, `release`, `release_asset`, `topic_change`, `language_shift`, `issue_load`, `pr_load`, etc. |
| `event_ts` | Event date/time used for correlation. |
| `event_date` | UTC date bucket. |
| `title` | Short display title. |
| `url` | GitHub URL when available. |
| `primary_sha` | Commit SHA when applicable. |
| `release_id` | Release id when applicable. |
| `issue_or_pr_number` | Issue or PR number when applicable. |
| `magnitude` | Numeric event weight for ranking. |
| `classification` | Coarse category such as `docs`, `release`, `maintenance`, `feature`, `churn`, `community`. |
| `source_table` | Source retained table. |
| `captured_at` | Collection timestamp. |
| `schema_version` | Retained packet schema version. |

The event spine prevents the renderer from hard-coding every source table. It
also gives future AI or rules-based insight layers one consistent event grammar.

#### Layer 4: Narrative Insight Projections

Derived insight code should move from "rank metric anomalies" to "rank
explainable observations." Initial insight classes:

| Insight class | Required data | Example |
| --- | --- | --- |
| Traffic near code activity | traffic daily + event index + commits | "Docs/example commits landed two days before visitor growth from search." |
| Release/referrer correlation | releases + release assets + referrers | "Release v0.28 aligned with traffic from a specific referring site." |
| Adoption without attention | clones/forks + traffic + releases | "Clone growth rose without visitor growth after a release asset shipped." |
| Attention without readiness | traffic/growth + community + issues | "Views are rising while issue templates and contribution docs are missing." |
| Maintenance pressure | issues/PR snapshots + traffic | "User attention rose while open issue load grew faster than closures." |
| Code churn context | code frequency + commits + traffic | "A traffic dip occurred during high-deletion refactor work, not after a user-facing release." |
| Positioning signal | topics/languages/referrers | "Referrer growth matches a topic/language shift; docs may be attracting a new audience." |

The dashboard should display these as contextual observations with evidence
links, not as overconfident causal claims. The preferred language is correlation
and nearby activity: "near", "after", "aligned with", "during", "suggests".

## Proposed Table Shapes

### `repo-commits.csv`

Row identity: `repo`, `sha`.

Columns:

- `repo`
- `sha`
- `parent_sha`
- `committed_at`
- `authored_at`
- `author_name`
- `author_email_hash`
- `author_login`
- `committer_login`
- `message_subject`
- `message_body_hash`
- `files_changed`
- `additions`
- `deletions`
- `changed_paths_sample`
- `classification`
- `associated_pr_number`
- `source`
- `captured_at`
- `schema_version`

Notes:

- Store an email hash, not raw email.
- Store only the subject and a body hash by default.
- `changed_paths_sample` is a compact pipe-delimited sample or JSON string,
  capped to prevent large rows.
- `classification` can start heuristic-only: docs, tests, ci, release, refactor,
  feature, fix, dependency, unknown.
- This is an observed commit fact table, not a complete clone-derived history.
  Rows start accumulating when collection begins and are deduplicated by
  `repo`, `sha`.

### `repo-commit-observations.csv`

Row identity: `repo`, `captured_at`, `default_branch`, `sha`.

Columns:

- `repo`
- `captured_at`
- `default_branch`
- `branch_head_sha`
- `sha`
- `parent_sha`
- `committed_at`
- `position_from_head`
- `source`
- `schema_version`

Each row means that a commit appeared in the sampled default-branch window for
that collection run. This table preserves evidence of branch shape over time,
including force-pushes or rebases, without requiring daily clones or attempting
to rewrite previously observed commit facts.

### `repo-releases.csv`

Row identity: `repo`, `release_id`.

Columns:

- `repo`
- `release_id`
- `node_id`
- `tag_name`
- `target_commitish`
- `target_sha`
- `name`
- `draft`
- `prerelease`
- `immutable`
- `created_at`
- `published_at`
- `author_login`
- `html_url`
- `asset_count`
- `asset_download_count`
- `body_hash`
- `captured_at`
- `schema_version`

### `repo-release-assets.csv`

Row identity: `repo`, `asset_id`, `captured_at`.

Columns:

- `repo`
- `release_id`
- `asset_id`
- `name`
- `label`
- `content_type`
- `state`
- `size_bytes`
- `download_count`
- `created_at`
- `updated_at`
- `browser_download_url`
- `captured_at`
- `schema_version`

Asset rows are snapshots because download counts change over time.

### `repo-languages.csv`

Row identity: `repo`, `captured_at`, `language`.

Columns:

- `repo`
- `captured_at`
- `language`
- `bytes`
- `share`
- `schema_version`

### `repo-topics.csv`

Row identity: `repo`, `captured_at`, `topic`.

Columns:

- `repo`
- `captured_at`
- `topic`
- `schema_version`

### `repo-issue-pr-snapshots.csv`

Row identity: `repo`, `captured_at`.

Columns:

- `repo`
- `ts`
- `captured_at`
- `open_issues_count`
- `open_prs_count`
- `closed_issues_recent`
- `merged_prs_recent`
- `stale_open_issues_count`
- `stale_open_prs_count`
- `unanswered_issue_count`
- `issue_sample_count`
- `pr_sample_count`
- `source`
- `schema_version`

The first implementation can populate only the cheap fields:
`open_issues_count`, `open_prs_count`, and sample counts. Stale/unanswered
fields can come later after pagination and labeling behavior are settled.

### `repo-issue-label-snapshots.csv`

Row identity: `repo`, `captured_at`, `item_type`, `state`, `label_name`.

Columns:

- `repo`
- `ts`
- `captured_at`
- `item_type`
- `state`
- `label_name`
- `label_key`
- `label_bucket`
- `labeled_item_count`
- `sample_item_count`
- `sample_scope`
- `source`
- `schema_version`

This table is a tall aggregate fact table for labels seen in sampled open
issues and pull requests. Labels retain the exact GitHub label string in
`label_name`; `label_key` normalizes the name for grouping, and `label_bucket`
maps common labels such as `bug` or `enhancement` into coarse maintainer-facing
categories when possible. Counts such as "open issues labeled bug" are derived
by filtering or grouping these rows within a capture.

### `repo-code-frequency-weekly.csv`

Row identity: `repo`, `week_start`.

Columns:

- `repo`
- `week_start`
- `additions`
- `deletions`
- `captured_at`
- `source_status`
- `schema_version`

`source_status` records `ok`, `accepted`, `too_large`, `not_modified`,
`not_available`, or `error`. GitHub statistics endpoints can return delayed or
limited data; unsupported states are product signals, not just errors.

### `repo-contributor-activity-weekly.csv`

Row identity: `repo`, `author_id`, `week_start`.

Columns:

- `repo`
- `author_id`
- `author_login`
- `week_start`
- `commits`
- `additions`
- `deletions`
- `captured_at`
- `source_status`
- `schema_version`

### `collection-endpoints.csv`

Row identity: `repo`, `captured_at`, `endpoint_key`.

Columns:

- `repo`
- `captured_at`
- `endpoint_key`
- `credential_class`
- `status`
- `http_status`
- `rows_written`
- `cache_state`
- `rate_limit_remaining`
- `retry_after_seconds`
- `duration_ms`
- `error_type`
- `error_message`
- `schema_version`

This table lets the dashboard explain missing context: "commit statistics are
unavailable because GitHub does not provide this graph for repositories with
10,000 or more commits", or "release data was skipped by permissions."

## Collection Workflow

The new collection workflow should be endpoint-planned before execution. The
plan should produce both user-visible cost estimates and the actual sequence the
collector runs.

Per selected repository, the beta collection plan should include:

1. Existing traffic views, clones, referrers, and paths.
2. Existing repository detail and community profile.
3. Local default-branch git fetch/clone and git-log extraction.
4. Releases and release assets.
5. Languages.
6. Topics.
7. Open issue and pull request samples.
8. Code frequency and contributor activity statistics when GitHub supports them.
9. Endpoint telemetry for every endpoint family.
10. Event-index derivation during merge.

Collection cadence:

- traffic: daily;
- repository detail/community: daily at first, later conditional;
- local git log: daily for selected repositories, using incremental fetch;
- releases/assets: daily or conditional;
- languages/topics: daily at first, later conditional;
- issue/PR snapshots: daily;
- statistics endpoints: daily until stable behavior is understood, then less
  often if useful.

## Migration And Compatibility

Compatibility remains a design concern, but not the product governor for this
pre-beta shift.

Rules:

1. If a compatible additive migration is cheap and does not distort the model,
   do it.
2. If preserving an old packet shape would force misleading semantics or weak
   product design, prefer a deliberate compatibility reset.
3. Any reset must be recorded in `template-contract.yml`, release notes, and
   retained-data migration docs.
4. Migration should preserve row identity for any retained table that survives
   the reset.
5. New tables must have explicit row identities in lineage metadata from the
   first implementation.
6. New unavailable historical values should be blank or explicitly marked
   unavailable; do not synthesize fake history.

Because beta users do not yet exist, the first implementation may bump the
retained packet schema and require newly generated templates to use that schema.
However, old fixture migration should still be maintained when it costs little,
because the code already has a good migration path and fixtures catch accidental
packet loss.

## Implementation Milestones

### Milestone 1: Product Model Foundation

- Land this ADR.
- Add canonical CSV schemas for the new table families.
- Add lineage row identities and dedup functions.
- Add migration coverage proving old packets gain empty new tables.
- Update export and artifact docs to state that `storage.CSV_REGISTRY` is the
  canonical list, not a hand-maintained subset.

### Milestone 2: Local Commit History Collection

- Add a git-log extraction module that operates on a local clone/fetch of each
  selected repository's default branch.
- Populate `repo-commits.csv`.
- Add commit classification heuristics.
- Derive commit rows into `repo-event-index.csv`.
- Add essential unit tests around parsing, privacy fields, and row identity.

### Milestone 3: GitHub Context Endpoint Collection

- Add release/release-asset, language, topic, issue, PR, code-frequency, and
  contributor-stat endpoint modules.
- Record endpoint telemetry in `collection-endpoints.csv`.
- Treat optional endpoint failures as context gaps, not full run failures, unless
  the endpoint is required for the selected collection profile.

### Milestone 4: Event Spine And Insight Layer

- Materialize `repo-event-index.csv` in merge.
- Add time-window joins between metric anomalies and nearby events.
- Add structured insight candidates that cite event evidence.
- Keep generated prose conservative: correlation, not causation.

### Milestone 5: Dashboard Product Surface

- Add a "What changed nearby" panel for selected metric windows.
- Add repository timeline rows that combine traffic, releases, commits, and
  maintenance load.
- Add evidence links from insights to GitHub objects.
- Tune demo fixtures to show normal gradual growth plus contextual explanation,
  not only obvious spikes.

### Milestone 6: Collection Profile And Template Contract

- Revisit default repository count and configuration UX.
- Prefer curated 20-30 repo selection for beta.
- Decide whether the retained packet change is a compatibility reset.
- Record any reset in `template-contract.yml` and release docs.

## Essential Tests

The first pass should test model reliability, not every staging scenario:

- schema migration creates all new registered CSV files with canonical headers;
- lineage snapshot includes row identities for every new retained table;
- deduplication preserves the intended latest row for snapshot tables;
- commit parser hashes sensitive fields and extracts stable identities;
- event-index derivation produces stable `event_id` values from source rows;
- collection endpoint telemetry records optional endpoint failures without
  corrupting the retained packet.

Staging-only fixtures and brittle generated snapshots should not block this
direction. If they fail because they encode an obsolete product assumption, they
should be revised or explicitly bypassed with a documented `--no-verify` commit
rather than allowed to dictate the data model.

## Consequences

The dashboard becomes a contextual maintainer instrument rather than a traffic
counter. This increases collection and rendering complexity, but it gives
Reponomics the raw material needed for engaging beta feedback:

- richer repository timelines;
- maintainer-specific observations;
- code-grounded explanations;
- clearer advice about documentation, release cadence, issue load, and adoption;
- a better foundation for future AI-assisted narrative summaries.

The cost is that the retained packet is now a real product model. It must be
designed intentionally, versioned carefully, and reflected honestly in the
template contract.
