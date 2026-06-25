# ADR 026: Native ESM Dashboard Runtime

Date: 2026-06-19

## Status

Accepted

## Context

The generated HTML dashboard had grown from a single runtime into several
ordered first-party script files, but those files still behaved like one
decomposed global program. Runtime functions, constants, and mutable state were
shared through implicit global scope and script ordering. That made the
dashboard hard to test, refactor, and extend because a change in one file could
depend on names created by another file without an explicit import boundary.

The pre-refactor generated Pages dashboard also relied on embedded inert JSON
payloads and several same-origin first-party scripts. Its Content Security
Policy allowed `default-src 'self'`, same-origin scripts/styles/fonts/images,
`img-src data:`, `connect-src 'self'`, and `form-action 'self'`. That was a
reasonable static-site policy, but the dashboard could be stricter because the
published product does not need inline executable code, forms, frames, media,
workers, or arbitrary fallback loading.

The product constraints for this change were:

- keep encrypted GitHub Pages dashboards as the primary product surface;
- preserve the chunked encrypted dashboard payload model;
- preserve browser-local encrypted CSV export;
- avoid new npm, bundler, CDN, or third-party runtime dependencies;
- keep vendored Chart.js, fonts, CSS, dashboard code, encrypted payloads, and
  export assets same-origin;
- retain compatibility for private plaintext and local artifact workflows;
- keep the standalone single-file dashboard as a secondary compatibility
  artifact, not as the primary architecture constraint.

## Decision

Use native browser ES modules for the hosted dashboard runtime.

Published dashboards now load:

- same-origin CSS and fonts from `assets/`;
- same-origin vendored `assets/chart.umd.min.js`;
- same-origin first-party ESM entries under `assets/dashboard/`;
- same-origin JSON payload assets for dashboard data and export manifests.

The first-party runtime is organized as an explicit module tree rooted at:

- `assets/dashboard/entry-secure.js` for encrypted Pages output;
- `assets/dashboard/entry-public.js` for private plaintext artifact output;
- `assets/dashboard/theme-preload.js` for early theme application;
- `assets/dashboard/app.js` for application context construction and lifecycle
  orchestration.

The app shell constructs a `DashboardContext`-style object and installs runtime
capabilities into that context. Domain and UI slices are represented as module
installers such as `state`, `data-provider`, `format`, `selection`, `series`,
`momentum`, `quality-calendar`, `chart-options`, `controls`, `charts`,
`tables`, and `controller`.

This is intentionally an architectural foundation rather than a complete
perfectly factored frontend rewrite. Some modules still expose larger runtime
slices than we ultimately want. The important accepted boundary is that
cross-file dependencies are now expressed through ESM imports and app-owned
context instead of implicit global script ordering.

Only the Chart.js adapter may read `globalThis.Chart`. The rest of the
first-party runtime receives chart construction through the app context.

## CSP

Generated GitHub Pages HTML uses this exact meta CSP:

```http
default-src 'none'; base-uri 'none'; object-src 'none'; script-src 'self'; script-src-elem 'self'; script-src-attr 'none'; style-src 'self'; style-src-elem 'self'; style-src-attr 'none'; font-src 'self'; img-src 'self'; connect-src 'self'; media-src 'none'; frame-src 'none'; child-src 'none'; worker-src 'none'; manifest-src 'none'; form-action 'none'
```

Hosts that can set HTTP headers should use the same policy plus
`frame-ancestors 'none'`:

```http
default-src 'none'; base-uri 'none'; object-src 'none'; script-src 'self'; script-src-elem 'self'; script-src-attr 'none'; style-src 'self'; style-src-elem 'self'; style-src-attr 'none'; font-src 'self'; img-src 'self'; connect-src 'self'; media-src 'none'; frame-src 'none'; child-src 'none'; worker-src 'none'; manifest-src 'none'; form-action 'none'; frame-ancestors 'none'
```

`frame-ancestors` is not included in the generated meta CSP because browsers
ignore it in meta-delivered policies.

`connect-src 'self'` remains necessary for the product surface because the ESM
runtime fetches same-origin JSON payload assets and the encrypted export asset.
The export path fetches `assets/export-data-<hash>.enc`, verifies ciphertext
size and SHA-256, decrypts locally with the dashboard key, verifies the
plaintext ZIP SHA-256, and then prepares the browser-local download.

Compared with the prior generated Pages policy, this is stricter in the primary
published surface:

- `default-src` changes from `'self'` to `'none'`;
- inline executable scripts are not allowed;
- inline styles and style attributes are not allowed;
- script attributes are forbidden;
- `img-src data:` is removed;
- forms cannot submit anywhere;
- frames, children, workers, media, and manifests are explicitly denied.

## Data And Export Payloads

The chunked encrypted payload model is unchanged.

Encrypted dashboard data still has the same browser envelope shape:

- dashboard data version;
- AES-GCM cipher metadata;
- PBKDF2 metadata;
- salt;
- encrypted gzip+JSON summary token;
- encrypted per-repository chunk tokens;
- `chunk_count`.

The carrier changed for published Pages output. Instead of embedding the
encrypted envelope in an inert JSON script tag, the generated HTML now points to
`assets/encrypted-dashboard-data.json` with:

```html
<meta name="reponomics-encrypted-dashboard-data" content="assets/encrypted-dashboard-data.json">
```

Plaintext artifact output analogously points to `assets/dashboard-data.json`.
The encrypted export manifest is written to `assets/export-manifest.json` and
referenced by:

```html
<meta name="reponomics-export-manifest" content="assets/export-manifest.json">
```

Legacy embedded JSON script fallback remains in the runtime and doctor
diagnostics so older generated artifacts and local compatibility surfaces can
still be inspected.

## Standalone Artifact

The standalone single-file dashboard is retained as a compatibility artifact,
but it is no longer the primary design constraint.

For standalone output, the renderer mechanically flattens the first-party
module sources into a single inline runtime and keeps the payload embedded as
inert JSON. The standalone CSP remains looser and hash-based because the
artifact is designed for local/offline viewing and cannot rely on loading an
ESM graph from separate files. This preserves the practical single-file upload
and artifact-download workflow while allowing the hosted product surface to use
real modules and a stronger CSP.

Standalone compatibility does not imply that future dashboard architecture must
be optimized for single-file output. If the standalone artifact becomes
incompatible with necessary product changes, it can be further demoted or
replaced with an extracted-artifact workflow.

## Product Changes

The primary encrypted Pages dashboard remains functionally the same from the
user's perspective:

- the user opens a generated dashboard;
- enters the dashboard key;
- decrypts summary and per-repository chunks locally;
- sees the same dashboard controls and charts;
- can export retained CSV data through the encrypted export control.

Generated published dashboard directories now contain additional first-party
assets:

- `assets/dashboard/*.js`;
- `assets/encrypted-dashboard-data.json` or `assets/dashboard-data.json`;
- `assets/export-manifest.json` for encrypted output.

Private plaintext artifact output also uses the ESM entry and external JSON
payload asset. Plaintext Pages publication remains disallowed by policy.

Local `file://` viewing of extracted encrypted artifacts may still be blocked
by browser fetch restrictions. The documented workaround remains to use hosted
Pages or serve the extracted artifact over local HTTP.

## Provenance And Asset Validation

This change does not add third-party dependencies or a JavaScript package
manager. Chart.js and fonts remain vendored assets governed by the existing
vendored-asset validation flow.

Package data now includes nested dashboard module assets so built wheels carry
the complete ESM tree. Tests assert that the nested module assets are included
in the built package.

Scenario snapshots now record the new published HTML contract: strict CSP,
module entries, and external JSON payload metadata instead of embedded payload
JSON. The snapshots intentionally do not duplicate the full payload inside the
HTML file.

The generated payload and export asset hashes remain part of the existing data
and export contracts:

- encrypted export manifests still record ciphertext size, ciphertext SHA-256,
  plaintext SHA-256, IV, salt, and KDF metadata;
- export ciphertext assets still use the hashed
  `assets/export-data-<hash>.enc` naming pattern;
- browser runtime and doctor diagnostics validate the export contract before
  reporting success.

The source repository provenance model is otherwise unchanged. This ADR records
an implementation architecture decision for generated dashboard runtime assets;
it does not change release attestation, template provenance, dependency-lock,
or SBOM policy.

## Test Coverage

The implementation added or updated coverage for:

- no-dependency Node module tests using `node --test`;
- importability of the ESM module graph without DOM globals for domain-oriented
  modules;
- app-context and state isolation;
- focused domain helper behavior for formatting and series aggregation;
- published HTML module entry assertions;
- exact published meta CSP assertions;
- package-data inclusion of nested ESM assets;
- external JSON payload asset handling;
- doctor diagnostics for both external JSON assets and legacy embedded JSON
  scripts;
- encrypted export manifest and encrypted export asset validation;
- dashboard scenario snapshots under the new published HTML contract.

Browser smoke verified the generated encrypted Pages artifact over local HTTP:

- ESM graph loaded from same-origin `assets/dashboard/`;
- unlock/decryption succeeded;
- dashboard rendered populated stats and chart canvases;
- encrypted export fetched `assets/export-data-<hash>.enc`, decrypted locally,
  and reported the expected ZIP SHA-256;
- no CSP console warnings or runtime console errors were observed.

The in-app browser used for smoke testing does not support download events, so
the final native download event itself was not asserted there. The runtime did
complete the fetch/decrypt/hash path and reported export success.

## Consequences

- The dashboard runtime now has a maintainable module boundary suitable for
  independent testing and future refactoring.
- Published Pages CSP is substantially stronger than before.
- Same-origin fetch is now part of the normal dashboard boot path for payload
  JSON, not only export.
- The generated published artifact contains more files, but still requires no
  build step, bundler, CDN, or npm dependency.
- The standalone artifact remains possible, but it has a different CSP and
  different runtime carrier than hosted Pages.
- Doctor diagnostics and tests must understand both the current external JSON
  format and older embedded JSON format.
- Snapshot diffs for dashboard HTML are smaller with respect to data payloads,
  but payload regressions now require checking the referenced JSON assets.

## Open Questions

- Whether future refactors should replace installer-style modules with smaller
  direct imports and pure exports once the current architecture has settled.
- Whether to add a dedicated JavaScript lint or type-check step without
  introducing an npm dependency chain.
- Whether hosted environments outside GitHub Pages should emit the header CSP
  with `frame-ancestors 'none'`, and where that should be documented for users
  who self-host generated artifacts.
- Whether standalone output should remain indefinitely supported or be replaced
  by a documented extracted-artifact local HTTP workflow.
- Whether to update broader user documentation to emphasize that generated
  published dashboards now load same-origin JSON payload assets during boot.

## Non-Goals

- This ADR does not introduce a bundler, transpiler, package manager, CDN, or
  third-party frontend dependency.
- This ADR does not redesign the dashboard UI or data model.
- This ADR does not change the encryption algorithm, PBKDF2 parameters,
  chunked payload schema, export manifest schema, or retained artifact format.
- This ADR does not make plaintext Pages publication acceptable.
- This ADR does not define a full frontend style guide or final module
  taxonomy.
