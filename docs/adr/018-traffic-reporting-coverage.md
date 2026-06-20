# ADR 018: Traffic Reporting Coverage

## Status

Accepted

## Context

GitHub repository traffic is exposed through a rolling API and UI window. The traffic data can lag behind the current day across repositories and organizations, while still being recoverable later if GitHub backfills the missing days within the rolling window.

Reponomics previously used traffic count rows as the only date domain for traffic charts. When a collection ran on a newer date than GitHub's latest reported traffic day, charts silently ended at the older traffic date while the collection calendar showed the current run. Padding the traffic CSV with zeroes would be misleading because an unreported day is not confirmed zero traffic.

## Decision

Introduce two additive reporting ledgers:

- `collection-days.csv` records daily collection cadence. It includes successful runs, collection gaps, all-zero runs, and explicit `no_run` days between retained collection dates.
- `traffic-coverage.csv` records per-repository, per-date traffic reporting coverage. Count rows remain in `traffic-log.csv` and `traffic-daily.csv`.

Traffic coverage states are:

- `reported`: a traffic count row exists for the repo/date.
- `not_reported_by_api`: collection succeeded for the repo, but GitHub did not report trailing traffic days through the collection date.
- `collection_failed`: collection failed for the repo/date and no traffic row exists.
- `repo_skipped`: the repo was skipped or unavailable and no traffic row exists.

Dashboard and README renderers use the coverage summary to disclose upstream traffic lag. Interactive charts extend to the latest collection date with unreported trailing points represented as missing values, not zero.

## Consequences

- Existing traffic CSVs remain factual count observations and are still safe for long-term aggregation.
- The dashboard can distinguish `no_run`, collection failures, skipped repos, upstream non-reporting, and reported traffic.
- Later backfill replaces an earlier `not_reported_by_api` coverage state with `reported` because the count row now exists.
- The artifact schema grows additively and is migrated by the existing CSV registry machinery.
