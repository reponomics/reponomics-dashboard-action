# ADR 0001: Demo Repository as User-Realistic Consumer

Date: 2026-05-21

## Status

Accepted

## Context

Reponomics needs a public demo repository that users can inspect to understand
what setup, collection, publication, encrypted dashboard access, and generated
outputs look like in practice. The demo repository is also expected to become a
core infrastructure repository, not a one-off fixture or renderer harness.

A demo that bypasses normal setup or rendering paths would be easier to build,
but it would be less useful as product documentation and less valuable in CI. It
could accidentally demonstrate a workflow that users cannot reproduce, or let the
demo drift away from the action's real setup contract.

The only behavior that should differ from a normal user repository is the
upstream GitHub API boundary. The demo must not make live traffic or repository
detail API calls during routine regeneration; those responses should be mocked
from deterministic fixtures.

## Decision

The public demo repository will be built exactly like a normal user-owned
Reponomics repository, except that collection uses mocked GitHub API responses.

This means the demo repository should use the same setup and publish lifecycle a
user would use:

- the same repository layout produced by setup;
- the same `config.yaml` shape;
- the same action inputs and workflow structure;
- the same artifact and data lifecycle;
- the same collection, merge, schema-prep, README rendering, and Pages dashboard
  rendering paths;
- the same encrypted dashboard path when demonstrating secure Pages mode.

Mocking belongs at the collect boundary only. Once mocked GitHub responses have
been returned, downstream processing should be real.

The demo should use a strong, intentionally public dashboard key for encrypted
mode demonstrations. The key should be documented in an obvious location, such
as `docs/SECURE_DASHBOARD_KEY.md`, and described as a public demo key that must
not be reused for real dashboards. The demo should not rely on weak keys merely
for convenience, because that would normalize unsafe setup and avoid exercising
the real entropy policy.

## Consequences

The demo repository becomes both a product surface and an integration test. This
raises the maintenance bar, but it keeps the public example honest.

CI for the demo repository should be able to regenerate the demo from clean
state, then fail if committed outputs are stale. A likely local and CI shape is:

```bash
make demo-setup
make demo-collect
make demo-publish
git diff --exit-code
```

Those commands may wrap workflow-equivalent commands or a reusable workflow, but
they should not introduce private shortcuts that users cannot map back to the
documented setup flow.

The action repository remains responsible for the runtime, renderer, validation,
mock fixture contract, and tests that prove mocked collection exercises normal
downstream behavior. The demo repository remains responsible for the public demo
configuration, generated sample data, README, Pages dashboard, public demo key,
and any screenshots or social-preview artifacts.

## Implementation Notes

The demo infrastructure should provide:

- deterministic mocked responses for GitHub traffic endpoints and repository
  detail endpoints;
- a way to run collect in mock mode through an explicit input or environment
  variable;
- schema-current generated CSV data for the public demo repository;
- separate migration fixtures for older schemas, kept in test fixtures rather
  than used as the public demo's source of truth;
- CI checks that validate workflow YAML, run the mocked setup/collect/publish
  lifecycle, validate vendored assets, and verify no generated output drift.

The demo workflow may use GitHub Actions directly, but CI should avoid awkwardly
dispatching one workflow from another unless the goal is specifically to test
GitHub workflow dispatch behavior. Prefer extracting shared workflow-equivalent
commands into Make targets or a reusable workflow, then have both local runs and
CI call the same entry points.

## Non-Goals

This ADR does not choose the final repository name, fixture file format, mock
server implementation, or exact CI workflow topology.

This ADR does not require the existing packaged demo data under sibling
repositories to become the long-term source of truth. Existing data can be used
for temporary visual smoke tests, but the planned demo repository should own its
own reproducible demo lifecycle.
