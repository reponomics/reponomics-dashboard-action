# Naming Cutover Map

Status: maintainer reference for the pre-release hard cut from traffic-specific contract names to collection and dashboard data names.

This document records the intended before/after mapping for the naming cutover. Old names should not remain in product code, generated workflows, user-facing setup instructions, or action inputs except when they appear here to explain the migration.

## Credential And Secret Names

| Before | After | Notes |
| --- | --- | --- |
| `TRAFFIC_TOKEN` | `COLLECTION_TOKEN` | Repository secret used by generated workflows for GitHub API data collection. |
| `traffic-token` | `collection-token` | Composite action input for the collection credential. |
| `REPONOMICS_TRAFFIC_TOKEN` | `REPONOMICS_COLLECTION_TOKEN` | Internal action environment variable passed from `action.yml` into runtime code. |
| `traffic_token` | `collection_token` | Python/runtime variable and configuration field names. |
| `TRAFFIC_DASHBOARD_SECRET` | `DASHBOARD_SECRET_DO_NOT_REPLACE` | Repository secret containing the current dashboard encryption key. The blunt name is intentional because replacing it directly can make retained encrypted history unrecoverable. |
| `TRAFFIC_DASHBOARD_NEXT_SECRET` | `DASHBOARD_NEXT_SECRET` | Repository secret containing the next dashboard encryption key during rotation. |
| `dashboard-secret` | `dashboard-secret` | Action input remains generic; callers pass `${{ secrets.DASHBOARD_SECRET_DO_NOT_REPLACE }}`. |
| `dashboard-next-secret` | `dashboard-next-secret` | Action input remains generic; callers pass `${{ secrets.DASHBOARD_NEXT_SECRET }}`. |

## Artifact And Data Names

| Before | After | Notes |
| --- | --- | --- |
| `traffic-data` | `dashboard-data` | Canonical retained Actions artifact for all dashboard data families, not only traffic metrics. |
| `traffic-data.enc` | `dashboard-data.enc` | Encrypted retained dashboard data payload. |
| `.traffic-artifact` | `.dashboard-data-artifact` | Local restore/upload staging directory. |
| `traffic-dashboard-plain` | `html-dashboard-plaintext` | Plain-mode HTML dashboard artifact. |
| `traffic artifact` | `dashboard data artifact` | Prose name for the retained Actions artifact. |
| `traffic data artifact` | `dashboard data artifact` | Prose name for the retained Actions artifact. |
| `traffic dashboard plane` | `HTML dashboard plane` | Prose name for the hosted or artifact-delivered HTML dashboard surface. |

## Workflow, Bot, And Brand Names

| Before | After | Notes |
| --- | --- | --- |
| `Collect Reponomics traffic` | `Collect Reponomics Data` | Generated collection workflow name. |
| `Collect GitHub Traffic` | `Collect Reponomics Data` | Older generated/demo workflow name. |
| `github-traffic-release` | `reponomics-release` | Bot identity used by generated template publishing. |
| `GitHub Traffic Report` | `Reponomics Dashboard` | Product-facing name. |
| `github-traffic-report` | `reponomics-dashboard` | Slug-style product name where a repository or package slug is needed. |

## Terms To Keep

Do not mechanically replace every use of `traffic`. Keep traffic-specific names when they refer to GitHub traffic metrics, GitHub traffic API concepts, or CSV files that contain traffic data.

Examples that should remain traffic-specific:

- `traffic-log.csv`
- `traffic-daily.csv`
- `traffic-snapshots.csv`
- `traffic-referrers.csv`
- `traffic-paths.csv`
- `traffic_days`
- `zero_traffic_repos`
- GitHub traffic API endpoint names and descriptions
- prose such as `GitHub traffic data` when the sentence is specifically about views, clones, referrers, or paths

Use `dashboard data` for the retained artifact and broad data store. Use `collection` for the credential and process that gathers data from GitHub APIs.

CSV family boundary: `traffic-*` CSV files are reserved for GitHub traffic metrics. Stars, subscribers/watchers, forks, repository metadata, and community health fields belong in `repo-metrics.csv`; collection diagnostics belong in `collection-status.csv`.
