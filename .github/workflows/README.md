# Workflow Inventory

This directory contains the repository's CI, release, dependency, and supply-chain workflows. The summaries below explain why each workflow exists; the workflow YAML remains the source of truth for exact triggers, permissions, pinned action refs, and command lines.

## Workflows

- [`ci.yml`](ci.yml) is the aggregate pull request and main-branch quality gate. It calls the reusable validation workflows, validates release-notice fixtures, runs linting, type checking, action/workflow parsing, tests across supported Python versions, and uploads coverage as a short-lived artifact.

- [`open-source-security.yml`](open-source-security.yml) runs `pip-audit` against the resolved Python environment. It provides an independent open-source dependency vulnerability signal rather than relying only on GitHub-native Dependabot or CodeQL surfaces.

- [`osv-scanner.yml`](osv-scanner.yml) runs OSV-Scanner recursively and uploads SARIF to GitHub code scanning. The workflow inlines the scanner, reporter, artifact upload, and SARIF upload steps so this repository's full-SHA action-pinning policy applies to every imported action.

- [`release-please.yml`](release-please.yml) creates or updates Release Please PRs and publishes GitHub Releases when a release PR is merged. It uses the release app token so release-created events can trigger downstream automation, and it moves the floating major/minor action tags after a release is created.

- [`sbom-provenance.yml`](sbom-provenance.yml) generates a repository SPDX SBOM and creates release source/SBOM attestations for release and manual runs. Release asset upload is explicitly disabled because immutable releases cannot be mutated after publication, and dependency snapshot upload is disabled so the third-party SBOM action runs with a read-only job token.

- [`scorecard.yml`](scorecard.yml) runs OpenSSF Scorecard and publishes SARIF/results for supply-chain posture visibility. It also supports the public Scorecard badge and keeps checks such as Maintained refreshed on a schedule.

- [`semantic-pr.yml`](semantic-pr.yml) validates pull request titles against the conventional-commit types used by Release Please. It runs through `pull_request_target` with read-only pull request permission and skips draft PRs.

- [`update-vendored-assets.yml`](update-vendored-assets.yml) periodically refreshes vendored browser assets from their recorded upstream npm packages, validates the refreshed files and manifests, and opens or updates a pull request when the vendored assets change.

- [`validate-action-pins.yml`](validate-action-pins.yml) verifies that imported GitHub Actions in `action.yml` and repository workflow files are pinned to full commit SHAs, and rejects third-party reusable workflows that would hide unpinned transitive action use. It is both a standalone check and a reusable workflow called by `ci.yml`.

- [`validate-runtime-lock.yml`](validate-runtime-lock.yml) verifies that `requirements-runtime.txt` remains synchronized with `pyproject.toml` and is accepted by `pip` in hash-required mode. This protects the composite action's runtime dependency installation from unpinned resolution at execution time.

- [`validate-vendored-assets.yml`](validate-vendored-assets.yml) verifies vendored browser asset manifests, local hashes, upstream npm tarball integrity, license bytes, and OSV status for pinned package versions. It runs independently and through `ci.yml` so vendored asset provenance has both PR and scheduled coverage.

## Conventions

Imported actions should be pinned by full commit SHA with a nearby version comment for maintainability. Workflows should keep workflow-level permissions minimal and grant write permissions only at the job level that needs them.

Where a workflow exists partly to support a public badge or external security signal, keep the executable workflow small and put longer rationale in repository documentation such as [`../../docs/SECURITY_CHECKS.md`](../../docs/SECURITY_CHECKS.md) or [`../../docs/PROVENANCE.md`](../../docs/PROVENANCE.md).
