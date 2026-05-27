# ADR 009: Community Health Profile Metrics

Date: 2026-05-27

## Status

Proposed

## Context

`repo-metrics.csv` currently captures repository growth and profile counters (stars, subscribers, forks, issue count, size, visibility, etc.) but does not capture repository community-health posture. That leaves the dashboard without a structured way to answer questions such as:

- Which repos have weak community setup relative to peers?
- Is a repo missing contribution guidance while attention rises?
- How does health posture trend across the tracked set?

GitHub provides per-repo community profile metrics via:

- `GET /repos/{owner}/{repo}/community/profile`

The endpoint returns health percentage and file-presence signals (README, contributing guide, issue template, pull request template, license, code of conduct), plus related metadata.

## Decision

Add community profile metrics to the existing per-repo snapshot collection flow and store them as flattened columns in `repo-metrics.csv`, then surface them in the dashboard’s Repositories table.

### Data schema additions (`repo-metrics.csv`)

New columns:

- `community_health_percentage`
- `community_documentation`
- `community_updated_at`
- `community_content_reports_enabled`
- `community_has_code_of_conduct`
- `community_has_contributing`
- `community_has_issue_template`
- `community_has_pull_request_template`
- `community_has_readme`
- `community_has_license`

These fields are appended additively to the canonical `REPO_METRIC_FIELDS` list and migrate through existing header migration behavior (`storage.migrate_schema`).

### Collection behavior

Per tracked repo, collection performs an additional call to `community/profile` and maps response fields into the snapshot row.

Failure policy:

- Community-profile fetch failure is **non-fatal** for the run.
- Collector records a warning and writes repo metrics with community fields blank for that snapshot.
- Traffic collection and other metric families continue.

This preserves run continuity while exposing missing community data as an observable gap.

### UI placement

Community metrics are exposed in the dashboard Repositories table as a new **Community** column:

- Primary value: community health percentage.
- Secondary value: file-signal coverage + docs-link presence.
- Sort support: sortable by community health.

This keeps the signal per-repo (where it belongs) without crowding top-level traffic/growth summary cards.

## Consequences

- **Pros**: richer repo-level context, actionable maintenance signal, aligns growth with contribution readiness.
- **Tradeoff**: one additional API request per repo per collect run.
- **Compatibility**: additive schema migration; existing artifacts remain readable and are upgraded in place.

## Alternatives considered

1. Separate `repo-community.csv` family:
   - Pros: isolated schema, smaller `repo-metrics.csv` rows.
   - Cons: extra merge/load complexity and cross-file join logic for UI.
2. UI-only live fetch during render:
   - Pros: no retained schema growth.
   - Cons: violates retained-artifact model and breaks offline/privacy guarantees.

Chosen approach keeps all analytics in the retained canonical artifact path and follows existing repo-metric snapshot patterns.
