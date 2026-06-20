# ADR 007: Collection Quality Visibility for Dashboard Consumers

## Status

Accepted

## Context

The dashboard currently treats retained CSV history as the source of truth for metrics, but users can misread missing collection data as genuine zero traffic when one or more repositories were skipped or failed during a run. This creates an interpretation risk: "no activity" and "no successful collection" are operationally different states, but the UI did not consistently expose that distinction at the point where users consume growth and traffic signals.

## Decision

We will persist per-repository collection outcomes as retained artifact data and surface a quality signal in dashboard payloads and UI. Collection writes a `collection-status.csv` row for each repo in each run with normalized outcomes (`ok_with_data`, `ok_zero_data`, `skipped_unavailable`, `error`, `error_secondary_rate_limit`) and lightweight diagnostics. The shared loader computes a `data_quality` summary from the latest captured run, and the dashboard runtime displays a visible warning when collection gaps are detected, or a neutral informational banner when all tracked repos collected successfully but returned zero traffic.

## Consequences

- Users can distinguish collection gaps from true low/zero traffic without reading workflow logs.
- The quality signal is durable because it lives inside the retained artifact lifecycle and is available at publish time.
- Existing growth and traffic formulas remain unchanged; this ADR adds observability first, not statistical imputation.
- The artifact schema expands with one additional CSV file that follows existing migration, retention, and deduplication behavior.

## Follow-up

Potential next steps include exposing per-repo confidence badges in repository tables, adding README-level quality notes, and introducing optional confidence weighting in anomaly ranking.
