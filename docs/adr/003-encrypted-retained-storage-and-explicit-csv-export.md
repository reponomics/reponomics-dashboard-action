# ADR 003: Two-Track Privacy Model And Explicit CSV Export

Date: 2026-05-21

## Status

Accepted

## Context

Reponomics currently supports multiple retained artifact storage modes:

- `encrypted`
- `plain`
- `auto`

That flexibility makes the runtime and setup contract harder to explain when it
is presented as a matrix of independent controls. Users must distinguish
repository visibility, retained artifact visibility, GitHub Pages visibility,
dashboard payload encryption, and README disclosure. The `auto` mode is
especially unclear because it asks users to trust conditional runtime behavior
rather than make an explicit privacy decision.

Reponomics has two legitimate audiences:

- public/free-tier users and other maintainers who want private collected data
  while hosting a useful dashboard from ordinary GitHub workflows;
- private-repository users who mainly want turnkey CSV collection and do not
  need encryption inside a repository they already treat as private.

The product surface should serve both audiences without presenting every
internal combination as a first-class setup choice.

Portability remains important. The product pitch includes the idea that the
retained history is still ordinary CSV data that users can move elsewhere. When
retained storage is encrypted, portability must be a first-class workflow rather
than a manual decryption recipe.

## Proposed Decision

Replace the flexible `encrypted`/`plain`/`auto` mode surface with two explicit
tracks.

The primary track is the encrypted privacy model:

- retained collection data is stored in encrypted artifacts;
- GitHub Pages publication, when enabled, publishes an encrypted dashboard;
- the user decides whether to publish plaintext README dashboard summaries;
- plaintext CSV portability is provided through explicit export and cleanup
  workflows.

The secondary track is the plaintext private-repository model:

- retained collection data is stored as plaintext CSV artifacts;
- README dashboard summaries are allowed because the repository is already
  treated as private;
- the user may optionally publish a plaintext GitHub Pages dashboard;
- no dashboard secret is required.

Remove `auto`. The setup flow should ask users to choose between the encrypted
privacy track and the plaintext private-repository track. It should not expose a
general-purpose matrix of storage and publication modes.

Add explicit export and cleanup workflows for plaintext CSV portability:

- `export` restores and decrypts the retained `traffic-data` artifact, packages
  the canonical CSV files, and uploads a separate plaintext export artifact.
- `destroy-exports` deletes plaintext export artifacts created by `export`.

Plaintext export artifacts should use a distinct name or prefix, for example:

```text
reponomics-csv-export-<run-id>
```

The generated template should provide manual workflows for the encrypted track
such as:

- **Export Reponomics CSV**
- **Destroy Reponomics CSV exports**

The export artifact should have short retention by default, initially one day.
Users who need a weekly export for investors, backups, or downstream analysis
can schedule export runs deliberately, then either download the artifact and run
cleanup or let artifact retention expire.

## Consequences

The product becomes simpler without pretending every user has the same privacy
requirements. The encrypted track gives public/free-tier users a coherent
default: retained artifacts are encrypted, hosted dashboards are encrypted, and
the only deliberate plaintext surface is the optional README summary. The
plaintext track gives private-repository users a low-friction CSV collection
path without fake secrets or weak keys.

This removes the least explainable state: `auto`. It also avoids mixed-mode
configuration as a primary user experience. Plaintext storage remains supported,
but only as part of an explicit private-repository track.

The encrypted track makes key loss serious. If the dashboard key is lost,
retained history cannot be recovered from encrypted artifacts. Documentation and
setup summaries must say this plainly.

Portability remains part of the encrypted track, but it moves to an explicit
workflow: users export plaintext CSV artifacts when they want to move data
elsewhere. Those artifacts are temporary disclosure events, not durable storage.
This is acceptable for public/free-tier users only if the export workflow is
manual, clearly labeled, short-lived by default, and paired with a cleanup
workflow.

## Credential Boundary

This decision preserves the core credential story. The encrypted track should
require one collection token plus one dashboard secret. The plaintext track
should require one collection token and no dashboard secret.

The product still has two separate API permission boundaries:

- collection access to the repositories whose traffic data is being read;
- dashboard-repository access for setup, workflow management, Pages deployment,
  export artifact cleanup, and any committed README output.

Those boundaries should not be conflated in documentation. A collection token
may need read access across source repositories. Dashboard-repository operations
should use the default `GITHUB_TOKEN` whenever possible.

The credential model is:

- `TRAFFIC_TOKEN`: reads GitHub traffic and repository metadata for tracked
  repositories; used by `collect`.
- `GITHUB_TOKEN`: manages dashboard-repository operations such as Pages
  deployment, export artifact upload, export artifact deletion, and optional
  README commits, with workflow permissions set in the generated workflows.
- `TRAFFIC_DASHBOARD_SECRET`: used only in the encrypted track to
  encrypt/decrypt retained traffic data and encrypted dashboard payloads.

The export/destroy workflows should not require a second personal access token.
`export` can upload a plaintext export artifact with a short retention period.
`destroy-exports` can use `GITHUB_TOKEN` with `actions: write` permission in the
dashboard repository to delete export artifacts created by Reponomics.

## Implementation Notes

Action runtime changes:

- replace `artifact-security-mode` with an explicit two-track input, or otherwise
  expose an equivalent setup contract without `auto`;
- keep encrypted retained artifact read/write behavior for the encrypted track;
- keep plaintext retained artifact read/write behavior for the plaintext private
  repository track;
- require `dashboard-secret` for encrypted-track `collect`, `publish`,
  `rotate-key`, and `export` runs;
- do not require `dashboard-secret` for plaintext-track collection or plaintext
  publication;
- add `export` mode that restores/decrypts encrypted retained state and writes a
  plaintext CSV export artifact payload with short retention;
- add `destroy-exports` mode that deletes export artifacts by name prefix and
  does not require the dashboard secret.

Generated template changes:

- ask users to choose the encrypted privacy track or plaintext private-repository
  track;
- for the encrypted track, require and validate `TRAFFIC_DASHBOARD_SECRET`;
- for the encrypted track, publish only encrypted Pages dashboards when Pages is
  enabled;
- for the encrypted track, ask whether to publish plaintext README summaries;
- for the plaintext track, store plaintext CSV artifacts and allow README
  summaries;
- for the plaintext track, allow optional plaintext Pages publication;
- add manual export and destroy workflows for encrypted-track CSV portability;
- document that export artifacts are plaintext and should be downloaded,
  deleted, or left to expire according to retention.

Test changes:

- remove tests for `auto` resolution;
- add tests for encrypted-track retained storage and encrypted Pages payloads;
- keep or add tests for plaintext-track retained artifact upload;
- add export tests proving the exported artifact contains the canonical CSV
  files and manifest;
- add destroy tests proving only Reponomics CSV export artifacts are deleted.

## Open Questions

- Should export artifacts use a stable name with overwrite behavior, or a
  per-run name with a shared prefix?
- Should `destroy-exports` delete every matching export artifact by default, or
  accept an optional age/run-id filter?
- Should the action continue accepting `artifact-security-mode` as a deprecated
  alias before `v1`, or remove it immediately while the project is still in
  public pre-release?
- What should the explicit two-track input be called in the action, if any?
- Should plaintext Pages publication be included in the template setup surface
  or remain an action-level capability for users who wire workflows manually?
