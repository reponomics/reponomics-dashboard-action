---
name: PROVENANCE.md
description: Describe the various ways in which distribution assets and repository artifacts can be verified and supply chain/provenance guarantees can be established.
created: 2026-05-26
modified: 2026-05-26
---

# Provenance

This document summarizes what this repository can currently assert about source authenticity, vendored asset provenance, release materials, generated artifacts, and integrity checks. It is intentionally conservative: a claim belongs here only if it is backed by repository files, CI, GitHub metadata, or a command a user can run.

This is not meant to be the normal setup guide. Most users should follow the README and may reasonably use the moving major-version ref recommended there once the project has a stable release line. This document is for users, researchers, maintainers, or reviewers who want to inspect the higher-assurance evidence behind the project's privacy and supply-chain posture. Full commit SHA pinning is the highest-assurance consumer-side control, but it is not presented here as the only acceptable way for ordinary users to run the action.

## Short Version

- The highest-assurance way to consume the action is by full commit SHA: `uses: reponomics/reponomics-dashboard-action@<40-character-commit-sha>`. With a full SHA, the action code GitHub runs is the repository tree at that immutable commit. Major-version refs are more convenient for normal users, but they trade some strict pinning assurance for easier updates.
- Chart.js and dashboard fonts are vendored, not loaded from CDNs. The current manifests record exact npm package versions, tarball URLs, tarball integrity values, upstream source paths, local paths, local SHA-256 digests, license paths, and license SHA-256 digests.
- Runtime Python dependencies are installed from the committed `requirements-runtime.txt` file in hash-required mode. The lock fixes the third-party Python package set used by the composite action, while CI checks that the lock remains current with `pyproject.toml`.
- `make validate-vendored-assets` verifies that the vendored browser asset bytes and license bytes match the recorded npm package tarballs, verifies each tarball SRI value against the downloaded tarball, confirms the registry still reports the recorded tarball and integrity metadata for each pinned package version, and checks OSV for known vulnerabilities in each pinned package version.
- Published dashboard HTML loads Chart.js from `assets/chart.umd.min.js` in the same generated artifact, and the renderer copies that file from `vendor/chart.js/chart.umd.min.js`. The supported path is not a remote script and not a CDN.
- Repository CI validates workflow/action SHA pins, vendored assets, tests, type checks, Python dependency audit, OSV SARIF scanning, Scorecard, and CodeQL. The dashboard renderer also emits a strict CSP with hashes for first-party inline code. These are hardening and detection controls; they are not a substitute for pinning the action by commit SHA.
- GitHub immutable releases are enabled for releases. Use `gh release view TAG --json isImmutable,targetCommitish,url` to inspect the current immutability and target commit evidence for a specific release.
- The SBOM/provenance workflow generates SPDX SBOMs and GitHub artifact attestations for release source archives. Because this is a composite action consumed by Git ref rather than a package registry artifact, the release attestation covers the source archive produced from the release checkout, not a registry package.

## What Can Be Asserted

### Source Identity For Consumers

- This repository distributes a composite GitHub Action. A consuming workflow that uses `reponomics/reponomics-dashboard-action@REF` causes GitHub Actions to fetch this repository at `REF` and run `action.yml` from that checkout.
- If `REF` is a full 40-character commit SHA, the consumed source tree is fixed by Git object identity. A user can inspect the exact source at `https://github.com/reponomics/reponomics-dashboard-action/tree/<commit-sha>`.
- If `REF` is a tag such as `v0.11.0` or `v0.11`, the user can inspect which commit the tag currently resolves to, but a tag is a weaker reference than a full commit SHA unless repository policy and GitHub protections are relied on. Major-version refs may be the practical recommendation for most users because they receive fixes and features automatically; full commit SHA pinning is the high-assurance option for users who prefer explicit update review.
- The action itself uses full-SHA pins for imported GitHub Actions in `action.yml`, and `scripts/validate_action_pins.py` enforces that policy for `action.yml` and `.github` workflow files.

### Vendored Browser Assets

- Each vendored browser asset has a manifest under `vendor/*/manifest.json`. The manifest identifies the npm package, exact version, registry, tarball URL, npm tarball integrity value, upstream path inside the tarball, local vendored path, local SHA-256 hash, license source path, local license path, and license SHA-256 hash.
- Current vendored browser assets include Chart.js, Inter, and JetBrains Mono. Their exact package versions, upstream paths, local paths, tarball integrity values, file SHA-256 values, and license SHA-256 values are recorded in the corresponding `vendor/*/manifest.json` files.
- `scripts/validate_vendored_assets.py` proves byte identity against the published npm tarball at validation time. It does not merely trust the local hash; it downloads the recorded package tarball, verifies the tarball integrity, extracts the recorded upstream file, hashes it, and compares that hash to the local manifest and local file.
- `.github/workflows/validate-vendored-assets.yml` runs the vendored asset validator on pushes to `main`, on a weekly schedule, manually, and through the aggregate CI workflow. A passing run is evidence that the committed vendored asset still matches its recorded upstream package artifact and has no known OSV vulnerability at that package version at the time of the run. `.github/workflows/update-vendored-assets.yml` runs `make update-vendored-assets` weekly and opens or refreshes a pull request when upstream npm package updates are available for vendored browser assets.

### Dashboard Asset Inclusion

- The dashboard renderer defines `VENDORED_CHART_JS_PATH = ACTION_ROOT / "vendor" / "chart.js" / "chart.umd.min.js"` and publishes `assets/chart.umd.min.js` by copying that vendored file.
- The dashboard renderer embeds vendored Inter and JetBrains Mono font bytes as `data:` URLs in generated CSS. Those font bytes are covered by the same vendored asset manifests and validation workflow.
- The generated Pages dashboard references `<script src="assets/chart.umd.min.js"></script>`, so the published dashboard uses the same-origin asset copied from the action checkout, not a remote network script.
- The dashboard renderer emits a CSP meta tag with hash-based allowances for generated first-party inline scripts and CSS. This protects against accidental reintroduction of broad inline script/style allowances, but it is not itself a provenance proof for upstream dependencies.
- Encrypted browser-local CSV export uses a generated manifest and digest checks before download: the runtime verifies encrypted asset metadata and decrypted bundle digests so the browser detects mismatched or corrupted export assets before handing the plaintext ZIP to the user.
- Standalone local dashboard output may inline Chart.js for local development convenience, but it is not the supported offline/mobile distribution path. The supported convenience path is downloading the workflow artifact and serving the extracted dashboard over local HTTP when needed.

### Release Materials

- GitHub immutable releases are configured. A current release can be checked with `gh release view TAG --repo reponomics/reponomics-dashboard-action --json isImmutable,targetCommitish,url`.
- GitHub release attestations can be checked with `gh release verify TAG --repo reponomics/reponomics-dashboard-action --format json`. The verification output includes the package URL, attested subject, and digest information for the release being checked.
- `.github/workflows/sbom-provenance.yml` generates an SPDX JSON SBOM with Anchore's SBOM action and submits dependency information to GitHub's dependency graph.
- For published releases and manual runs, the same workflow creates a `git archive` source tarball from the release checkout, generates a matching SPDX SBOM, and uses GitHub artifact attestations for both the source archive and the SBOM.
- These attestations establish GitHub-hosted provenance for the generated release source archive and SBOM. They do not change how GitHub Actions consumes this repository as a composite action; consumers still get the source tree for the ref they use.

### GitHub Actions Supply Chain

- Imported GitHub Actions in `action.yml` and repository workflows are pinned by full commit SHA. This reduces the risk that an upstream tag move changes what CI or the composite wrapper runs.
- `scripts/validate_action_pins.py` enforces this in CI and can be run locally with `make validate-action-pins`.
- Current composite-action imports include pinned `actions/setup-python`, `actions/configure-pages`, `actions/upload-pages-artifact`, `actions/deploy-pages`, and `actions/upload-artifact`.
- The composite action installs runtime Python dependencies from `requirements-runtime.txt` with `pip --require-hashes` before executing `dashboard_action/run.py`. `make validate-runtime-lock` regenerates a temporary lock from `pyproject.toml`, compares it against the committed lock, and verifies that `pip` accepts the committed lock in hash-required mode.

### Vulnerability And Supply-Chain Signals

- `pip-audit` audits the resolved local Python environment used by the repository checks. This is a vulnerability signal for resolved Python dependencies, not a cryptographic provenance claim.
- OSV-Scanner uploads SARIF for repository-level dependency vulnerability scanning.
- CodeQL, Scorecard, Dependabot, branch/repository settings, and action SHA pin validation provide additional hardening signals. They should be read as layered controls, not as proof that every future dependency resolution is identical.

## How To Verify Vendored Browser Assets

1. Inspect the relevant `vendor/*/manifest.json` file in the exact commit you plan to consume.
2. Check local hashes in that commit:

```bash
shasum -a 256 vendor/chart.js/chart.umd.min.js
shasum -a 256 vendor/inter/inter-latin-wght-normal.woff2
shasum -a 256 vendor/jetbrains-mono/jetbrains-mono-latin-wght-normal.woff2
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

The expected digests are the `sha256` values in the corresponding manifest files at the commit or tag being evaluated. This document intentionally does not duplicate those values so the manifest remains the single source of truth.

## How To Verify The Action A Consuming Repo Runs

1. For the highest-assurance posture, use a full commit SHA in the consuming workflow:

```yaml
uses: reponomics/reponomics-dashboard-action@<40-character-commit-sha>
```

2. Inspect that exact source tree in GitHub at `https://github.com/reponomics/reponomics-dashboard-action/tree/<40-character-commit-sha>`.
3. Inspect `action.yml`, `vendor/chart.js/manifest.json`, and `dashboard_action/runtime/scripts/render_dashboard.py` at that same commit.
4. If the consuming workflow uses a tag instead of a commit SHA, resolve the tag to a commit and compare that commit against the source and CI results you intend to trust.

## How To Verify A Release

1. Check whether the release is immutable and what commit it targets:

```bash
gh release view TAG --repo reponomics/reponomics-dashboard-action --json isImmutable,targetCommitish,url
```

2. Verify GitHub's release attestation:

```bash
gh release verify TAG --repo reponomics/reponomics-dashboard-action --format json
```

3. Compare the attested digest or `targetCommitish` to the commit SHA used in a consuming workflow. If those do not match, the release evidence and the consumed action source are not evidence for the same tree.

## Verification Limitations

Because this is a publicly available GitHub action and part of the security and verification assurances depend on how a user who consumes this action, either through the Reponomics Dashboard template repository, or in some other way, decides to configure their own repository, this section discusses some of the things that can still be improved upon at the project-level, things that depend on a user's own choices, and general limits of security tooling.

### Project-Controlled Claims Not Currently Made

- No claim is made that every commit is signed by maintainer keys.
- No package-registry artifact is published for the action, so there is no registry-level package signature or registry-level provenance statement.
- No reproducible-build claim is made for the full runtime environment. Runtime Python dependencies are hash-locked, but the complete runner, operating system, Python interpreter, GitHub Actions platform, and user-repository workflow context are not reproduced from a single hermetic build recipe.

### Consumer-Controlled Assurances

- GitHub immutable releases and release attestations strengthen release-level evidence, but the source actually run by GitHub Actions is determined by the ref in the consuming workflow. Full commit SHA pinning is the highest-assurance consumer control; major-version refs trade some strict pinning assurance for automatic compatible fixes and feature updates, and this may be preferable for many users, depending on their priorities and security posture. We try to accommodate users with a variety of preferences and here we simply document the tradeoffs so that they can make an informed decision.
- The project can provide pinned workflow examples and recommend full-SHA consumption, but it cannot claim that every consuming repository uses those examples unchanged.
- No release attestation from this repository covers every dashboard artifact generated inside a user's consuming repository. Those artifacts are generated by the consuming repository's workflow run and inherit that repository's workflow identity, permissions, artifact retention, branch protections, secrets handling, and action-ref pinning choices.

### Tooling Limits

- No vulnerability scanner can prove absence of vulnerabilities. `pip-audit`, OSV, CodeQL, Dependabot, and Scorecard provide detection and posture signals based on their databases, rules, and execution times.
