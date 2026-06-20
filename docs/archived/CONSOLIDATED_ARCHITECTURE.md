# Repository Architecture

## Overview

The Reponomics Dashboard project publishes two independently versioned products that are tightly coupled, one public demo surface, and one promotional splash page. The core pieces consist of:

- `reponomics-dashboard`: the primary user-facing offering - a template repository that provides the basic scaffolding to support the Dashboard - its main functional surface is the set of workflows that consume the Dashboard Action; it also houses important repo owner documentation, and the owner's configuration files.
- `reponomics-dashboard-action`: the GitHub Marketplace action that implements the runtime for the core Dashboard feature offerings.
- `reponomics-dashboard-demo`: a public demo repository that uses synthetic data to show prospective Dashboard repo owners the set of features that the Reponomics Dashboard has to offer.
- `reponomics-dashboard-web`: a promotional splash page that gives a public presence to the Dashboard project outside of GitHub - it presents an overview of the project and highlights the core functionality.

The `@reponomics/reponomics-dashboard-action` repository is the development repository responsible for maintaing the template repo, the GitHub action, and the demo repo. It is also the repository that Dashboard owners, project contributors, and potential collaborators are invited to use to file issues (feature enhancements, bug reports), make PRs, and review more detailed technical literature. Because it is part of the supply chain for the other products, it strives to follow Open Source best practices to the greatest extent, and produces the necessary provenance artifacts, attestations, immutable releases, and other outputs necessary for the project to establish publicly verifiable evidence regarding the claims that are made about the project.

The dashboard-action repo is also the repo that is referenced by workflows that consume the action:

```yaml
uses: reponomics/reponomics-dashboard-action@v0
```

The reason for this bifurcated design (template + action) is due to the goal of providing maintainers with a data dashboard that is completely under their control, and at the same time offering feature updates, security patches, and bug fixes. Since the product is a data dashboard repo, a template repo is a natural way to package it. However, after copying a template, the repo owner has virtually no connection to that template. (The template repo is not "upstream" of its copies.) So, the template needs some sort of distribution channel. Since the majority of the functionality comes from the workflows (querying the GitHub API, collecting and storing the data, etc.), it is the _action_ that is the primary functional core, or "runtime", for the Reponomics Dashboard, and the template repo is supposed to be only a thin compatibility layer.

> [!NOTE] Maintainers who copy the Dashboard template should be referred to as "owners" when speaking in that mode, although they may also be referred to as "users" of the Dashboard action. "Consumer" is the most generic label, if one is needed, although this also applies to the workflows themselves. This is only stylistic advice.

## Compatibility

The architecture must always be designed with this constraint in mind: after copying the template, that copy owner might never update, or migrate, their data to a newer template version. Therefore, the action must _always_ be able to prove that as it evolves, it maintains compatibility with the minimum compatible template version. Breaking this contract is what decides whether a new major version of the action is justified, or required.

The project follows an asymmetric compatibility rule:

- New action releases on the same major version line must continue to work with previously published template versions.
- New template releases, however, may assume that any user who copies it will be using the action version that is current at the time of its publication, or later.

So, action releases must establish backwards-compatibility with the template version stated as the `minimum_compatible_template_version` in the `template-contract`; template releases do not have to take into account backwards compatibility at all.

## Repository Topology

The core directory structure is as follows:

```
├── .github/              # Workflows for CI/CD and release management
├── action.yml            # GitHub action metadata file
├── dashboard_action/     # Central runtime implementation
│   ├── run_modules/      # Core module files and facades
│   └── runtime/
│       └── managed-docs/ # Documentation that is shipped to Dashboard owners
│       └── scripts/      # Large collection of implementation scripts and shared logic
├── docs/                 # Maintainer documentation (live docs, ADRs)
├── scripts/              # Shared scripts/helpers
├── template/             # A sub-tree that is mostly isomorphic with the generated template repo
├── tests/                # Collected tests for both products
└── vendor/               # Vendored assets (chart.js, fonts)
```

The major areas of responsibility are:

| Area                                                                       | Responsibility                                                                                                                                                 |
| -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `action.yml`                                                               | Public composite action interface. This is the Marketplace product entry point.                                                                                |
| `dashboard_action/`                                                        | Action runtime package, mode dispatch, collection, publish, doctor, incident reset, managed docs sync, provenance, and rendering.                              |
| `dashboard_action/runtime/managed_docs/`                                   | Source bundle for user-facing managed documentation that ships into generated repositories and can be refreshed by the action.                                 |
| `template/`                                                                | Hand-maintained source for files that belong in the generated dashboard template repository.                                                                   |
| `template-manifest.yml`                                                    | Explicit shipped-file allowlist plus forbidden-path guard for generated template output.                                                                       |
| `template-contract.yml`                                                    | Template product metadata and action compatibility contract.                                                                                                   |
| `scripts/build_template.py`                                                | Builds `dist/template` from `template/`, overlays managed docs, and verifies output.                                                                           |
| `scripts/template_contract.py`                                             | Validates local action/template compatibility, managed docs snapshots, and action references in generated output.                                              |
| `scripts/publish_generated_repo.py`                                        | Publishes a generated output tree to `reponomics-dashboard` with target safety checks.                                                                         |
| `scripts/template_consumer_e2e.py` and `scripts/smoke_template_release.py` | Local generated-template validation against the current action source.                                                                                         |
| Demo tooling                                                               | Builds and publishes `reponomics-dashboard-demo` from the generated template plus explicit synthetic data, demo fixtures, and demo-only publication overrides. |
| `tests/`                                                                   | Action runtime tests, generated-template tests, scenario snapshots, security/contract checks, and compatibility fixtures.                                      |
| `.github/workflows/`                                                       | CI, release, template publish, pre-release validation, and repository hygiene workflows.                                                                       |
| `docs/`                                                                    | Maintainer documentation for this development repository.                                                                                                      |

## Product Boundaries

### Action Product

The action product consists of:

- `action.yml`
- `dashboard_action/`
- runtime dependencies and locks
- bundled runtime assets
- bundled managed docs
- Marketplace-facing README and release notes
- action release tags
- floating action tags (major and minor lines)

### Template Product

The template product consists of the generated output published to `reponomics/reponomics-dashboard`. Its source inputs are:

- `template/`
- `template-manifest.yml`
- `template-contract.yml`
- template-generator scripts
- `dashboard_action/runtime/managed_docs/`
- action metadata required by generated workflows
- template publication workflows

### Generated Template Repository

Publication should be a reproducible projection from this repository:

```text
source tree at commit S
  -> make build-template
  -> dist/template
  -> publish_generated_repo.py
  -> reponomics-dashboard main
```

### Demo Repository

Because the template repository has nothing very interesting to show when it is first copied, the demo repository is maintained as a faithful replica of the current template, seeded with synthetic data. It is intended to deviate from the genuine template to the smallest extent possible - the synthetic data is encrypted according to the same protocols, with the minor difference that the unlock key is printed directly to the unlock screen (normal templates don't expost this, for obvious reasons).

- use the same repository layout as a real generated template repository
- use the same repository layout, rendering paths, encrypted artifact format, Pages publication path, and managed docs surface wherever possible
- replace live GitHub collection with deterministic synthetic canonical data for a manicured portfolio of repositories
- publish a README dashboard even though normal public generated repositories prohibit README dashboard generation
- publish a Pages dashboard, which is normal and supported
- use encrypted dashboard mode with an intentionally public demo key so visitors can unlock the Pages dashboard
- label the public demo key unmistakably as a demo credential that must never be reused

The demo repository should be treated as a public showroom and, to some degree, a secondary integration test surface, not as a third semantically versioned product. It is regenerated every day so that the synthetic data can be advanced in time by one day, giving the impression that it is always "up to date".

## Development Tooling

The Makefile should remain the primary local interface. That keeps local development, CI, and release workflows speaking the same commands.

Recommended command groups:

- `make lint`, `make type-check`, `make test`: normal action/runtime quality gates.
- `make validate`: action metadata, workflow syntax, runtime lock, vendored asset checks, and any source-repo security posture checks that remain local.
- `make build-template`: generate and verify `dist/template`.
- `make verify-template`: regenerate `dist/template` and verify it against the source contract.
- `make template-smoke`: check generated workflow and publication shape.
- `make template-consumer-e2e`: run generated template consumers against the local action source.
- `make publish-template-dry-run`: verify the publication target without pushing.
- `make publish-template`: operator-only push to the generated template repo.
- Demo commands mirror the same pattern: build the demo from generated template output, materialize synthetic canonical data, render public README and encrypted Pages outputs, verify no output drift, dry-run publication, and then publish to `reponomics-dashboard-demo`.

Python development should continue to use `venv/` and Python 3.11 as the release workflow baseline, while CI also checks newer supported Python versions for runtime compatibility. Source-repository GitHub Actions should remain full-SHA pinned or covered by repository policy checks, with top-level workflow permissions read-only or empty and write permissions scoped to the specific job that needs them. Generated user repositories intentionally default to the compatible Reponomics action channel rather than full-SHA pinning.

The template generator should keep refusing unsafe output paths inside the source tree outside `dist/`. That is more important after consolidation, because the template source and generated output now live in the same checkout.

## Testing Model

The testing model should prove three things:

1. The action runtime works.
2. The generated template is clean and complete.
3. The current action source works when invoked by the generated template.

Current and recommended layers:

| Layer                  | Purpose                                                                                                                                                                                                                                 |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unit tests             | Runtime modes, GitHub API handling, artifact lineage, crypto, config parsing, render helpers, managed docs sync.                                                                                                                        |
| Generated-repo tests   | Verify manifest behavior, forbidden paths, generated workflows, managed docs snapshots, action references, and publication safety.                                                                                                      |
| Scenario snapshots     | Hold dashboard output stable across representative data shapes.                                                                                                                                                                         |
| Template smoke         | Exercise generated template workflow shape and release/publish assumptions cheaply.                                                                                                                                                     |
| Template consumer e2e  | Build a generated template and run it against the local action source, closing the old action-repo-to-dashboard-dev gap.                                                                                                                |
| Demo build/verify      | Build a public demo repository from the generated template, materialize curated synthetic repository data, render README and Pages outputs, verify retained data is not committed, verify demo provenance, and check publication drift. |
| Compatibility fixtures | Future requirement: preserve old published template contracts and run new action versions against them.                                                                                                                                 |

The largest remaining architectural testing gap is historical compatibility. Before public release, create at least one fixture representing the first published template surface. After each template release, retain a minimal fixture that captures:

- generated workflow files
- `config.yaml` shape
- managed docs manifest schema
- relevant action refs and action inputs
- representative user setup state

Then CI can test the current action against previous template fixtures. That is the practical enforcement mechanism for "old templates must keep working."

## CI/CD Shape

### CI

Normal CI should remain split into jobs with different purposes:

- Python matrix job for lint, typing, metadata validation, workflow syntax, and full tests.
- Dedicated template job for workflow classification, template smoke, template consumer e2e, and template publication dry-run.
- Demo publication workflow for generated demo build/verify, demo publication dry-run, generated repository force-push, artifact seed import, and Pages deployment.
- Scenario snapshot job for dashboard rendering stability.
- Security and supply-chain jobs for source-repository action pinning or policy verification, runtime lock, vendored assets, OSV, Scorecard, and SBOM/provenance generation.

This is the right direction. The template job is the key addition made possible by consolidation: it validates action changes with the generated template before either product ships.

### Pre-release Validation

`.github/workflows/pre-release-validation.yml` should validate a candidate ref without publishing:

- action metadata and source-repository workflow policy
- generated template build
- generated template smoke checks
- template consumer e2e against the same candidate action source
- template publication dry-run
- generated template artifact upload for inspection

This should be run before action releases that affect runtime behavior used by templates, and before every template release.

`.github/workflows/publish-template-staging.yml` is the persistent private generated-template staging surface. It publishes generated output to `reponomics-dashboard-staging` after running generated-template gates. Use it when maintainers need to inspect a candidate generated template in a repository that reflects the eventual production template repository without touching `reponomics-dashboard`.

Consumer-mode smoke testing should happen in separate staging dashboard repositories, not in the generated-template staging repo itself. The current maintainer protocol is in `docs/STAGING_SMOKE.md`: one private encrypted repo is reset from the staging template for fresh setup, Pages, README, and key-rotation coverage, while one private plaintext repo preserves history for artifact-only HTML, README, and retained-data continuity checks.

### Template Publication

Template publication should remain tag-driven for normal releases:

```text
create GitHub release/tag reponomics-dashboard-vX.Y.Z
  -> validate tag equals template-contract.yml template_version
  -> build dist/template
  -> publish generated tree to reponomics-dashboard main
```

Manual workflow dispatch can remain as an explicit operator escape hatch, but it should continue to label itself as an unreleased publication. It should not be the normal release mechanism.

### Demo Publication

Demo publication should be generated and verified, not hand-maintained. The recommended flow is:

```text
source tree at commit S
  -> make build-template
  -> build demo overlay/profile from dist/template
  -> materialize deterministic synthetic canonical data
  -> render public README and encrypted Pages outputs
  -> upload encrypted retained-data seed artifact
  -> verify demo output drift
  -> publish generated tree to reponomics-dashboard-demo main
  -> dispatch demo-only target workflow to store dashboard-data artifact and deploy Pages
```

The demo should have its own expected-repo safety guard, source commit trailer, and generated provenance. It may publish on a different cadence from template releases: for example, after every template release, after action releases that affect rendered output or setup behavior, and manually when curated demo data changes.

The demo publication workflow should not be required for action correctness, but it should be a strong public regression signal. If the demo cannot regenerate cleanly from the current source, that is evidence of product drift even if unit tests still pass.

## Provenance And Attestation

There are two provenance layers and they should not be conflated.

### Product Provenance

Product provenance answers: "What source produced this action or generated template?"

Current controls:

- action releases are tied to Git tags in this source repository
- floating action tags are moved by release automation
- generated template publication records `Source-Commit`
- generated demo publication records source commit in `.reponomics/demo-provenance.json` and in the generated publication commit
- generated template output is produced from `template-manifest.yml`
- generated template output includes `.reponomics/template-provenance.json` with source commit, template version, action compatibility metadata, and a canonical payload tree digest
- generated template release workflow artifacts include a deterministic archive, canonical tree manifest, and `SHA256SUMS`
- template release artifacts are uploaded as workflow artifacts and attested by GitHub Actions on `reponomics-dashboard-v*` template releases before the workflow creates the template-repository app token or force-pushes `reponomics-dashboard`
- managed docs output includes a manifest with action repository, action version, UTC timestamp, namespace, and file hashes
- pre-release validation uploads the generated `dist/template` artifact for inspection
- source-repository third-party GitHub Actions are SHA-pinned or covered by repository policy checks; generated template repositories intentionally use the compatible Reponomics action channel by default
- runtime dependency lock and vendored assets are validated
- SBOM/provenance workflow exists for the source repository

Recommended additions:

- keep template release tags immutable once public
- require the template publish workflow to validate both the release tag and the generated output contract before push

### Generated Template Tree Digest

The first proof should be intentionally simple: compute a deterministic digest over the generated template file tree and use it to prove that the local build output is the same payload published to `reponomics-dashboard`.

The digest should be based on a canonical manifest rather than raw archive bytes. A reasonable manifest format is sorted JSON Lines containing each file path, file mode or executable bit, size, and SHA-256 of the raw file contents. Path separators should be normalized, `.git` should be excluded, and symlinks should either be rejected or represented explicitly.

The template release workflow should compute this digest for `dist/template`, publish the generated repository, fetch `reponomics-dashboard@main`, recompute the same digest, and fail if the values differ. The digest should also be written to the workflow summary, the generated commit message trailer, and a machine-readable provenance file such as `.reponomics/template-provenance.json`.

There is a self-reference problem if the provenance file contains the digest of a tree that includes itself. The simplest rule is to define the digest over the generated payload excluding `.reponomics/template-provenance.json`, then include that provenance file in both `dist/template` and the published repository. That keeps the published repository identical to the local generated tree while making the digest rule easy to explain.

The public claim becomes:

```text
payload_digest(dist/template) == payload_digest(reponomics-dashboard@main)
```

This proof is not a cryptographic build attestation by itself, but it is easy for users to understand and directly answers whether the generated template that was built is the same tree that was published.

Next-pass potential enhancement: Git's own object model can provide a useful secondary cross-check, but it should not be a Batch 4 requirement until the publication protocol is settled. The publish script creates a Git commit from the generated tree before force-pushing it to `reponomics-dashboard`; that commit has a commit SHA, and its root tree has a Git tree SHA that recursively identifies the published file names, file modes, and blob contents. A later hardening pass could record the generated commit SHA and root tree SHA in the publication summary or provenance, then compare them after fetching `reponomics-dashboard@main`. That should be treated as an auxiliary Git-native identity check, not as a replacement for the canonical payload digest or release artifact attestation.

### Release Artifact Attestation

The second proof should be stronger and release-artifact-backed. For each template release, package `dist/template` as a deterministic or manifest-backed artifact, publish the package as a workflow artifact, publish checksum files, and generate a GitHub artifact attestation for the release artifact before force-pushing the generated template repository. Do not upload these files to an already-published GitHub Release from a `release.published` workflow; immutable releases cannot be mutated after publication. If first-class GitHub Release assets become necessary, the release protocol should change so a workflow builds and attaches assets while the release is still a draft, then publishes the release last.

The release artifact set should probably include:

- `reponomics-dashboard-template-vX.Y.Z.tar.gz`
- `reponomics-dashboard-template-vX.Y.Z.tree.jsonl`
- `SHA256SUMS`

The GitHub workflow should use an attestation step with job-scoped `id-token: write` and `attestations: write` permissions. The attestation subject should include the template archive and the manifest/checksum files. Users can then verify the artifact provenance independently with GitHub CLI, while less specialized users can still compare checksums and tree digests.

The stronger public claim becomes:

```text
source commit
  -> GitHub Actions template release workflow
  -> generated template release artifact
  -> signed GitHub provenance attestation
  -> canonical tree digest
  -> reponomics-dashboard@main with matching digest
```

This avoids overloading the generated repository branch with a claim GitHub attestations are not naturally designed to make. GitHub attests the release artifact; the canonical tree digest proves that the published template repository matches that attested artifact's payload.

### Runtime Provenance

Runtime provenance answers: "Which action commit produced the collected artifact and which publish run is allowed to consume it?"

Current controls in `dashboard_action/run_modules/provenance.py`:

- collect writes source repository, source SHA, workflow run ID, action repository, action ref, resolved action SHA, runtime version, data mode, retention settings, Pages setting, and README setting
- publish can require current runtime/action identity to match collect provenance
- data mode mismatches are rejected
- malformed or cross-repository provenance is rejected

This should remain part of the action runtime, not the template generator. The template only wires the action into user workflows.

## Release Coordination Recommendations

### Keep Two Versions, But One Source Of Truth

Use one repository for development and two explicit product versions:

- action version: action/runtime SemVer, action release tag `vX.Y.Z`
- template version: generated template SemVer, template release tag `reponomics-dashboard-vX.Y.Z`

Do not collapse these versions. They answer different questions:

- "Can this action release run under templates already copied by users?"
- "What generated template did a new user copy?"

### Keep Template SemVer Human-Owned

Release Please can continue to automate action release PRs. For the template, prefer human-owned version classification for now. The template has cross-path inputs, compatibility implications, and user setup consequences that are easy for path-based automation to misclassify.

Release Please may still help as process tooling if configured narrowly, for example by drafting notes or reminding maintainers about release files. It should not be the authority that decides template SemVer. After an action release is published, release automation may still open or update the template acceptance PR using the already-decided SemVer class.

### Suggested Action Release Flow

01. Merge PRs to `main` after CI passes.
02. Release Please opens or updates the action release PR for action-affecting changes.
03. Before merging the release PR, run pre-release validation for the candidate ref when action/template behavior is touched.
04. Publish the action release `vX.Y.Z`.
05. Move floating `vX` and `vX.Y` tags.
06. Open or update a follow-up template acceptance PR that records the released action version, tag, immutable SHA, and default compatible ref in `template-contract.yml`.
07. Review and merge the template acceptance PR as the effective template release approval.
08. Let `template-release.yml` run the template release gates from the merged commit and create the matching `reponomics-dashboard-vX.Y.Z` release.
09. Let `publish-template.yml` publish the accepted template projection.
10. Once historical compatibility fixtures exist, confirm they pass against the released action major.

### Suggested Template Release Flow

1. Make template-affecting changes in this source repository.
2. Update `template-contract.yml` manually:
   - bump `template_version`
   - update `accepted_action` when accepting a newly published action release
   - adjust `minimum_compatible_template_version` and protected template refs only for an explicit action/template compatibility reset
   - adjust `compatible_action_major` only when intentionally moving to a new action compatibility line
3. Run local gates:
   - `make build-template`
   - `make template-smoke`
   - `make template-consumer-e2e`
   - `make validate-template-accepted-action`
   - `make template-accepted-action-e2e`
   - `make publish-template-dry-run`
   - `make publish-template-staging-dry-run`
4. Run pre-release validation on the candidate ref.
5. Publish to `reponomics-dashboard-staging` and smoke-test a copied staging template when the change has user-visible setup or workflow impact.
6. Let `template-release.yml` create `reponomics-dashboard-vX.Y.Z` from the merged `main` commit.
7. Let `publish-template.yml` publish the generated output to `reponomics-dashboard`.
8. Add or update compatibility fixtures for this template release.

### Generated Template Regeneration Protocol

`dist/template` is generated output, not source. It is rebuilt from `template/`, `template-manifest.yml`, `template-contract.yml`, and the action-owned managed-docs bundle in `dashboard_action/runtime/managed_docs/`.

The managed-docs snapshot at `dist/template/docs/reponomics/` is generated by `scripts/build_template.py` through `scripts/template_contract.py`. The generated `.manifest.json` records the current action version, managed namespace, source timestamp, and SHA-256 hashes for the rendered managed-doc files. Maintainers should not edit that manifest or its generated hashes by hand.

To regenerate the template locally, run `make build-template`. To prove the generated tree still matches the source contract, run `make verify-template`; this target rebuilds `dist/template` before verification so ignored local output cannot mask stale generated files. If managed docs, action version metadata, template workflow or wrapper refs, accepted action metadata, or the template contract change, these commands are the authoritative way to refresh and verify `dist/template`.

Publishing `dist/template` to `reponomics-dashboard` is a product decision for template-only changes, but it is now a required acceptance step for every public action release. Existing generated repositories consume compatible fixes through the floating action channel; the corresponding template release records that the template contract accepts the released action version/tag/SHA and gives SHA-pinned users an auditable recommendation. For template-only changes, perform a template release when the first-copy template surface should change for new users, or use an explicitly recorded manual private publication for non-public staging.

### Template Contract

`template-contract.yml` is the human-owned compatibility contract between this source repository, the generated template repository, and the public action channel that generated workflows invoke through their local wrapper. It is intentionally small: it should answer which template is being published, which Reponomics action line the template uses by default, the minimum compatible template version that action releases must continue to support, which published template refs prove that claim, and where generated managed docs belong.

The current fields have these meanings:

- `schema_version`: the contract file format. Version `1` means the fields below are required and validated by `scripts/template_contract.py`.
- `template_version`: the SemVer version of the generated template product. Template release tags must be `reponomics-dashboard-v<template_version>`.
- `action_repository`: the GitHub repository that the generated local wrapper invokes. For this product line it must remain `reponomics/reponomics-dashboard-action`.
- `default_action_ref`: the default ref written into the generated local wrapper. During the `v0` beta line this should remain the compatible floating major ref `v0`, not a full SHA.
- `compatible_action_major`: the action major line the template is allowed to use. It must match `default_action_ref`, so `compatible_action_major: 0` implies `default_action_ref: v0`.
- `accepted_action`: the released action that this template contract accepts. It records the action repository, SemVer version, exact tag, immutable commit SHA, and default compatible ref that generated templates recommend by default.
- `minimum_compatible_template_version`: the oldest published template version that action releases must continue to support.
- `protected_template_refs`: the source-repository template release refs that prove the minimum compatible template version and any additional compatibility-relevant published template releases.
- `managed_docs_namespace`: the generated repository path that receives the managed Reponomics docs snapshot. It is currently fixed at `docs/reponomics`.

The contract is validated in four layers. Local validation proves the checked-out action version matches `compatible_action_major` and still exposes action metadata required by generated workflows. Generated-template validation proves `dist/template` contains the expected managed-docs snapshot, generated workflows invoke the local wrapper, and the wrapper's remote action ref matches `action_repository@default_action_ref`. Accepted-action validation proves the recorded action tag resolves to the recorded SHA and that the public default ref is consistent with the accepted release. Action-release validation proves the candidate action still works against both the current generated template and the minimum compatible template version recorded by `template-contract.yml`. Template publication should use `make template-release-gates` so these checks run together before the generated repository is pushed.

### Coordinated Releases

Some changes legitimately require both products:

- a new generated workflow uses a new action input
- managed docs describe behavior introduced in a new action release
- the template changes default action refs or setup assumptions
- artifact/provenance contracts change

For these changes, release order should be:

1. Release the action first if the new template requires new action behavior.
2. Accept the released action in `template-contract.yml` with its exact tag and SHA through a template acceptance PR.
3. Merge the acceptance PR after review.
4. Release the template after validating it against the accepted action release.

For action-only fixes that remain compatible with old templates, publish a template acceptance release even if the generated first-copy surface is otherwise unchanged. For docs-only managed-doc updates bundled in the action, publish a template acceptance release for the public action release; use the normal template SemVer classification to decide whether that acceptance is a patch or minor template release.

### Demo Update Flow

The demo should not drive SemVer, but it should follow product releases:

1. After a template release, regenerate and publish the demo from the new template if the setup surface, docs, workflows, or first-run experience changed.
2. After an action release, regenerate and publish the demo if runtime output, README rendering, Pages rendering, managed docs, doctor/incident guidance, or setup behavior changed.
3. When curated demo data changes, publish the demo without implying an action or template version bump.
4. Treat scheduled synthetic-date rollover failures as demo-publication failures, not action/template release failures.

The demo should disclose which action version, template version, source commit, synthetic data revision, and public demo key it uses. That makes it useful both to prospective users and to skeptical reviewers trying to trace what they are seeing.

## Product And Test Boundary Constraints

The consolidated repository should be understood as one source repository with two product projections, not as two independently rebased product trees:

- Action product projection: `action.yml`, `dashboard_action/`, runtime dependency locks/assets, runtime managed-docs bundle, and action release metadata.
- Template product projection: `template/`, `template-contract.yml`, `template-manifest.yml`, template build/publish scripts, and generated-template tests.
- Shared contract/support layer: managed docs, action metadata consumed by generated workflows, Make targets, release workflows, and bridge tests.
- Maintainer-only material: non-shipping docs, repository hygiene workflows, and local tooling.

The mainline invariant is:

> Every merge to `main` must leave the repository in a state where both products can be built and validated from that same commit.

That does not require every deep test from both product pyramids to run on every PR forever. It does require the mainline merge gate to be an AND over the defined releasability contract for the current release phase:

- shared source gates such as linting, typing, unit tests, and workflow parsing;
- action core gates for action/runtime behavior;
- template core gates such as build, verify, workflow classification, and generated workflow syntax;
- action/template bridge gates proving the generated template from the candidate commit can invoke the action from the same candidate commit through the public contract.

Deeper product-specific checks may be path-aware or release-only once they become expensive, but bridge tests should block action-side PRs. A runtime change that breaks copied generated templates is an action regression even when no template files changed.

The direct generated-template consumer e2e and the composite action boundary e2e are separate bridge checks. The direct runtime e2e proves that generated consumer repositories still work against the local runtime under realistic template data/config conditions. The composite boundary e2e proves that `action.yml` maps generated workflow inputs into the expected `REPONOMICS_*` environment and executes the runtime command through the composite action surface. They do not both need to run routinely for every PR: run the direct bridge as the regular generated-template behavior gate, and run the composite boundary gate when `action.yml`, generated workflow `with:` blocks, action input names/defaults, or runtime env-loading changes. Product release candidates may run both as an explicit pre-release confidence check.

When changing the action input schema, update the full boundary, not just `action.yml`. The usual checklist is: update `action.yml` input metadata and the composite runtime-step env mapping; update `dashboard_action/run_modules/config.py` and `RuntimeConfig` if the runtime consumes a new or renamed `REPONOMICS_*` variable; update generated workflow `with:` blocks under `template/.github/workflows/`; update managed docs and template README/config examples when user-facing setup changes; update `scripts/template_consumer_e2e.py`'s required composite env contract and generated-repo tests when the boundary intentionally changes. Run `make template-action-boundary-e2e` for any action input/default/env-loading change. Run `make template-consumer-e2e` when the change affects runtime behavior in generated consumer repositories. Run `make template-compat-e2e` for release candidates and for changes that might affect copied template compatibility. If an action release intentionally stops supporting older published templates, update `template-contract.yml`'s `minimum_compatible_template_version` and protected template refs in the same review and make the compatibility reset explicit in release notes.

As a search aid, action input changes often touch `action.yml`, `dashboard_action/run.py`, `dashboard_action/run_modules/config.py`, `dashboard_action/run_modules/core.py`, `dashboard_action/run_modules/validation.py`, `scripts/template_consumer_e2e.py`, `scripts/template_contract.py`, and tests such as `tests/test_action_metadata.py`, `tests/test_run_unit.py`, and `tests/test_runner.py`. This list is intentionally not exhaustive. If these files stop owning the relevant boundary, update the guidance instead of treating the list as a fixed contract.

Compatibility fixtures should be phased by release maturity:

- Before beta, compatibility fixtures are regression canaries only. They should not prevent intentional last-minute breaking changes while there are no public users.
- At beta, keep fixtures for beta surfaces and treat backwards compatibility within the `v0` line as a real commitment once live beta users exist. A breaking beta reset should be explicitly announced and coordinated.
- At public release, preserve the first public generated template surface as a hard compatibility target for the declared compatible action major.
- After public release, every template release should retain a minimal fixture capturing generated workflows, `config.yaml` shape, managed-docs manifest schema, relevant action refs/inputs, and representative setup state.

Colocated tests are acceptable, but they need explicit ownership and isolation to avoid environment pollution:

- Prefer clear test groupings such as `action`, `template`, `bridge`, and `release` through directories, markers, or CI jobs.
- Consumer-repository simulations should run under `tmp_path` or temporary git repositories, not by mutating the source repo root.
- Tests that patch cwd, environment variables, runtime paths, module globals, or `sys.path` should restore them through fixtures such as `monkeypatch`.
- Tests should not depend on order or shared generated state. Root-level writes should be limited to explicit Make targets like `build-template`.
- CI jobs may separate action, template, and bridge checks for process isolation and clearer ownership even when the tests live in one `tests/` tree.

This framing keeps concerns separated without pretending the products are physically independent. The repository remains one source of truth, while the action and template remain separate products with explicit projection and bridge boundaries.

## Current Gaps To Close

Before public release, the most valuable hardening work is:

- Create historical template compatibility fixtures and run current action code against them in CI.
- Add a short template release checklist that encodes the manual SemVer decision points.
- Operationalize the demo refresh cadence and keep validating the live public demo after UI/rendering changes.
- Review maintainer docs listed in `docs/OBSOLETE_DOCS_INVENTORY.md` and either archive or supersede them.
- Tighten pre-release validation so it is clearly required by policy for product releases, even if GitHub cannot technically force it for every manual tag.
- Keep public beta on the `v0` compatibility line and document the beta compatibility commitment, including the process for any explicitly coordinated breaking beta reset.

## Design Bias

The consolidation is worth keeping. The previous architecture spent too much coordination energy proving that one repository could hand off to another. The co-located architecture lets CI test the real product relationship directly: the generated template invoking the candidate action.

The important guardrail is not to erase the product boundary. One source repository should reduce coordination overhead, but action and template versions should remain separate, explicit, and testable.
