# ADR 006: Private Plain Dashboard Artifact Delivery

Date: 2026-05-25

## Status

Accepted

## Amends

- [ADR 003](003-encrypted-retained-storage-and-explicit-csv-export.md)

## Context

ADR 003 intentionally disabled GitHub Pages publication for `privacy-mode: plain` to prevent accidental public disclosure of plaintext metrics. That policy is correct, but it leaves private-repository users in plain mode without a rendered dashboard surface unless they inspect CSV artifacts directly.

Private plain users already accept plaintext retained artifacts inside repository workflow artifacts. A plain dashboard download artifact does not expand disclosure beyond that repository trust boundary, but it materially improves usability.

## Decision

For private repositories using `privacy-mode: plain`, `publish` will render a plain dashboard and upload it as a regular workflow artifact named `traffic-dashboard-plain`.

Guardrails:

- No GitHub Pages publication in plain mode.
- No new action input, flag, or mode is added.
- Behavior is automatic default for private plain `publish` runs.
- Existing encrypted behavior for `strong` and `casual` remains unchanged.

## Implementation Notes

- Runtime: when `publish-pages` is false because `privacy-mode` is plain, `publish` now renders the dashboard via the standard renderer (public access mode) instead of the pages-disabled placeholder.
- Composite action: plain private `publish` runs upload `${{ steps.runtime.outputs.pages-path }}` as `traffic-dashboard-plain` using `actions/upload-artifact`.
- Pages configure/upload/deploy steps remain gated to `publish-pages: true` and therefore do not run for plain mode.

## Consequences

- Private plain users get a ready-to-open dashboard HTML artifact by default.
- The no-plaintext-pages policy remains intact.
- No extra configuration burden or decision surface is introduced.
- Artifact retention for plain dashboards follows `retention-days`, matching other workflow artifacts.

## Alternatives Considered

### 1) Keep placeholder-only behavior in plain mode

Pros:
- smallest implementation surface.

Cons:
- poor UX for private plain users.
- forces manual CSV analysis for basic dashboard review.

### 2) Add a new input to opt into plain dashboard artifacts

Pros:
- explicit opt-in control.

Cons:
- increases user decision complexity for behavior that should be default within private plain mode.
- conflicts with the product goal of minimizing privacy-surface misconfiguration.

### 3) Re-enable plaintext Pages publication for plain mode

Pros:
- direct hosted viewing.

Cons:
- violates established policy to avoid accidental public plaintext disclosure.

## Non-Goals

This ADR does not change:

- public-repository eligibility for plain mode
- encrypted dashboard export/delivery model
- incident-reset or sentinel behaviors
