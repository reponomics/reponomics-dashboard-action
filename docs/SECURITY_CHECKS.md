# Maintainer Security Checks

This repository ships a composite GitHub Action that handles sensitive repository metrics and encrypted artifacts. The checks below are intentionally enforced in CI, not only through local pre-commit hooks or repository settings, so pull requests expose a visible security signal and the README can display a badge.

## Tooling Posture

The repository uses both GitHub-native security automation and separately auditable open-source tools. CodeQL is best treated as a hybrid signal: the standard CodeQL libraries and queries are open source, while the CodeQL CLI/engine is separately licensed. Dependabot Core is open source, but hosted Dependabot is GitHub platform automation.

For OpenSSF-style evidence of independent open-source security tooling, this repository therefore does not rely only on CodeQL, Dependabot, or Scorecard. The additional open-source checks are `pip-audit`, OSV-Scanner, Syft-generated SBOMs through Anchore's SBOM action, vendored-asset validation, and the local action-pin validator.

## GitHub Action SHA Pins

`scripts/validate_action_pins.py` scans `action.yml` and `.github` workflow YAML for imported GitHub Actions. Third-party `uses:` references must be pinned to a full 40-character lowercase commit SHA. Local actions and Docker image references are not checked by this script. Third-party remote reusable workflows are rejected even when the reusable workflow reference itself is SHA-pinned, because their internal `uses:` entries are outside this repository's local workflow YAML and can violate the repository's action policy at workflow startup. Reusable workflows owned by the `reponomics` organization are allowed when SHA-pinned.

CI runs this check through `.github/workflows/validate-action-pins.yml`, which is also called by the aggregate `.github/workflows/ci.yml` workflow.

Run it locally with:

```bash
make validate-action-pins
```

GitHub repository settings also enforce SHA-pinned actions, and the settings are configured according to an explicit allowlist. The script keeps local workflow changes auditable from code review and from the `CI` workflow result. A separate live repository-settings check may be added later for the public badge claim that the GitHub action policy itself has `selected` actions and SHA pinning enabled.

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

CI runs this check through `.github/workflows/open-source-security.yml` on pull requests, pushes to `main`, a weekly schedule, and manual dispatch. This is intentionally separate from the GitHub-native Dependabot signal: Dependabot opens update PRs, while `pip-audit` gives an open-source dependency vulnerability gate on the resolved CI environment.

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

`.github/workflows/sbom-provenance.yml` generates an SPDX SBOM with Syft through Anchore's SBOM action and submits it to GitHub's dependency graph through the dependency submission API.

For published releases and manual runs, the workflow also creates a source archive, generates a matching SPDX SBOM, and uses GitHub artifact attestations for both provenance and SBOM attestation. The archive and SBOM are uploaded as workflow artifacts; the attestation records are available through GitHub's attestation surfaces.

The Anchore SBOM action's release-asset upload is disabled because this repository uses immutable GitHub Releases; release evidence is published through workflow artifacts and artifact attestations instead of mutating the release after publication.

This repository is a composite action consumed by Git ref, not a package pushed to a package registry. The release attestation therefore covers the source archive produced from the release checkout rather than a registry package.

## Release Notice Blocks

`scripts/validate_release_notice.py` validates the constrained `<!-- reponomics-update {...} -->` block used in release notes. The dashboard runtime parses this JSON metadata to show compatible upgrade notices to users of pinned action versions. It does not render arbitrary remote release Markdown. The purpose of this is to enable end users (owners of repos created from the `reponomics-dashboard` template) to use a strict, full-SHA-pinned version of this action, while also providing a channel to stay informed of product updates without having to manually track our releases.

The supported schema and an example block are documented in `README.md#maintainer-release-policy`.

Run the CLI against a release-note Markdown file with:

```bash
venv/bin/python scripts/validate_release_notice.py path/to/release-notes.md
```

Run the release-notice fixture tests with:

```bash
make validate-release-notice
```
