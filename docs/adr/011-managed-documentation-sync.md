# ADR 011: Managed Documentation Sync

Date: 2026-05-29

## Status

Proposed

## Context

When users accept a new Reponomics action version, they may also need updated local documentation: new configuration options, privacy-mode guidance, artifact access instructions, upgrade notes, or feature-specific migration steps. A release-status link can point upstream, but it does not make a generated dashboard repository self-contained.

The project should not treat the most sensitive user as the default product model. Many users will expect useful managed updates when they opt into a new action version. At the same time, repository writes need a strict boundary so users can understand what Reponomics owns and how to opt out.

## Decision

Support managed documentation sync into a single Reponomics-owned namespace in the generated dashboard repository, such as `docs/reponomics/` or `docs/reponomics-dashboard/`.

Managed docs sync should be enabled by default in the template workflow. Users may disable it with an explicit config setting if they want to use a new action version without accepting local documentation updates.

The default delivery mode is a direct write using the consuming workflow's `GITHUB_TOKEN`, when the workflow grants the required permission. PR-based docs updates are a valid future option, but they are not the baseline because they add review-state and branch-management complexity and are easy for normal users to ignore.

## Boundaries

The action may write only inside the managed docs namespace. It must not scatter files through user documentation, mutate `config.yaml`, or write retained dashboard data, tokens, secrets, or local machine paths.

The managed namespace should include a manifest, for example `docs/reponomics/.manifest.json`, recording the docs bundle version, action version, managed file list, and generated content hashes.

Sync behavior:

- Write missing managed files.
- Replace existing managed files only when they match the previous generated hash.
- Leave user-modified managed files untouched and report that manual review is needed.
- If managed files exist but the manifest is missing or inconsistent, fail closed or skip rather than guessing ownership.
- If workflow permissions are insufficient, skip docs sync with a clear message rather than failing dashboard publication by default.

Workflow permissions should remain minimal at the top level. Any required `contents: write` permission should be declared only at the job level that performs docs sync or publish.

## Bundle Source

The docs bundle should ship with the action release. A runtime workflow should not fetch mutable docs from an external service just to update a user repository. If the user chooses a new action ref, the matching documentation payload should come from that action revision.

The initial bundle should be the local user-facing subset: upgrade notes, configuration reference, privacy-mode guidance, dashboard/artifact access instructions, and links to upstream release notes for longer history.

## Floating Ref Receipt

Users on floating refs such as `@v1` may receive a new action version without editing their workflow. For those users, docs sync is also the best available local receipt that a new version has actually run in their repository.

The risk is not mainly that users will be surprised or upset by the update. The larger product risk is that users will not notice newly available opt-in features, configuration choices, or workflow improvements. When the running action version differs from the version recorded in the managed docs manifest, docs sync should attempt to update the local docs and manifest on the next publish run. If it writes a commit, the commit message should include the action version and docs bundle version. If it cannot write because docs sync is disabled, permissions are missing, or user edits block the update, the workflow summary and generated dashboard/version-status surface should report that local documentation is not current.

This is not a perfect discovery mechanism: a user may ignore a dashboard indicator or workflow summary. PR mode would provide a stronger review signal for users who want it. Active upstream channels such as an RSS feed or release-announcement feed could also serve users who want to follow the product more closely. The first implementation should still use direct managed sync as the default, because it gives normal floating-ref users a concrete local update rather than only an upstream notice.

## Adoption Visibility

Managed docs sync should not be treated as product telemetry. Its purpose is to update the user's local documentation and improve feature discovery.

The project still needs adoption signals, but GitHub does not appear to expose a complete first-party count of repositories generated from a template or actively using a generated dashboard repository. Public code search for workflow references, dependency-graph/dependents signals for public action usage, upstream repository traffic, stars, issues, discussions, and release/feed subscribers can all provide partial evidence. None of those signals should be treated as a reliable count of active installations.

An RSS or release-announcement feed is still useful because it gives engaged users an active update channel. If the feed is hosted somewhere Reponomics controls, aggregate request logs may provide weak adoption evidence. The project should be careful not to overstate RSS subscriber counts, because many feed readers proxy, cache, prefetch, or hide individual subscribers.

Do not add silent telemetry to generated repositories as part of this feature. Any future adoption reporting from user repositories should be explicit, opt-in, documented, and separate from managed docs sync.

## Implementation Scope

The first implementation should be small enough to delegate:

1. Add a versioned docs bundle to the action package.
2. Add a sync helper that writes the bundle into one managed namespace.
3. Add manifest/hash ownership checks.
4. Add an opt-out config flag.
5. Add tests for first write, clean update, user-modified conflict, opt-out, insufficient permission behavior, and no writes outside the namespace.
6. Add tests for floating-ref receipt behavior when the running action version differs from the manifest version.
7. Link generated README/HTML surfaces to local managed docs only when the local docs exist; otherwise fall back to upstream docs or release notes.

Do not implement PR mode in the first pass unless direct writes reveal a blocking limitation.

## Consequences

Generated dashboard repositories become more self-contained after action upgrades, and users who want managed updates get them by default.

The action takes on a new responsibility to preserve a strict managed-file boundary. Manifest-based ownership checks are therefore part of the feature, not a later hardening task.

Users who disable docs sync or remove write permission can still use the dashboard, but they must read upstream documentation manually.

## Open Questions

- What final path should the template use for the managed docs namespace?
- Should docs sync run during every `publish`, only when the action version changes, or through a dedicated workflow mode?
- What exact config key should disable docs sync?
- What dashboard/README indicator is visible enough when floating-ref users cannot or do not accept a docs sync update?
- Should Reponomics publish an RSS or release-announcement feed for users who want an active update channel?
- What public and opt-in signals should the project use to estimate adoption without implying a precise install count?
- When, if ever, should optional PR mode be added?

---

## Appendix A: Proposed Emendments (2026-05-29)

This appendix records implementation-level clarifications without changing the
main ADR text above.

### A1. Comparator Source Of Truth

Use a machine marker in the managed docs namespace manifest as the comparator
source of truth. Do not use README/dashboard version badges as the control
marker for sync decisions.

Required manifest fields:

- `schema_version`
- `managed_namespace`
- `action_repository`
- `action_version`
- `docs_bundle_version`
- `files` (map of relative path -> sha256)

The manifest should be deterministic. Avoid volatile fields that change on every
run (for example, `generated_at` timestamps) unless they are excluded from diff
and ownership checks.

### A2. Default Execution Model

Default template wiring should run docs sync in a dedicated job before
collection/publish jobs. The job should compare:

- currently running action version and docs bundle version
- manifest `action_version` and `docs_bundle_version`
- current managed-file bytes against manifest hashes

Recommended state outcomes:

- `up_to_date` (no write needed)
- `updated` (managed docs written and manifest advanced)
- `disabled` (opt-out config)
- `permission_missing` (insufficient write permission)
- `user_modified_conflict` (managed file diverged from prior generated hash)
- `manifest_inconsistent` (ownership cannot be proven)
- `push_race` (write intent valid, but commit/push could not be completed)

If state is not `updated` or `up_to_date`, write a clear step summary and expose
the state as a machine-readable output for downstream surfacing.

### A3. Write Boundary And Commit Rules

Managed docs sync may stage and commit only files inside the managed namespace.
No writes are allowed outside that namespace as part of this feature.

Commit rules:

- use the consuming repository `GITHUB_TOKEN` by default
- commit only when staged bytes differ
- include action version and docs bundle version in the commit message
- include `[skip ci]` in the commit message for direct-write mode
- if push fails due to non-fast-forward, retry with a bounded reconciliation
  strategy; on failure, emit `push_race`

### A4. Concurrency And Permissions

Serialize docs-sync writes per branch/ref with workflow/job concurrency so only
one docs-sync writer can push at a time for a given ref.

Keep top-level workflow permissions minimal/read-only. Grant `contents: write`
only at the docs-sync job level when direct-write mode is enabled.

### A5. Failure Policy

Docs sync is advisory to dashboard publication and collection continuity:

- `permission_missing`, `disabled`, `user_modified_conflict`,
  `manifest_inconsistent`, and `push_race` should not fail collection/publish by
  default
- these states must still be surfaced in workflow summary and status outputs

### A6. Surface Contract

Expose docs-sync status through explicit outputs so template workflows and UI
surfaces can consume stable semantics:

- `docs-sync-state`
- `docs-sync-reason`
- `docs-bundle-version`
- `docs-manifest-action-version`

README/dashboard/version-status surfaces should display a local-docs freshness
indicator based on these outputs when available.

### A7. Opt-Out Contract

Define one canonical opt-out key and precedence to avoid drift across template,
action runtime, and docs:

- canonical key: `managed_docs_sync`
- default: `true`
- accepted locations in first pass:
  - workflow/action input
  - `config.yaml` key
- precedence: explicit workflow/action input overrides `config.yaml`; otherwise
  `config.yaml`; otherwise default `true`

### A8. Ownership Recovery Path

When state is `manifest_inconsistent`, the sync helper must not guess ownership
or overwrite files. Recovery should be explicit and auditable.

Required behavior:

- fail closed for write operations in that run
- emit remediation instructions in workflow summary
- require explicit operator intent for recovery (for example, an adopt/reset
  flag or a documented manual reset procedure)
- on successful recovery, emit `updated` with a fresh manifest that rebinds
  ownership to the managed namespace

### A9. Open-Question Dispositions

This section captures what is now considered resolved by this appendix and what
remains intentionally deferred.

Resolved now:

- managed docs namespace path: use `docs/reponomics/`
- execution model: run docs sync as a dedicated pre-collect/pre-publish job
- opt-out key: `managed_docs_sync` with precedence rules in A7
- freshness indicator contract: expose `docs-sync-*` outputs and render a
  local-docs freshness indicator in README/dashboard/version-status surfaces

Deferred (not blocked by first implementation):

- whether to publish an RSS or release-announcement feed
- which external/public/opt-in adoption signals to treat as advisory inputs
  (without claiming precise install counts)
- when optional PR mode should be added; default remains direct-write unless
  direct-write proves operationally insufficient
