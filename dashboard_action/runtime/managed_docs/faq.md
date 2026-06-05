# Frequently Asked Questions

This FAQ explains user-facing privacy, storage, export, and trust-boundary concepts for repositories created from the Reponomics Dashboard template.

## Why are there several Reponomics repositories?

`reponomics-dashboard` is the template repository users create their own dashboard repositories from. `reponomics-dashboard-action` is the versioned runtime used by generated dashboard workflows; it owns collection, artifact restore/upload, schema migration, encryption, README rendering, HTML dashboard rendering, CSV export packaging, key rotation, and release notices.

This split keeps each generated user repository small and understandable while allowing the action runtime to receive fixes and features through normal version upgrades.

## What privacy mode should I choose?

Use `strong` unless you have a specific reason not to. It encrypts retained artifacts and hosted dashboard output with a high-entropy dashboard key. This is the right default for public repositories, sensitive dashboards, and any dashboard hosted with GitHub Pages.

Use `casual` only when you want to deter accidental viewing or casual discovery but are not trying to resist targeted guessing. It encrypts the same surfaces as `strong`, but allows weak or memorable secrets. Weak secrets can be guessed offline from encrypted dashboard payloads.

Use `plain` only in private repositories where GitHub repository and artifact access are the intended privacy boundary. `plain` stores retained CSV files directly in the `dashboard-data` artifact and does not publish a hosted Pages dashboard. The publish workflow can still generate a downloadable HTML dashboard artifact. For `strong` and `casual`, that downloadable artifact remains encrypted when hosted Pages publication is disabled.

For the full matrix, see [Privacy Configuration Matrix](privacy-configuration-matrix.md).

## How do I turn on the hosted GitHub Pages dashboard?

For `strong` or `casual`, first run the setup workflow. Then open the dashboard repository on GitHub and go to **Settings -> Pages**. Under **Build and deployment**, set **Source** to **GitHub Actions**. If GitHub suggests workflow templates, skip them; the Reponomics publish workflow already handles the Pages artifact upload and deployment.

The action verifies the Pages configuration during publish. It does not enable Pages or change the publishing source for you.

## What sort of dashboard key do I need?

For `strong`, use a high-entropy random key. A 32-byte random hex key generated with `openssl rand -hex 32` is appropriate. Store it in your password manager and in the repository secret named `DASHBOARD_SECRET_DO_NOT_REPLACE`.

For `casual`, any non-empty key is accepted, but a weak key only protects against casual discovery. It should not be treated as protection against a targeted attacker.

See [Secure Dashboard Key Generation](secure-dashboard-key.md).

## What does encryption protect?

In `strong` and `casual`, retained artifacts and hosted dashboard payloads are encrypted before they are stored or published. The hosted dashboard decrypts data only in your browser after you enter the dashboard key.

Encryption does not hide everything. A hosted encrypted dashboard can still disclose that the dashboard exists, update timing, artifact size, and the fact that the repository uses Reponomics. It also does not protect against malicious browser extensions, compromised devices, compromised CI/CD, malicious workflow changes, or people with repository control-plane access.

## Is any dashboard data committed to git history?

Only if you enable metric README generation in a private repository. In that case, the README dashboard and its supporting assets become part of git history.

Otherwise, retained dashboard data lives in GitHub Actions artifacts, not in the repository's tracked files. The HTML dashboard is rendered during workflow runs and is deployed only when hosted dashboard publication is enabled; otherwise it is uploaded as a downloadable artifact.

## Who should I trust with repository access?

Repository access is part of the dashboard security model. In personal private repositories, collaborators should be treated as trusted with the dashboard control plane, not merely as people who can read a report.

Collaborators may not be able to read existing secret values directly, but if they can update repository secrets, run workflows, or affect trusted workflow behavior, they can exfiltrate dashboard data through workflow changes, replace dashboard keys, take over publication, rotation, or incident-response flows, delete retained workflow runs or artifacts, deny access to current encrypted state, or cause data loss. A hostile collaborator could exfiltrate retained data, rotate to a key they control, and delete prior GitHub-hosted history before the owner notices. Branch rulesets can protect branches, but they are not a clean data-access boundary.

Do not treat GitHub policy enforcement, support, or retained workflow history as a backup plan. If retained dashboard history matters, periodically export an independent copy outside the repository control plane.

See [Repository Access And Trust Boundary](trust-boundary.md).

## Can someone use browser devtools to export CSV before unlocking the dashboard?

Not in a way that yields plaintext data. The export flow is wired after successful unlock, and the runtime keeps an explicit key gate before export work proceeds. Even if someone manually invokes JavaScript in devtools, the export asset is encrypted and cannot produce plaintext ZIP bytes without the correct dashboard key.

## If someone forces the export click path early, will plaintext ZIP download anyway?

No. The downloadable export asset is encrypted. Plaintext ZIP bytes are only produced after successful decryption with the correct dashboard key and digest verification.

## What checks does the browser run before CSV export download?

For encrypted exports, the browser verifies:

1. ciphertext size matches the embedded manifest
2. ciphertext SHA-256 matches the embedded manifest
3. AES-GCM decryption succeeds with the provided dashboard-key-derived key
4. decrypted ZIP SHA-256 matches the embedded manifest

Only then does the browser trigger the ZIP download.

## Why offer manual checksum copy if the browser already verifies export integrity?

Operational trust and auditability. Some users want an independent verification record or need to share verification details in support/debug workflows. The UI can copy a checksum line in the form `<sha256>  <filename>` so users can run local checksum checks.

## Does CSV export integrity checking protect against all attacks?

No. It protects export payload integrity within the client-side model. It does not replace broader trust in the action release, generated workflow, GitHub Actions execution, GitHub Pages deployment, browser, device, or dashboard key strength.

## How can I verify the action release and supply chain?

See [Provenance And Supply Chain Verification](provenance.md). It explains how to inspect the action ref your workflows use, verify vendored browser assets, check action release immutability and attestations, and understand which claims apply to generated artifacts in your own repository.

## What is the practical export difference between `strong` and `casual`?

Both modes keep export payloads encrypted at rest and in transit as published assets. The difference is key strength policy. `strong` requires a high-entropy secret and is intended to resist offline guessing. `casual` allows weak or memorable secrets and is not intended to resist determined brute-force attempts.
