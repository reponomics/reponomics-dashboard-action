---
name: PROVENANCE.md
description: Describe the various ways in which distribution assets and repository artifacts can be verified and supply chain/provenance guarantees can be established.
created: 2026-05-26
modified: 2026-05-26
---

# Provenance

This document summarizes what this repository can currently assert about source authenticity, vendored asset provenance, release materials, generated artifacts, and integrity checks. It is intentionally conservative: a claim belongs here only if it is backed by repository files, CI, GitHub metadata, or a command a user can run.

## Short Version

- The strongest way to consume the action is by full commit SHA: `uses: reponomics/reponomics-dashboard-action@<40-character-commit-sha>`. With a full SHA, the action code GitHub runs is the repository tree at that immutable commit.
- Chart.js is vendored, not loaded from a CDN. The current manifest records `chart.js@4.5.1`, npm registry metadata, the npm tarball URL and integrity value, the upstream source path `package/dist/chart.umd.min.js`, the local path `vendor/chart.js/chart.umd.min.js`, and the local SHA-256 digest `48444a82d4edcb5bec0f1965faacdde18d9c17db3063d042abada2f705c9f54a`.
- `make validate-vendored-assets` verifies that the vendored Chart.js bytes and license bytes match the recorded npm package tarball, verifies the tarball SRI value against the downloaded tarball, confirms the registry still reports the recorded tarball and integrity metadata for the pinned package version, and checks OSV for known vulnerabilities in that pinned package version.
- Published dashboard HTML loads Chart.js from `assets/chart.umd.min.js` in the same generated artifact, and the renderer copies that file from `vendor/chart.js/chart.umd.min.js`. The supported path is not a remote script and not a CDN.
- Repository CI validates workflow/action SHA pins, vendored assets, tests, type checks, Python dependency audit, OSV SARIF scanning, Scorecard, and CodeQL. These are hardening and detection controls; they are not a substitute for pinning the action by commit SHA.
- The SBOM/provenance workflow generates SPDX SBOMs and GitHub artifact attestations for release source archives. Because this is a composite action consumed by Git ref rather than a package registry artifact, the release attestation covers the source archive produced from the release checkout, not a registry package.

## What Can Be Asserted

### Source Identity For Consumers

- This repository distributes a composite GitHub Action. A consuming workflow that uses `reponomics/reponomics-dashboard-action@REF` causes GitHub Actions to fetch this repository at `REF` and run `action.yml` from that checkout.
- If `REF` is a full 40-character commit SHA, the consumed source tree is fixed by Git object identity. A user can inspect the exact source at `https://github.com/reponomics/reponomics-dashboard-action/tree/<commit-sha>`.
- If `REF` is a tag such as `v0.11.0` or `v0.11`, the user can inspect which commit the tag currently resolves to, but a tag is a weaker reference than a full commit SHA unless repository policy and GitHub protections are relied on. The strongest recommendation remains full-SHA pinning.
- The action itself uses full-SHA pins for imported GitHub Actions in `action.yml`, and `scripts/validate_action_pins.py` enforces that policy for `action.yml` and `.github` workflow files.

### Vendored Browser Assets

- Each vendored browser asset has a manifest under `vendor/*/manifest.json`. The manifest identifies the npm package, exact version, registry, tarball URL, npm tarball integrity value, upstream path inside the tarball, local vendored path, local SHA-256 hash, license source path, local license path, and license SHA-256 hash.
- For Chart.js specifically, `vendor/chart.js/manifest.json` identifies the asset as `chart.js@4.5.1` from `https://registry.npmjs.org/chart.js/-/chart.js-4.5.1.tgz`, with `vendor/chart.js/chart.umd.min.js` matching upstream `package/dist/chart.umd.min.js`.
- `scripts/validate_vendored_assets.py` proves byte identity against the published npm tarball at validation time. It does not merely trust the local hash; it downloads the recorded package tarball, verifies the tarball integrity, extracts the recorded upstream file, hashes it, and compares that hash to the local manifest and local file.
- `.github/workflows/validate-vendored-assets.yml` runs the vendored asset validator on pushes to `main`, on a weekly schedule, manually, and through the aggregate CI workflow. A passing run is evidence that the committed vendored asset still matches its recorded upstream package artifact and has no known OSV vulnerability at that package version at the time of the run.

### Dashboard Asset Inclusion

- The dashboard renderer defines `VENDORED_CHART_JS_PATH = ACTION_ROOT / "vendor" / "chart.js" / "chart.umd.min.js"` and publishes `assets/chart.umd.min.js` by copying that vendored file.
- The generated Pages dashboard references `<script src="assets/chart.umd.min.js"></script>`, so the published dashboard uses the same-origin asset copied from the action checkout, not a remote network script.
- Standalone local dashboard output may inline Chart.js for local development convenience, but it is not the supported offline/mobile distribution path. The supported convenience path is downloading the workflow artifact and serving the extracted dashboard over local HTTP when needed.

### Release Materials

- `.github/workflows/sbom-provenance.yml` generates an SPDX JSON SBOM with Anchore's SBOM action and submits dependency information to GitHub's dependency graph.
- For published releases and manual runs, the same workflow creates a `git archive` source tarball from the release checkout, generates a matching SPDX SBOM, and uses GitHub artifact attestations for both the source archive and the SBOM.
- These attestations establish GitHub-hosted provenance for the generated release source archive and SBOM. They do not change how GitHub Actions consumes this repository as a composite action; consumers still get the source tree for the ref they use.

### Vulnerability And Supply-Chain Signals

- `pip-audit` audits the resolved local Python environment used by the repository checks. This is a vulnerability signal for resolved Python dependencies, not a cryptographic provenance claim.
- OSV-Scanner uploads SARIF for repository-level dependency vulnerability scanning.
- CodeQL, Scorecard, Dependabot, branch/repository settings, and action SHA pin validation provide additional hardening signals. They should be read as layered controls, not as proof that every future dependency resolution is identical.

## How To Verify The Chart.js Claim

1. Inspect `vendor/chart.js/manifest.json` in the exact commit you plan to consume.
2. Check the local hash in that commit:

```bash
shasum -a 256 vendor/chart.js/chart.umd.min.js
```

3. Run the validator from a checkout of that commit:

```bash
make validate-vendored-assets
```

4. To inspect the file without cloning, replace `REF` with the commit SHA or tag you are evaluating:

```bash
curl -fsSL "https://raw.githubusercontent.com/reponomics/reponomics-dashboard-action/REF/vendor/chart.js/manifest.json"
curl -fsSL "https://raw.githubusercontent.com/reponomics/reponomics-dashboard-action/REF/vendor/chart.js/chart.umd.min.js" | shasum -a 256
```

The expected Chart.js digest for the current manifest is:

```text
48444a82d4edcb5bec0f1965faacdde18d9c17db3063d042abada2f705c9f54a  vendor/chart.js/chart.umd.min.js
```

## How To Verify The Action A Consuming Repo Runs

1. Prefer a full commit SHA in the consuming workflow:

```yaml
uses: reponomics/reponomics-dashboard-action@<40-character-commit-sha>
```

2. Inspect that exact source tree in GitHub at `https://github.com/reponomics/reponomics-dashboard-action/tree/<40-character-commit-sha>`.
3. Inspect `action.yml`, `vendor/chart.js/manifest.json`, and `dashboard_action/runtime/scripts/render_dashboard.py` at that same commit.
4. If the consuming workflow uses a tag instead of a commit SHA, resolve the tag to a commit and compare that commit against the source and CI results you intend to trust.

## What Is Not Yet Claimed

- No broad claim is made that tags are cryptographically immutable. Full commit SHA pinning remains the recommended consumer control.
- No claim is made that every commit or tag is signed by maintainer keys.
- No package-registry artifact is published for the action, so there is no registry-level package signature or registry-level provenance statement.
- No reproducible-build claim is made for the full runtime environment. The composite action installs Python dependencies from package metadata at runtime, and those dependency ranges are not currently locked by hash in a committed lockfile.
- No release attestation covers every dashboard artifact generated inside a user's consuming repository. Those artifacts are generated by the consuming repository's workflow run and inherit that repository's workflow identity, permissions, artifact retention, and ref pinning choices.
- No vulnerability scanner can prove absence of vulnerabilities. `pip-audit`, OSV, CodeQL, Dependabot, and Scorecard provide detection and posture signals based on their databases, rules, and execution times.
