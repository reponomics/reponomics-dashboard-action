# ADR 003: Two-Track Privacy Model And Dashboard-Local CSV Export

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
retained storage is encrypted, portability must be available without requiring
manual decryption commands.

## Initial Proposal

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

The setup flow should ask users to choose between the encrypted privacy track
and the plaintext private-repository track. It should not expose a
general-purpose matrix of storage and publication modes.

The initial export proposal added two manual workflows for encrypted-track CSV
portability:

- `export` restores and decrypts the retained `traffic-data` artifact, packages
  the canonical CSV files, and uploads a separate plaintext export artifact.
- `destroy-exports` deletes plaintext export artifacts created by `export`.

Export artifacts would have used a distinct name or prefix, short retention by
default, and cleanup through a separate workflow.

## Concern

The export/destroy workflow creates a temporary plaintext artifact in GitHub
Actions. In a public repository, workflow artifacts are available to users with
repository read access while the artifact exists. A short retention period and a
cleanup workflow reduce the exposure window, but they cannot prove that no one
downloaded the plaintext artifact before deletion.

That means export/destroy is not a privacy-preserving portability path for
public-repository users. It is a disclosure workflow.

The dashboard already has the data after unlock. For the encrypted track, the
browser receives encrypted dashboard data, the user enters the dashboard secret,
and the dashboard decrypts locally. Once that has happened, the dashboard can
generate CSV downloads in the browser without uploading plaintext back to
GitHub.

## Accepted Decision

Keep the two-track product model, but replace workflow export with
dashboard-local export for the encrypted track.

The primary track is the encrypted privacy model:

- retained collection data is stored in encrypted artifacts;
- GitHub Pages publication, when enabled, publishes an encrypted dashboard;
- the user decides whether to publish plaintext README dashboard summaries;
- plaintext CSV portability is provided by the unlocked dashboard in the
  browser.

The secondary track is the plaintext private-repository model:

- retained collection data is stored as plaintext CSV artifacts;
- README dashboard summaries are allowed because the repository is already
  treated as private;
- the user may optionally publish a plaintext GitHub Pages dashboard;
- no dashboard secret is required.

Remove `auto`. The setup flow should ask users to choose between the encrypted
privacy track and the plaintext private-repository track. It should not expose a
general-purpose matrix of storage and publication modes.

Do not ship export/destroy workflows as part of the product surface. For the
plaintext private-repository track, retained CSV artifacts are already
plaintext, so no special export workflow is necessary. For the encrypted track,
CSV export should happen from the unlocked dashboard after browser-side
decryption.

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

Portability remains part of the encrypted track, but it belongs inside the
dashboard. Users export plaintext CSV from the unlocked dashboard after local
decryption. Plaintext data should not be uploaded back to GitHub as an artifact
as part of the normal product surface.

## Credential Boundary

This decision preserves the core credential story. The encrypted track should
require one collection token plus one dashboard secret. The plaintext track
should require one collection token and no dashboard secret.

The product still has two separate API permission boundaries:

- collection access to the repositories whose traffic data is being read;
- dashboard-repository access for setup, workflow management, Pages deployment,
  and any committed README output.

Those boundaries should not be conflated in documentation. A collection token
may need read access across source repositories. Dashboard-repository operations
should use the default `GITHUB_TOKEN` whenever possible.

The credential model is:

- `TRAFFIC_TOKEN`: reads GitHub traffic and repository metadata for tracked
  repositories; used by `collect`.
- `GITHUB_TOKEN`: manages dashboard-repository operations such as Pages
  deployment and optional README commits, with workflow permissions set in the
  generated workflows.
- `TRAFFIC_DASHBOARD_SECRET`: used only in the encrypted track to
  encrypt/decrypt retained traffic data and encrypted dashboard payloads.

Dashboard-local export does not require another personal access token. It also
avoids requiring `actions: write` permission solely to clean up plaintext export
artifacts.

## Implementation Notes

Action runtime changes:

- replace `artifact-security-mode` with an explicit two-track input, or otherwise
  expose an equivalent setup contract without `auto`;
- keep encrypted retained artifact read/write behavior for the encrypted track;
- keep plaintext retained artifact read/write behavior for the plaintext private
  repository track;
- require `dashboard-secret` for encrypted-track `collect`, `publish`, and
  `rotate-key` runs;
- do not require `dashboard-secret` for plaintext-track collection or plaintext
  publication;
- do not add workflow modes that upload plaintext CSV export artifacts for the
  encrypted track.

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
- document that encrypted-track CSV export happens from the unlocked dashboard,
  not from a plaintext GitHub artifact.

Dashboard generator changes:

- add an export control to the unlocked dashboard;
- generate CSV from the decrypted retained data already available to the
  dashboard;
- perform the export entirely in the browser;
- ensure plaintext CSV is never uploaded to GitHub by this export path.

Test changes:

- remove tests for `auto` resolution;
- add tests for encrypted-track retained storage and encrypted Pages payloads;
- keep or add tests for plaintext-track retained artifact upload;
- add dashboard generator tests for local CSV export from decrypted dashboard
  data.

## Open Questions

- Should the action continue accepting `artifact-security-mode` as a deprecated
  alias before `v1`, or remove it immediately while the project is still in
  public pre-release?
- What should the explicit two-track input be called in the action, if any?
- Should plaintext Pages publication be included in the template setup surface
  or remain an action-level capability for users who wire workflows manually?
- Should dashboard-local export produce one combined CSV, one CSV per canonical
  table, or a ZIP containing the canonical CSV files?
