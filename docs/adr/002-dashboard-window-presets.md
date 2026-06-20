# ADR 002: Dashboard Window Presets

Date: 2026-05-21

## Status

Accepted

## Context

The dashboard currently exposes a binary window control: `Recent` and `All`. `Recent` is a fixed trailing window, while `All` means as far back as the retained dashboard data goes. That is useful but too coarse for normal day-to-day reading: a seven-day view answers a different question than a fourteen-day or thirty-day view.

An arbitrary numeric day input would add UI complexity and imply a degree of precision that is not especially useful for repository traffic. Users do not gain much from choosing 10 days instead of 7 days.

The long-window case also needs precise semantics. Ninety days is the default artifact retention period, but it is not necessarily the maximum retained range for every user. `All` should continue to mean all retained data present in the dashboard payload, not a fixed 90-day alias.

## Decision

Replace the binary `Recent` / `All` window control with fixed presets:

- `7d`
- `14d`
- `30d`
- `90d`
- `All`

The fixed presets are trailing collected-day windows. `All` means all retained data available in the payload.

The default window remains `14d`.

The dashboard URL state should use a `window` parameter:

- `window=7`
- `window=14`
- `window=30`
- `window=90`
- `window=all`

Existing links that use `range=recent` or `range=all` should remain supported. `range=recent` maps to `window=14`; `range=all` maps to `window=all`.

## Consequences

The dashboard gains more useful analytical modes without adding arbitrary input state. The UI also avoids calling a 90-day view `All`, which would be misleading for users who retain more than 90 days of data.

Fixed windows should be applied consistently to the client-rendered dashboard: stat cards, charts, repository visibility, and per-repository rows should all use the selected window. When growth metrics are shown for the selected window, they must be computed from data that follows the same selected-window semantics.

If older dashboard payloads lack newer metric time series, the dashboard should fall back gracefully to the existing growth summary rather than failing to render.

## Non-Goals

This ADR does not change artifact retention settings.

This ADR does not introduce arbitrary user-entered day counts.

This ADR does not require a separate backend render for each preset; the dashboard can compute preset windows client-side from the retained payload.
