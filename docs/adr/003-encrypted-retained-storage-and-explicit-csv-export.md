# ADR 003: Encrypted Retained Storage And Explicit CSV Export

Date: 2026-05-21

## Status

Proposed

## Context

Reponomics currently supports multiple retained artifact storage modes:

- `encrypted`
- `plain`
- `auto`

That flexibility makes the runtime and setup contract harder to explain. Users
must distinguish repository visibility, retained artifact visibility, GitHub
Pages visibility, dashboard payload encryption, and README disclosure. The
`auto` mode is especially unclear because it asks users to trust conditional
runtime behavior rather than make an explicit privacy decision.

The emerging product position is simpler: Reponomics retains private GitHub
traffic history for maintainers and small operators, then lets them choose which
surfaces expose summaries or dashboards. The retained history should be private
by default and should not be committed to git.

Plain retained artifacts do have one important benefit: portability. The product
pitch includes the idea that the retained history is still ordinary CSV data
that users can move elsewhere. If retained storage is always encrypted,
portability must become a first-class workflow rather than a manual decryption
recipe.

## Proposed Decision

Remove plaintext retained artifact storage as a normal runtime mode.

The retained `traffic-data` artifact should always contain encrypted retained
state, encrypted with `TRAFFIC_DASHBOARD_SECRET`. The public action and generated
template should no longer expose `artifact-security-mode`, `plain`, or `auto`
for retained storage.

Add explicit export and cleanup workflows for plaintext CSV portability:

- `export` restores and decrypts the retained `traffic-data` artifact, packages
  the canonical CSV files, and uploads a separate plaintext export artifact.
- `destroy-exports` deletes plaintext export artifacts created by `export`.

Plaintext export artifacts should use a distinct name or prefix, for example:

```text
reponomics-csv-export-<run-id>
```

The generated template should provide manual workflows such as:

- **Export Reponomics CSV**
- **Destroy Reponomics CSV exports**

The export artifact should have short retention by default. Users who need a
weekly export for investors, backups, or downstream analysis can schedule export
runs deliberately, then either download the artifact and run cleanup or let
artifact retention expire.

## Consequences

The runtime privacy model becomes simpler:

- retained storage is always encrypted;
- GitHub Pages, when enabled, is encrypted;
- README metrics, when enabled, are plaintext committed output;
- plaintext CSV exists only after an explicit export workflow run.

This removes confusing combinations such as encrypted Pages with plaintext
retained artifacts. It also avoids presenting plaintext storage as a recommended
setup path.

The cost is that all normal collection and publication workflows require
`TRAFFIC_DASHBOARD_SECRET`. Users who do not need meaningful confidentiality can
use an intentionally weak key and set `allow-weak-dashboard-secret: true`, but
the storage mechanism remains encrypted-by-design.

Key loss becomes more serious. If the dashboard key is lost, retained history
cannot be recovered from encrypted artifacts. Documentation and setup summaries
must say this plainly.

Portability remains part of the product, but it moves to an explicit workflow:
users export plaintext CSV artifacts when they want to move data elsewhere.
Those artifacts are temporary disclosure events, not durable storage.

## Implementation Notes

Action runtime changes:

- remove `artifact-security-mode` from `action.yml`;
- remove `plain` and `auto` retained storage paths from the runtime;
- require `dashboard-secret` for normal `collect`, `publish`, `rotate-key`, and
  `export` runs;
- always restore/decrypt `data/traffic-data.enc`;
- always encrypt retained state to `.traffic-artifact/traffic-data.enc`;
- always upload `.traffic-artifact/traffic-data.enc` as `traffic-data`;
- add `export` mode that restores/decrypts retained state and writes a
  plaintext CSV export artifact payload;
- add `destroy-exports` mode that deletes export artifacts by name prefix and
  does not require the dashboard secret.

Generated template changes:

- remove artifact storage choices from setup;
- always require and validate `TRAFFIC_DASHBOARD_SECRET`;
- keep setup choices focused on hosted encrypted Pages and plaintext README
  metrics;
- add manual export and destroy workflows;
- document that export artifacts are plaintext and should be downloaded,
  deleted, or left to expire according to retention.

Test changes:

- remove tests for `auto` resolution and plain retained artifact upload;
- add tests for always-encrypted retained storage;
- add export tests proving the exported artifact contains the canonical CSV
  files and manifest;
- add destroy tests proving only Reponomics CSV export artifacts are deleted.

## Open Questions

- Should the export artifact default retention be 1 day, 7 days, or inherited
  from the repository's normal retention setting?
- Should export artifacts use a stable name with overwrite behavior, or a
  per-run name with a shared prefix?
- Should `destroy-exports` delete every matching export artifact by default, or
  accept an optional age/run-id filter?
- Should the action continue accepting `artifact-security-mode` as a deprecated
  no-op before `v1`, or remove it immediately while the project is still in
  public pre-release?

