# ADR 005: Incident Reset Rekey And History Purge

Date: 2026-05-25

## Status

Accepted

## Context

For encrypted privacy modes, retained history is stored in `dashboard-data` artifacts encrypted with `DASHBOARD_SECRET_DO_NOT_REPLACE`. If that secret is exposed, prior encrypted artifacts can be downloaded and attacked offline indefinitely. A normal `rotate-key` run only moves forward and does not remove older workflow runs or artifacts that remain decryptable with the compromised key.

The product needs an emergency mode that preserves continuity while removing old decryptable history from GitHub Actions surfaces as far as repository-scoped API permissions allow.

## Decision

Add a dedicated runtime mode: `incident-reset`.

`incident-reset` is designed for emergency recovery after suspected secret exposure and does all of the following in one run:

1. Restores the current retained artifact.
2. Decrypts retained state with `DASHBOARD_SECRET_DO_NOT_REPLACE`.
3. Re-encrypts retained state with `DASHBOARD_NEXT_SECRET`.
4. Uploads the new encrypted retained artifact.
5. Finds prior `dashboard-data` artifacts, excluding the artifact uploaded by the current reset run.
6. Deletes workflow runs associated with those prior artifacts. GitHub deletes a run's artifacts when the run is deleted.
7. Deletes only old `dashboard-data` artifacts that GitHub reports without an associated workflow run id.

The mode is intentionally destructive and requires explicit triple confirmation inputs:

- `incident-confirm-mode=INCIDENT_RESET_CONFIRMED`
- `incident-confirm-purge=PURGE_OLD_HISTORY_CONFIRMED`
- `incident-confirm-irreversible=IRREVERSIBLE_ACTION_CONFIRMED`

`incident-reset` also requires:

- encrypted privacy mode (`strong` or `casual`)
- `dashboard-secret`
- `dashboard-next-secret`
- `github-token` with `actions: write`
- GitHub Actions runtime context with `GITHUB_REPOSITORY` and `GITHUB_RUN_ID`

The recommended operational response is to make the dashboard repository private
and disable any published Pages dashboard before running `incident-reset`.

## Scope Clarification

`incident-reset` is not a general outage-preservation tool and it does not render Pages or README outputs. It is an emergency rekey-and-purge operation.

Deletion scope is intentionally bounded:

- Workflow runs: runs associated with prior `dashboard-data` artifacts, excluding the currently running incident-reset run.
- Artifacts: only prior `dashboard-data` artifacts that GitHub reports without an associated workflow run id.

This mode does not claim global repository cleanup outside those scopes.

## Rationale

Bundling re-encryption and history purge in one mode reduces operator error during incident response. If users only rekey without cleanup, old ciphertext remains available under the compromised key. If users only purge without successful rekey, they can destroy recoverable history without establishing a new valid retained state.

A single mode with mandatory explicit confirmations provides a safer operator path under stress.

## Retry And Failure Semantics

Delete operations are executed through GitHub REST APIs with retry behavior aligned to existing runtime throttling policy:

- retry on transient network failures
- honor secondary rate-limit windows
- retry on retryable throttle/server failures
- treat `204` and `404` delete responses as non-fatal completion for that resource
- delete sequentially, never concurrently
- execute deletion sequentially so GitHub API throttling remains observable and retryable

If required repository/run context is missing or malformed, the mode fails fast with a user-facing action error.

## Consequences

- Users can recover to a new encryption boundary while aggressively reducing old decryptable history in repository Actions surfaces.
- Incident recovery requires stronger workflow permissions (`actions: write`) than normal collection-only paths.
- The mode is irreversible for deleted runs/artifacts and must be used intentionally.
- Purge coverage is limited to deletable workflow/artifact surfaces exposed by repository-scoped APIs and token permissions.

## Alternatives Considered

### 1) Keep only rotate-key

Pros:
- simpler runtime surface

Cons:
- leaves old decryptable artifacts/runs intact after secret exposure

### 2) Add purge-only mode without re-encryption

Pros:
- narrow feature scope

Cons:
- easier to destroy history without establishing new encrypted continuity
- increases operator sequencing mistakes during incidents

### 3) Require manual API cleanup outside the action

Pros:
- no destructive mode in product surface

Cons:
- high operator burden and inconsistent execution during emergencies
- weak reproducibility and auditability

## Non-Goals

This ADR does not define:

- credential exfiltration prevention for users with repository write/admin control
- deletion of every possible historical surface on GitHub beyond run/artifact APIs used here
- automatic token repair or permissions remediation during outages

## Implementation Status, 2026-05-25

Implemented in `dashboard_action/run.py`, exposed in `action.yml`, documented in `README.md`, and covered by runtime tests in `tests/test_run_unit.py` and `tests/runner/`.

## Implementation Update, 2026-06-05

The composite action now separates reset preparation from purge execution.
`run_incident_reset` restores, decrypts, re-encrypts, and stages the new
encrypted retained artifact. The composite action uploads that new
`dashboard-data` artifact before invoking the post-upload purge step. This
preserves a recovery checkpoint before destructive cleanup begins.

The purge step is now artifact-driven rather than workflow-id-driven. It finds
old `dashboard-data` artifacts repository-wide, deletes their associated
workflow runs, and relies on GitHub's run deletion behavior to delete run-owned
artifacts. Direct artifact deletion remains only a fallback for old artifacts
that do not report an associated workflow run id.
