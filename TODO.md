# TODO

## Encrypted Dashboard Hardening

Recently addressed:

- Validate encrypted dashboard payload metadata before WebCrypto work. The browser runtime should reject unexpected payload versions, cipher names, KDF names, KDF hashes, KDF iterations, salt sizes, IV sizes, and empty ciphertexts instead of trusting attacker-controlled payload fields.
- Prefer generated high-entropy dashboard secrets in user guidance. Recommend `openssl rand -hex 32` as the simple shell-safe default, while noting that equivalent generated base64 secrets are cryptographically fine but easier to mishandle.
- Vendor Chart.js from a pinned npm tarball, render Pages output against `docs/assets/chart.umd.min.js`, inline the same vendored asset in standalone HTML, and assert generated dashboard HTML does not reference remote JavaScript.

Deferred:

- Add a strict CSP for the Pages dashboard. Target posture:

  ```http
  Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'
  ```

- Generate and commit a standalone encrypted dashboard HTML file for mobile and offline accessibility. This should inline Chart.js and the encrypted payload so a user can download one file, store it on a phone, turn off networking, and still open the dashboard.
- Treat the standalone HTML file as a convenience/offline artifact with a less clean CSP story than the Pages output. Avoid CDN JavaScript there too; if CSP is embedded, prefer generated script hashes over `unsafe-inline`.
- Optionally upload an offline zip artifact containing the same dashboard files for desktop and power users, but do not rely on GitHub Actions artifacts as the primary mobile/vibe-coder access path.

## CI, Release, And Badge Hardening

Recently addressed:

- Add first-party CI workflows for pull requests and pushes to `main`.
- Run local verification through the project Makefile with lint and coverage.
- Pin first-party workflow and composite-action `uses:` steps by full commit SHA.
- Add Dependabot for GitHub Actions and Python dependencies.
- Add `action-semantic-pull-request` for PR title validation.
- Add `release-please` manifest configuration initialized at `0.1.0`.
- Document current GitHub Marketplace packaging guidance for this Python-based action.

Deferred:

- Before first release, add a proper complexity gate with `antipasta` and `complexipy` after reducing large runtime modules and high-complexity functions. Initial targets include `load_data.py`, `collect.py`, `release_notice.py`, and the dashboard/rendering modules.
- Add CodeQL scanning for the action/runtime code.
- Add OSSF Scorecard on push/merge to `main`. It can report posture without
  blocking normal CI while the project is still hardening.
- Decide whether to add Snyk, Codacy, or another public quality/security badge
  after the core GitHub-native checks are stable.
- Add public README badges once the workflows exist:
  - project CI
  - Dependabot Updates
  - CodeQL
  - OSSF Scorecard
  - release/latest version if useful
- Document repository settings that complement workflow checks, especially requiring SHA-pinned actions where GitHub repository/organization policy can enforce it. Avoid duplicating that policy as a brittle custom CI check unless there is a concrete gap.
- Confirm commit identity/signing policy for harness-generated or bot-generated commits before enabling automated release/update workflows. Prefer an explicit Reponomics actor only if its credentials, signing behavior, and audit trail are clear.
