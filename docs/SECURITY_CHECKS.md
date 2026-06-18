# Maintainer Security Checks

This maintainer document describes the security checks and public signals used for the Reponomics action source repository. The action handles sensitive repository metrics and encrypted artifacts, so the source repository combines source-tree CI gates, GitHub repository policy, and independently visible supply-chain signals.

## Security Signals

The repository uses several kinds of security evidence:

- GitHub-hosted signals: CodeQL, Dependabot, dependency graph, release settings, repository workflow policy, and artifact attestations.
- OpenSSF Scorecard: a third-party OpenSSF supply-chain posture signal that includes checks such as maintained status and pinned dependencies/actions.
- Open-source CI tools: `pip-audit`, OSV-Scanner, Syft-generated SBOMs through Anchore's SBOM action, and vendored-asset validation.
- Project-operated visibility: PolicyChecks badges for repository settings that GitHub enforces but does not expose through a simple public badge.

## GitHub Action SHA Pinning Policy

This source repository is part of the Reponomics Dashboard supply chain, so repository/organization policy requires third-party GitHub Actions to be pinned to full commit SHAs. The policy is the control; local workflow parsing is not the enforcement mechanism.

Public visibility for this posture comes from:

- OpenSSF Scorecard, which includes action pinning in its broader supply-chain checks.
- PolicyChecks, a Reponomics-maintained badge service that reports selected repository settings with proof JSON. The README links to PolicyChecks badges for SHA pinning and immutable releases as additional public evidence of the current app-visible repository settings.

PolicyChecks is intentionally narrow: it makes selected repository settings easier for reviewers to inspect. It is an additional public signal, not a replacement for the repository policy or for OpenSSF Scorecard.

Generated dashboard template repositories are different. They intentionally default to the compatible Reponomics action channel, such as `reponomics/reponomics-dashboard-action@v0`, through the local wrapper at `.github/actions/reponomics/action.yml`, so most users receive compatible bug fixes and security fixes without self-managing SHA updates. Users with stricter organization policy can pin that nested wrapper reference to an exact tag or SHA, but they then own the upgrade cadence.

## Vendored Assets

`scripts/validate_vendored_assets.py` verifies every `vendor/*/manifest.json` entry. For each vendored asset it checks:

- the local asset and license hashes;
- npm registry metadata for the recorded package version;
- the recorded tarball integrity value;
- OSV vulnerability results for the pinned package version;
- the source asset and license bytes inside the published tarball.

Run it locally with:

```bash
make validate-vendored-assets
```

Refresh vendored assets from their recorded upstream npm packages with:

```bash
make update-vendored-assets
```

The updater reads each manifest, resolves the package's current npm `latest` dist-tag unless an explicit `--version PACKAGE=VERSION` override is passed to `scripts/update_vendored_assets.py`, downloads the selected tarball, verifies its SRI value, replaces the vendored asset and license bytes, and rewrites the manifest hashes.

This check requires network access to the npm registry and OSV API.

CI runs this check through `.github/workflows/validate-vendored-assets.yml`, which is also called by the aggregate `.github/workflows/ci.yml` workflow. The workflow has a weekly scheduled run so newly disclosed OSV vulnerabilities can fail the badge even when the vendored file has not changed. `.github/workflows/update-vendored-assets.yml` runs the updater weekly and opens or refreshes a pull request when upstream vendored asset updates are available.

## Python Dependency Audit

`make security-audit` runs `pip-audit` against the local virtual environment with editable project packages skipped. The Makefile upgrades `pip` before installing the dev environment so the audit does not fail on a stale installer bundled with the runner.

Run it locally with:

```bash
make security-audit
```

CI runs this check through `.github/workflows/open-source-security.yml` on pull requests, pushes to `main`, a weekly schedule, and manual dispatch. This is intentionally separate from the GitHub-native Dependabot signal: Dependabot opens update PRs, while `pip-audit` gives an open-source dependency vulnerability gate for the resolved CI environment.

## Runtime Lock Audit

`make audit-runtime-lock` runs `pip-audit` against `requirements-runtime.txt`, the hash-pinned dependency set installed by the composite action in user workflows.

Run it locally with:

```bash
make audit-runtime-lock
```

CI runs this check through `.github/workflows/open-source-security.yml` alongside the installed-environment audit. Together, those checks keep the source/development dependency surface and the action runtime lock visible as separate audit claims.

## Runtime Dependency Lock

`requirements-runtime.txt` is the hash-pinned runtime dependency lock generated from `pyproject.toml` with `make lock-runtime`. The composite action installs this lock with `python -m pip install --require-hashes -r "$GITHUB_ACTION_PATH/requirements-runtime.txt"` before running the bundled runtime script, so the action no longer resolves third-party Python dependency ranges at runtime.

Run the lock validation locally with:

```bash
make validate-runtime-lock
```

CI runs this check through `.github/workflows/validate-runtime-lock.yml`, which is also called by the aggregate `.github/workflows/ci.yml` workflow. The check regenerates a temporary lock from `pyproject.toml`, compares it against the committed lock, and verifies that `pip` accepts the committed lock in hash-required mode.

## OSV SARIF Scan

`.github/workflows/osv-scanner.yml` runs OSV-Scanner on pushes to `main`, a weekly schedule, and manual dispatch. It inlines the scanner, reporter, artifact upload, and SARIF upload steps with full-SHA-pinned actions instead of importing OSV-Scanner's reusable workflow, so the repository's SHA-pinning policy applies to every executable third-party action in the workflow.

This complements the vendored-asset validator. The validator checks the recorded npm tarball assets and their pinned package versions directly; OSV-Scanner provides a repository-level SARIF signal for supported manifests and lockfiles.

## SBOM And Release Provenance

`.github/workflows/sbom-provenance.yml` generates an SPDX SBOM with Syft through Anchore's SBOM action and uploads it as a workflow artifact.

For published releases and manual runs, the workflow also creates a source archive, generates a matching SPDX SBOM, and uses GitHub artifact attestations for both provenance and SBOM attestation. The archive and SBOM are uploaded as workflow artifacts; the attestation records are available through GitHub's attestation surfaces.

The Anchore SBOM action's release-asset upload is disabled because this repository uses immutable GitHub Releases; release evidence is published through workflow artifacts and artifact attestations instead of mutating the release after publication.

The generated-template release artifact path follows the same rule. `template-release.yml` packages the generated template archive, canonical tree manifest, and `SHA256SUMS` as workflow artifacts and attests those files before creating the template-repository app token and force-pushing the generated template. It does not depend on mutating a source-repository template release after publication; the public template release is created in the generated template repository after the generated commit is verified.

The Anchore SBOM action's dependency snapshot upload is also disabled. GitHub's Dependency Submission API requires `contents: write`, and this repository prefers to keep the third-party SBOM action's job token read-only. Dependency visibility is covered separately by GitHub's native dependency graph/Dependabot behavior, `pip-audit`, OSV-Scanner, the runtime lock validator, and the vendored-asset validator.

This repository is a composite action consumed by Git ref, not a package pushed to a package registry. The release attestation therefore covers the source archive produced from the release checkout rather than a registry package.

## Version Status

Generated dashboards expose compact local action version status rather than host-authored update prose. During publish, the action performs an unauthenticated GitHub Releases lookup for the latest stable SemVer tag and renders current runtime version, latest version, update availability, and a link to local managed docs when present or the release page otherwise. The caller token is not sent with this request. If the API check fails, publish continues and the generated output falls back to the local current version plus the generic releases page. Remote release bodies, Markdown, summaries, and HTML are not rendered into user repositories.
