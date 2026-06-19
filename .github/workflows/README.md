# Workflow Inventory

This directory contains the repository's CI, release, dependency, and supply-chain workflows. The summaries below explain why each workflow exists; the workflow YAML remains the source of truth for exact triggers, permissions, pinned action refs, and command lines.

## Workflows

- [`ci.yml`](ci.yml) is the aggregate pull request and main-branch quality gate. It calls the reusable validation workflows, runs linting, type checking, action/workflow parsing, tests across supported Python versions, and uploads coverage as a short-lived artifact.

- [`open-source-security.yml`](open-source-security.yml) runs `pip-audit` against the resolved Python environment and the hash-pinned runtime dependency lock. It provides an independent open-source dependency vulnerability signal rather than relying only on GitHub-native Dependabot or CodeQL surfaces.

- [`osv-scanner.yml`](osv-scanner.yml) runs OSV-Scanner recursively and uploads SARIF to GitHub code scanning. The workflow inlines the scanner, reporter, artifact upload, and SARIF upload steps so this repository's full-SHA action-pinning policy applies to every imported action.

- [`release-please.yml`](release-please.yml) creates or updates Release Please PRs and publishes GitHub Releases when a release PR is merged. It manages the root Marketplace action release, keeps bare `v*` release tags and floating major/minor action tags for action consumers, then opens or updates a template acceptance PR when an action release is published. That PR records the released action version, tag, SHA, and default compatible ref in `template-contract.yml`; merging it is the maintainer approval for the corresponding template release.

- [`template-release.yml`](template-release.yml) publishes generated template releases from merged template acceptance or template-only release PRs. It runs only after `template-contract.yml` changes on `main`, making the contract bump the release approval boundary for both action-coupled and template-only releases. It uses a target-scoped concurrency group for `reponomics-dashboard`, runs `make template-release-gates`, verifies existing generated releases instead of blindly skipping them, uploads and attests deterministic template release artifacts, creates an immutable source tag, appends a generated publication commit to `reponomics-dashboard`, creates or verifies the generated release tag, and creates the public `reponomics-dashboard-v*` GitHub Release in the generated template repository with `--verify-tag`.

- [`prepare-template-release.yml`](prepare-template-release.yml) is the manual template-only release preparation workflow. It bumps `template-contract.yml` by patch, minor, or major SemVer, creates or updates an `automation/template-release-*` branch, and opens a release-prep PR whose merge triggers [`template-release.yml`](template-release.yml).

- There is no manual production `publish-template.yml` workflow. Production generated-template publication is intentionally centralized in [`template-release.yml`](template-release.yml); operator repair should be explicit and separate from routine release automation.

- [`publish-template-staging.yml`](publish-template-staging.yml) builds the generated dashboard template from this repository and publishes it to the private `reponomics-dashboard-staging` repository. This staging effort is currently paused and is not a live release gate; the workflow, helper scripts, and skipped smoke tests remain as orphaned work until the protocol is revisited with a lighter contract model. The paused consumer-repository smoke protocol is documented in [`../../docs/STAGING_SMOKE.md`](../../docs/STAGING_SMOKE.md).

- [`publish-demo.yml`](publish-demo.yml) builds the generated public demo repository and publishes it to `reponomics-dashboard-demo`. It supports manual publication and scheduled daily refresh. Scheduled refresh uses an approved source ref, imports the encrypted synthetic data seed into the demo repository's Actions artifact storage, and deploys the committed Pages dashboard shell without requiring daily human approval.

- [`pre-release-validation.yml`](pre-release-validation.yml) is a manual, non-publishing validation pass for candidate refs. It builds the template from the candidate source, runs template smoke checks, runs generated-template consumer e2e against the same candidate action runtime, dry-runs template publication, and uploads the generated template for inspection.

- [`sbom-provenance.yml`](sbom-provenance.yml) generates a repository SPDX SBOM and creates release source/SBOM attestations for release and manual runs. Release asset upload is explicitly disabled because immutable releases cannot be mutated after publication, and dependency snapshot upload is disabled so the third-party SBOM action runs with a read-only job token.

- [`scorecard.yml`](scorecard.yml) runs OpenSSF Scorecard and publishes SARIF/results for supply-chain posture visibility. It also supports the public Scorecard badge and keeps checks such as Maintained refreshed on a schedule.

- [`semantic-pr.yml`](semantic-pr.yml) validates pull request titles against the conventional-commit types used by Release Please. It runs through `pull_request_target` with read-only pull request permission and skips draft PRs.

- [`update-vendored-assets.yml`](update-vendored-assets.yml) periodically refreshes vendored browser assets from their recorded upstream npm packages, validates the refreshed files and manifests, and opens or updates a pull request when the vendored assets change.

- [`validate-runtime-lock.yml`](validate-runtime-lock.yml) verifies that `requirements-runtime.txt` remains synchronized with `pyproject.toml` and is accepted by `pip` in hash-required mode. This protects the composite action's runtime dependency installation from unpinned resolution at execution time.

- [`validate-vendored-assets.yml`](validate-vendored-assets.yml) verifies vendored browser asset manifests, local hashes, upstream npm tarball integrity, license bytes, and OSV status for pinned package versions. It runs independently and through `ci.yml` so vendored asset provenance has both PR and scheduled coverage.

## Conventions

Imported third-party actions in this source repository should be pinned by full commit SHA with a nearby version comment for maintainability. Repository/organization policy is the control; OpenSSF Scorecard and PolicyChecks provide public visibility into that posture. Workflows should keep workflow-level permissions minimal and grant write permissions only at the job level that needs them.

Where a workflow exists partly to support a public badge or external security signal, keep the executable workflow small and put longer rationale in repository documentation such as [`../../docs/SECURITY_CHECKS.md`](../../docs/SECURITY_CHECKS.md) or [`../../docs/PROVENANCE.md`](../../docs/PROVENANCE.md).
