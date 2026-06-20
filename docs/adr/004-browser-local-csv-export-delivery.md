# ADR 004: Browser-Local CSV Export Delivery For Encrypted Dashboards

Date: 2026-05-22

## Status

Proposed

## Context

ADR 003 established that encrypted-mode CSV portability must happen in the browser after unlock, not through plaintext workflow artifacts.

The product now has an additional implementation constraint:

- retained data should remain artifact-backed, not committed in repository history;
- generated dashboard outputs are deployed as GitHub Pages artifacts, not committed;
- plaintext CSV must never be uploaded by the export path.

The remaining open design question is how encrypted dashboards should deliver portable CSV data to the browser while preserving strict privacy expectations and reasonable page size/performance.

## Decision Drivers

- keep plaintext off GitHub storage surfaces outside user-initiated download;
- keep encrypted export data out of git history;
- preserve canonical CSV fidelity (not lossy aggregates);
- avoid large first-load HTML payload growth;
- maintain simple user flow: unlock, click export, receive files.

## Options Considered

## Option A: Reconstruct CSV From Existing Decrypted Dashboard Payload

The dashboard would serialize CSV from data already used for charts and tables.

Pros:

- no additional encrypted export payload;
- minimal changes to publish pipeline.

Cons:

- lossy with current payload shape (top-N truncation and aggregated views);
- cannot guarantee canonical export parity with retained artifact files;
- fragile whenever dashboard view models evolve.

## Option B: Inline Encrypted Export Bundle Inside `index.html`

At publish time, create a canonical CSV ZIP bundle, encrypt it, and embed it as an additional payload block in the HTML.

Pros:

- single-file export path after unlock;
- no extra client fetch.

Cons:

- materially increases initial HTML size;
- base64 adds ~33% overhead on encrypted bytes;
- higher parse/decode cost on every dashboard load, including users who never export.

## Option C: Publish A Separate Encrypted Export Asset (Recommended)

At publish time, create a canonical CSV ZIP bundle, encrypt it, and publish it as a separate asset in the Pages artifact (for example `assets/export-data-<digest>.enc`). Keep only a small export manifest in `index.html`.

Pros:

- preserves canonical CSV fidelity;
- keeps encrypted export data out of git history;
- avoids inflating initial HTML with rarely used export bytes;
- browser only downloads export payload on explicit user action.

Cons:

- additional runtime fetch step during export;
- requires explicit asset-manifest integrity checks.

## Option D: Plaintext Workflow Export Artifact

Workflow decrypts retained artifact and uploads plaintext export artifact.

Pros:

- simple technical implementation.

Cons:

- rejected by ADR 003 because plaintext artifact visibility is a disclosure surface;
- conflicts with strict privacy expectations for public repositories.

## Proposed Decision

Adopt Option C for `strong` and `casual` privacy modes.

Key points:

- export bundle format is ZIP containing canonical CSV files from `storage.CSV_REGISTRY` plus `manifest.json`;
- ZIP bundle is encrypted at publish time with the same dashboard secret boundary as the encrypted dashboard payload;
- encrypted export bundle is published as a Pages asset and not committed to the repository;
- dashboard fetches and decrypts the bundle only after unlock and explicit user export action;
- plaintext export exists only in browser memory and user download output.

This keeps the retained-data and publication model artifact-backed while avoiding plaintext workflow artifacts.

## Implementation Qualifications

- Export scope defaults to canonical retained data fidelity. The bundle includes the full retained canonical file set (including repos currently excluded from dashboard rendering) unless a future decision explicitly introduces scoped export modes.
- Offline/local-file export is best-effort. If browser origin rules block asset fetch (for example `file://` behavior), the runtime must fail closed with a clear user-facing error and no partial plaintext output.
- The encrypted export asset path should be cache-safe (content-addressed filename) so dashboard pages and export assets stay aligned across deploys.

## Open Questions Resolved

1. Should export include excluded repos from retained canonical history, or only currently visible dashboard scope? Answer: canonical retained scope. Export includes the full canonical retained fileset (including excluded repos) to preserve portability and deterministic parity with retained artifacts.

2. Is offline `file://` export support mandatory or best-effort? Answer: best-effort. Hosted Pages and local HTTP serving are supported paths. Direct `file://` export may fail due to browser fetch/CORS behavior; runtime must fail closed with explicit user-facing errors and no partial plaintext output.

3. Do we require performance budgets in ADR acceptance? Answer: yes, with layered enforcement:

   - Hard budget: export ciphertext bytes in initial HTML must be zero.
   - Hard budget: export fetch/decrypt work must happen only on explicit export click (not during first-load render path).
   - Operational target: for a reference profile of 50 repos, 90 retained days, and one effective collect per day, export click-to-download should remain within a practical desktop interactive range. This is a release target, not a CI gate, until browser-runtime benchmark automation is added.

## Integrity Model Clarification

- `ciphertext_sha256` detects transport/cache corruption before decrypt.
- AES-GCM decryption success/failure provides keyed ciphertext integrity/authenticity checks at decrypt time.
- `plaintext_sha256` verifies the decrypted bytes match the publish-time canonical ZIP bundle before download.
- These controls do not replace trust in the build/deploy pipeline itself.

## Caveat Status

- Cache-safe asset versioning: addressed with content-addressed export asset filenames (`assets/export-data-<digest>.enc`) and strict manifest asset-path validation.
- Offline compatibility criteria: addressed with explicit best-effort policy for `file://`, fail-closed runtime behavior, and documented hosted/local-HTTP fallback.
- Integrity language precision: addressed by distinguishing ciphertext digest, AEAD decrypt integrity/authenticity checks, and decrypted-bytes digest parity.

## Security Requirements

- no plaintext export upload to GitHub artifacts, repository commits, or API;
- no persistence of decrypted export bytes in `localStorage` or `sessionStorage`;
- no logging of plaintext rows, keys, or decrypted bundle contents;
- after download creation, revoke object URLs and clear in-memory references as best effort;
- validate encrypted payload metadata before decryption;
- validate decrypted bytes against an expected digest from the manifest before download.

## Implementation Notes

Runtime publish path:

- build deterministic ZIP bundle from canonical files: `traffic-log.csv`, `traffic-daily.csv`, `traffic-snapshots.csv`, `traffic-referrers.csv`, `traffic-paths.csv`, `repo-metrics.csv`, and `manifest.json`;
- encrypt bundle into a content-addressed Pages asset path such as `assets/export-data-<digest>.enc`;
- emit compact `export-manifest` JSON in `index.html` with: `version`, `cipher`, `kdf`, `salt`, `iv`, `ciphertext_sha256`, `plaintext_sha256`, `ciphertext_size`, `filename`.

Dashboard runtime:

- show `Export CSV` control only after successful unlock;
- on click: fetch encrypted asset, validate metadata, decrypt in-browser, verify digest, then download ZIP;
- filename pattern: `reponomics-export-YYYYMMDDTHHMMSSZ.zip`;
- show explicit user-facing errors for fetch/decrypt/integrity failures.

Privacy modes:

- `strong` and `casual`: enabled via encrypted export asset path above;
- `plain`: no Pages dashboard publication, so this ADR does not add a Pages export path for plain mode.

## Consequences

- user experience remains simple and explicit;
- initial dashboard load avoids export-byte inflation;
- portability is canonical and deterministic;
- implementation adds a small asset/manifest management surface that must be covered by tests.

## Test Plan

- renderer tests: encrypted dashboards include export manifest metadata and export control, with no plaintext CSV data in HTML;
- publish tests: export asset exists in Pages output and matches expected metadata;
- crypto tests: round-trip decrypt of export asset reproduces canonical files;
- browser-runtime tests: export is unavailable pre-unlock and works post-unlock;
- browser compatibility checks: `file://` export limitations fail closed with explicit error messaging and no partial plaintext output;
- negative tests: digest mismatch and wrong key are handled safely without partial plaintext output.

## Non-Goals

- adding plaintext export workflows in GitHub Actions;
- exposing alternative export transforms (single merged CSV, JSON, etc.) in this decision;
- changing retained artifact schema or retention policy.
