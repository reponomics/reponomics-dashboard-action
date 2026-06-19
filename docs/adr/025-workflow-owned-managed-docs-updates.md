# ADR 025: Workflow-Owned Managed Docs Updates

Date: 2026-06-19

## Status

Accepted

## Context

ADR 011 introduced managed documentation sync for generated dashboard
repositories. The first implementation exposed `allow_docs_sync` as a runtime
configuration choice and allowed the action to commit managed documentation
directly when the calling workflow granted `contents: write`.

That split puts an authority decision in the wrong layer. Users who accept the
compatible Reponomics action line should normally receive the matching local
documentation for that action version. Letting a repository run a newer action
while silently retaining older Reponomics docs creates avoidable confusion and
can hide updated security, privacy, recovery, and permissions guidance.

The repository owner still needs a clear opt-out path and a strict write
boundary. GitHub workflow files are the better place for that boundary because
they are owned by the consuming repository and declare the permissions granted
to each job.

## Decision

Replace user-facing `docs-sync` configuration with a dedicated generated
`update-docs` workflow.

Generated repositories should not expose `allow_docs_sync` as a config option.
If a repository owner does not want automatic managed documentation updates,
they can disable or delete the generated `update-docs` workflow.

The `update-docs` workflow should use the same generated local Reponomics action
wrapper as the other generated workflows. Updating the local wrapper's nested
Reponomics action ref therefore accepts both the new runtime behavior and the
matching managed documentation payload shipped with that action version.

## Trust Boundary

The action may prepare a documentation update payload, but repository writes
belong to the user-owned workflow.

Use separate jobs:

1. A prepare job with `contents: read` runs the Reponomics action and produces a
   proposed managed-docs payload.
2. An apply job with `contents: write` downloads that payload, applies it only
   under `docs/reponomics/`, verifies the resulting git diff, and commits only
   if every changed path is inside `docs/reponomics/`.

The workflow path guard is the enforcement mechanism. `docs/reponomics/.manifest.json`
remains useful for provenance and freshness checks.

README updates remain separate from managed docs updates. `README.md` is outside
the Reponomics-managed docs namespace and should keep its own explicit consent
model.

## Trigger

The generated `update-docs` workflow should run after the generated
collect-and-publish workflow completes successfully:

```yaml
on:
  workflow_run:
    workflows: ["Collect and publish Reponomics dashboard"]
    types: [completed]
    branches: [main]
  workflow_dispatch:
```

The update job should gate normal chained runs on:

```yaml
if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success' }}
```

This makes documentation updates part of the dashboard cadence without granting
the collect-and-publish workflow any additional repository-write authority for
managed docs.

## Secrets And Artifacts

The `update-docs` workflow must not receive or reference collection or dashboard
secrets such as `COLLECTION_TOKEN`, `DASHBOARD_SECRET`, or
`DASHBOARD_NEXT_SECRET`.

It should not download artifacts from the triggering collect-and-publish run.
The prepare job should generate managed docs from the action bundle and ordinary
repository files only. The downstream workflow receives its own `GITHUB_TOKEN`
with permissions declared by its own jobs.

## Implementation Notes

- Rename the user-facing workflow and documentation language from `docs-sync` to
  `update-docs`.
- Keep top-level workflow permissions minimal; grant `contents: write` only to
  the apply job.
- Fail before commit if `git diff --name-only` contains any path outside
  `docs/reponomics/`.
- Preserve non-destructive managed-doc behavior: deprecated or legacy managed
  documentation should be marked as such rather than silently deleted by default.
- Continue to record managed-docs provenance in `docs/reponomics/.manifest.json`.

## Consequences

The generated repository has a clearer authority model: the action proposes
managed documentation updates, while the workflow grants and enforces the write
permission.

Normal users receive documentation updates that match the action version they
are already running. Users who do not want that behavior still have a direct
repository-level opt-out by disabling or deleting the generated workflow.

The runtime no longer needs a user-facing `allow_docs_sync` mode switch, reducing
configuration surface and avoiding stale-docs states for users on the compatible
action line.
