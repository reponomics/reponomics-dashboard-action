# Provenance And Supply Chain Verification

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

This document explains how a dashboard repository user can inspect the evidence behind the Reponomics action, generated template, vendored browser assets, release materials, and generated dashboard artifacts. It is intentionally conservative: a claim belongs here only if it is backed by repository files, CI, GitHub metadata, or a command a user can run.

Most users should follow the setup guide and use the recommended action version. This document is for users, researchers, maintainers, or reviewers who want a higher-assurance review path.

## Short Version

- The highest-assurance way to consume the runtime is by full commit SHA: `uses: reponomics/reponomics-dashboard-action@<40-character-commit-sha>`. With a full SHA, the action code GitHub runs is the repository tree at that immutable commit. Version tags are more convenient, but they trade some strict pinning assurance for easier updates.
- The generated template repository is intentionally thin. It delegates collection, encryption, rendering, CSV export, and key rotation to `reponomics-dashboard-action`.
- Chart.js and dashboard fonts are vendored by the action, not loaded from CDNs. The action repository records exact npm package versions, tarball integrity values, local SHA-256 digests, and license digests.
- Runtime Python dependencies are installed from the action's committed `requirements-runtime.txt` file in hash-required mode.
- The action repository CI validates imported action SHA pins, vendored browser assets, runtime dependency locks, tests, type checks, CodeQL, OSV scanning, Scorecard, and release notice fixtures.
- GitHub immutable releases are enabled for action releases. You can inspect release immutability, target commit, and release attestations with GitHub CLI.
- No release attestation from the action repository covers every dashboard artifact generated inside your own repository. Generated artifacts inherit your repository's workflow identity, permissions, secrets, action ref, artifact retention, and Pages settings.

## What To Verify In Your Dashboard Repository

Start with the workflow files in your dashboard repository:

- `.github/workflows/collect-and-publish.yml`
- `.github/workflows/rotate-key.yml`
- `.github/workflows/incident-reset.yml`
- `.github/workflows/keepalive.yml`

Check which action ref each workflow uses:

```bash
grep -R "reponomics/reponomics-dashboard-action@" .github/workflows
```

If the workflow uses a tag such as `v0.13.1` or `v0.13`, resolve that tag in the action repository:

```bash
gh api repos/reponomics/reponomics-dashboard-action/git/ref/tags/v0.13.1 --jq '.object.sha'
```

If you want the strongest pinning posture, replace the tag with the 40-character commit SHA after reviewing that exact source tree:

```yaml
uses: reponomics/reponomics-dashboard-action@<40-character-commit-sha>
```

That makes updates explicit. You will need to update the SHA yourself when you want compatible fixes or new features.

## How To Verify The Action Source

Inspect the exact source tree GitHub Actions will run:

```text
https://github.com/reponomics/reponomics-dashboard-action/tree/<ref-or-commit-sha>
```

For a focused review, inspect:

- `action.yml`
- `dashboard_action/run.py`
- `dashboard_action/runtime/scripts/render_dashboard.py`
- `dashboard_action/runtime/scripts/render_readme.py`
- `dashboard_action/runtime/scripts/crypto_artifact.py`
- `requirements-runtime.txt`
- `vendor/*/manifest.json`

The action itself pins imported GitHub Actions by full commit SHA. The action repository validates those pins in CI.

## How To Verify Vendored Browser Assets

The hosted dashboard loads Chart.js from a same-origin generated asset, not from a CDN. The action renderer copies that file from the action repository's vendored `vendor/chart.js/chart.umd.min.js` file. Dashboard fonts are also vendored by the action and embedded into generated CSS.

To inspect vendored asset metadata without cloning, replace `REF` with the action ref or commit SHA you are evaluating:

```bash
curl -fsSL "https://raw.githubusercontent.com/reponomics/reponomics-dashboard-action/REF/vendor/chart.js/manifest.json"
curl -fsSL "https://raw.githubusercontent.com/reponomics/reponomics-dashboard-action/REF/vendor/chart.js/chart.umd.min.js" | shasum -a 256
```

The expected digest is the `sha256` value in the corresponding manifest at the same ref.

For a fuller local check:

```bash
git clone https://github.com/reponomics/reponomics-dashboard-action.git
cd reponomics-dashboard-action
git checkout <ref-or-commit-sha>
make validate-vendored-assets
```

That validator downloads the recorded npm package tarballs, verifies tarball integrity, extracts the recorded upstream files, hashes them, and compares those hashes to the committed manifests and local vendored files.

## How To Verify A Release

Check whether an action release is immutable and what commit it targets:

```bash
gh release view TAG --repo reponomics/reponomics-dashboard-action --json isImmutable,targetCommitish,url
```

Verify GitHub's release attestation:

```bash
gh release verify TAG --repo reponomics/reponomics-dashboard-action --format json
```

Compare the release target or attested subject against the action ref used by your workflow. If they do not identify the same source tree, they are evidence for different things.

The action's SBOM/provenance workflow creates SPDX SBOMs and GitHub artifact attestations for release source archives. Because the action is consumed by Git ref rather than through a package registry, that attestation covers the release source archive, not a registry package install.

## How To Think About Generated Dashboard Artifacts

Dashboard HTML, Pages artifacts, README output, and private plain dashboard artifacts are generated inside your dashboard repository's workflow run. They inherit your repository's:

- workflow files and action refs
- repository secrets and permissions
- branch protections and rulesets
- GitHub Pages settings
- artifact retention settings
- collaborator and organization access model

The Reponomics project can provide tests, release evidence, and documented expectations for generated artifacts. It cannot globally attest every artifact generated inside every user's repository.

Generated dashboard HTML uses a summary plus per-repository chunk model so the browser can load repository detail data only as repositories are selected. For encrypted dashboards, the generated HTML includes an encrypted dashboard data object with an encrypted summary and per-repository encrypted chunks, plus an encrypted CSV export manifest. For plaintext dashboard artifacts, the same summary/chunk boundary is used without encryption. CSV export downloads a separate encrypted asset on demand, verifies ciphertext size and SHA-256, decrypts locally in the browser, verifies the decrypted ZIP SHA-256, and only then triggers the download.

## Verification Limits

No scanner can prove absence of vulnerabilities. `pip-audit`, OSV, CodeQL, Dependabot, Scorecard, release attestations, vendored asset validation, and SHA pinning are layered evidence and hardening controls, not absolute guarantees.

Reponomics also cannot protect against every consumer-side choice. A dashboard repository can weaken its posture by changing workflow permissions, using a weak dashboard key, giving collaborators broad control, changing action refs without review, disabling security workflows, or running on compromised infrastructure.

For repository access implications, see [Repository Access And Trust Boundary](trust-boundary.md).
