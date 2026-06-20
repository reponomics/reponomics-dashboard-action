# Completed TODO

This file is closed out as a historical checklist. Future-facing work now lives in `docs/ROADMAP.md`.

## Encrypted Dashboard Hardening

- [x] Validate encrypted dashboard payload metadata before WebCrypto work. The browser runtime should reject unexpected payload versions, cipher names, KDF names, KDF hashes, KDF iterations, salt sizes, IV sizes, and empty ciphertexts instead of trusting attacker-controlled payload fields.
- [x] Prefer generated high-entropy dashboard secrets in user guidance. Recommend `openssl rand -hex 32` as the simple shell-safe default, while noting that equivalent generated base64 secrets are cryptographically fine but easier to mishandle. \[NOTE: Data model has been clarified by three-way distinction: `strong`, `casual`, or `plain` (unencrypted).\]
- [x] Vendor Chart.js from a pinned npm tarball and validate the vendored bytes, license, upstream tarball integrity, and OSV vulnerability status through `make validate-vendored-assets`.
- [x] Render Pages output against the same-origin `assets/chart.umd.min.js` file and assert generated dashboard HTML does not reference remote JavaScript. Do not inline Chart.js into the Pages HTML; keeping it as a same-origin script is the cleaner CSP direction.
- [x] Keep retained data and generated dashboard output out of git. Dashboard delivery is via GitHub Pages artifacts for encrypted modes and workflow artifacts for private `plain` mode.
- [x] Add a generated CSP meta tag for dashboard HTML. The renderer hashes its inline CSS and first-party inline scripts, keeps Chart.js as a same-origin external script, allows only same-origin fetches, and avoids inline event handlers and HTML style attributes.
- [x] Resolve the standalone dashboard question. Do not promote `dist/dashboard-standalone.html` as a supported offline/mobile path; the supported convenience path is downloading the generated workflow artifact and serving the extracted dashboard over local HTTP when needed.
- [x] Use existing workflow artifacts as the offline/convenience access path instead of committing generated dashboard HTML or adding a separate offline zip. Encrypted modes reuse the Pages deployment artifact under `html-dashboard-encrypted`; private `plain` mode has a separate `html-dashboard-plaintext` artifact because Pages is intentionally disabled there. The README documents GitHub CLI download commands for both paths, and artifact retention remains the availability boundary.

## CI, Release, And Badge Hardening

- [x] Add first-party CI workflows for pull requests and pushes to `main`.
- [x] Run local verification through the project Makefile with lint and coverage.
- [x] Pin first-party workflow and composite-action `uses:` steps by full commit SHA.
- [x] Add Dependabot for GitHub Actions and Python dependencies.
- [x] Add `action-semantic-pull-request` for PR title validation.
- [x] Add `release-please` manifest configuration initialized at `0.1.0`.
- [x] Document current GitHub Marketplace packaging guidance for this Python-based action.
- [x] Add CodeQL scanning for the action/runtime code. Current repository state appears to rely on GitHub code scanning/default setup rather than a checked-in workflow.
- [x] Add OSSF Scorecard on push/merge to `main`. It can report posture without blocking normal CI while the project is still hardening.
- [x] Add open-source dependency vulnerability checks with `pip-audit` and OSV SARIF upload. These complement Dependabot and CodeQL rather than replacing them.
- [x] Generate SPDX SBOMs and release provenance attestations for repository source archives. This covers the composite-action release shape even though there is no package registry publish.
- [x] Decide whether to add Snyk, Codacy, or another public quality/security badge after the core GitHub-native checks are stable. Current decision: do not add a third-party SaaS scanner or badge yet. Revisit only if GitHub-native checks leave a concrete gap; start advisory-only, high-severity/SARIF-oriented, and pinned by full action SHA if added later.
- [x] Add public README badges once the workflows exist:
  - [x] project CI
  - [x] Dependabot Updates
  - [x] CodeQL
  - [x] OSSF Scorecard
  - [x] release/latest version if useful
- [x] Document repository settings that complement workflow checks, especially requiring SHA-pinned actions where GitHub repository/organization policy can enforce it. ~~Avoid duplicating that policy as a brittle custom CI check unless there is a concrete gap.~~ [CI checks are for badge visibility.]
