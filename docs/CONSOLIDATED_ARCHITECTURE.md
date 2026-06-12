# Consolidated Action And Template Architecture

This note describes the architecture this repository should converge on after the action/template transfer. It is partly descriptive and partly normative: some pieces already exist on this branch, while others are recommendations for the next hardening pass.

It is not an ADR. The goal is to make the intended operating model legible now that the source has been co-located.

## Architectural Thesis

Reponomics has one development repository and two independently versioned products, plus one public demo surface:

- `reponomics-dashboard-action`: the GitHub Marketplace action and runtime update channel.
- `reponomics-dashboard`: the generated template repository users copy.
- `reponomics-dashboard-demo`: a generated, public, user-realistic demonstration repository showing the post-setup experience.

The generated template is not a second development repository. It is a published artifact built from this source tree. The retired `reponomics-dashboard-dev` repository should not sit in the release path.

The demo repository is also not a third development repository. It should be a generated consumer of the same action/template system with an explicit demo profile layered on top.

This split is necessary because copied GitHub template repositories cannot be updated in place by the publisher. After a user copies the template, that copy is effectively durable. The action is therefore the ongoing delivery channel for compatible fixes, enhancements, runtime docs, and operational behavior.

That creates an asymmetric compatibility rule:

- New compatible action releases must continue to work with previously published template versions.
- New template releases may require newer action behavior through `template-contract.yml`.
- Old templates are not expected to learn new template structure unless their owners choose to recopy or manually migrate.

## Repository Topology

The intended source layout is:

```text
reponomics-dashboard-action/
  action.yml
  dashboard_action/
  template/
  template-contract.yml
  template-manifest.yml
  scripts/
  tests/
  docs/
  .github/workflows/
```

The major areas of responsibility are:

| Area | Responsibility |
| --- | --- |
| `action.yml` | Public composite action interface. This is the Marketplace product entry point. |
| `dashboard_action/` | Action runtime package, mode dispatch, collection, publish, doctor, incident reset, managed docs sync, provenance, and rendering. |
| `dashboard_action/runtime/managed_docs/` | Source bundle for user-facing managed documentation that ships into generated repositories and can be refreshed by the action. |
| `template/` | Hand-maintained source for files that belong in the generated dashboard template repository. |
| `template-manifest.yml` | Explicit shipped-file allowlist plus forbidden-path guard for generated template output. |
| `template-contract.yml` | Template product metadata and action compatibility contract. |
| `scripts/build_template.py` | Builds `dist/template` from `template/`, overlays managed docs, and verifies output. |
| `scripts/template_contract.py` | Validates local action/template compatibility, managed docs snapshots, and action references in generated output. |
| `scripts/publish_generated_repo.py` | Publishes a generated output tree to `reponomics-dashboard` with target safety checks. |
| `scripts/template_consumer_e2e.py` and `scripts/smoke_template_release.py` | Local generated-template validation against the current action source. |
| Future demo tooling | Builds and publishes `reponomics-dashboard-demo` from the generated template plus explicit demo fixtures and overrides. |
| `tests/` | Action runtime tests, generated-template tests, scenario snapshots, security/contract checks, and compatibility fixtures. |
| `.github/workflows/` | CI, release, template publish, pre-release validation, and repository hygiene workflows. |
| `docs/` | Maintainer documentation for this development repository. User-facing generated-repo docs should live in managed docs or `template/`. |

`dist/template/` is a local build output. It should be treated like a compiled artifact: useful for inspection, tests, and publication, but not as source.

## Product Boundaries

### Action Product

The action product consists of:

- `action.yml`
- `dashboard_action/`
- runtime dependencies and locks
- bundled runtime assets
- bundled managed docs
- Marketplace-facing README and release notes
- action release tags, currently `v*`
- floating action tags such as `v0` and `v0.22`

The action version is owned by the Python package/runtime metadata. Release Please may remain useful for the action release PR and GitHub release process, but it should be understood as action-only automation.

Action changes are breaking when they invalidate a previously published template contract within the declared compatible action major. That includes removing action inputs or outputs used by old templates, changing workflow mode semantics, changing required secrets without migration behavior, or changing artifact/provenance formats without compatibility handling.

### Template Product

The template product consists of the generated output published to `reponomics/reponomics-dashboard`. Its source inputs are:

- `template/`
- `template-manifest.yml`
- `template-contract.yml`
- template-affecting generator scripts
- `dashboard_action/runtime/managed_docs/`
- action metadata required by generated workflows

The template version is owned by `template-contract.yml`, not Release Please. Template releases should use `reponomics-dashboard-vX.Y.Z` tags so they do not compete with action tags.

Template changes are breaking when a newly copied generated repository requires different user setup, different repository permissions, different secrets, different GitHub Pages behavior, or a newer action capability than older template versions required. Because there are no users yet, the project can still use this pre-public phase to simplify aggressively, but this distinction should be preserved before public release.

### Generated Template Repository

`reponomics-dashboard` should contain only polished user-facing template output. It should not contain maintainer scripts, tests, source-only docs, caches, internal planning files, or action runtime source.

Publication should be a reproducible projection from this repository:

```text
source tree at commit S
  -> make build-template
  -> dist/template
  -> publish_generated_repo.py
  -> reponomics-dashboard main
```

The generated commit message should continue to record `Source-Commit: S`. That gives maintainers a cheap provenance link from the generated template back to the exact source commit.

### Demo Repository

`reponomics-dashboard-demo` should be a public generated repository that answers a different user question than the template: "What will this look like after I copy the template and run setup?"

The demo should be generated from the same template output, then configured by an explicit demo profile. That profile should be narrow and auditable:

- use the same repository layout as a real generated template repository
- use the same action entry points, workflow modes, rendering paths, artifact lifecycle, managed docs sync behavior, and Pages publication path wherever possible
- replace live GitHub collection with deterministic mocked responses for a manicured portfolio of repositories
- publish a README dashboard even though normal public generated repositories prohibit README dashboard generation
- publish a Pages dashboard, which is normal and supported
- use encrypted dashboard mode with an intentionally public demo key so visitors can unlock the Pages dashboard
- label the public demo key unmistakably as a demo credential that must never be reused

The demo should intentionally violate real-template constraints only where the demonstration requires it. Those violations should live in demo-specific source, scripts, or workflow inputs rather than weakening the normal template contract. In particular, the public-template rule that blocks README dashboard generation in public repositories should remain true for users; the demo should bypass it through a named demo mode or controlled fixture path, not by relaxing the production validation rule.

The demo repository should be treated as a public showroom and an integration test surface, not as a third SemVer product. It should normally track the current compatible action/template line and be republished when action or template changes materially affect the displayed experience.

## Development Tooling

The Makefile should remain the primary local interface. That keeps local development, CI, and release workflows speaking the same commands.

Recommended command groups:

- `make lint`, `make type-check`, `make test`: normal action/runtime quality gates.
- `make validate`: action metadata, workflow syntax, runtime lock, vendored asset checks, and any source-repo security posture checks that remain local.
- `make build-template`: generate `dist/template`.
- `make verify-template`: verify an existing generated output tree.
- `make template-smoke`: check generated workflow and publication shape.
- `make template-consumer-e2e`: run generated template consumers against the local action source.
- `make publish-template-dry-run`: verify the publication target without pushing.
- `make publish-template`: operator-only push to the generated template repo.
- Future demo commands should mirror the same pattern: build the demo from generated template output, run mocked setup/collect/publish, verify no output drift, dry-run publication, and then publish to `reponomics-dashboard-demo`.

Python development should continue to use `venv/` and Python 3.11 as the release workflow baseline, while CI also checks newer supported Python versions for runtime compatibility. Source-repository GitHub Actions should remain full-SHA pinned or covered by repository policy checks, with top-level workflow permissions read-only or empty and write permissions scoped to the specific job that needs them. Generated user repositories intentionally default to the compatible Reponomics action channel rather than full-SHA pinning.

The template generator should keep refusing unsafe output paths inside the source tree outside `dist/`. That is more important after consolidation, because the template source and generated output now live in the same checkout.

## Testing Model

The testing model should prove three things:

1. The action runtime works.
2. The generated template is clean and complete.
3. The current action source works when invoked by the generated template.

Current and recommended layers:

| Layer | Purpose |
| --- | --- |
| Unit tests | Runtime modes, GitHub API handling, artifact lineage, crypto, config parsing, render helpers, managed docs sync. |
| Generated-repo tests | Verify manifest behavior, forbidden paths, generated workflows, managed docs snapshots, action references, and publication safety. |
| Scenario snapshots | Hold dashboard output stable across representative data shapes. |
| Template smoke | Exercise generated template workflow shape and release/publish assumptions cheaply. |
| Template consumer e2e | Build a generated template and run it against the local action source, closing the old action-repo-to-dashboard-dev gap. |
| Demo e2e | Build a public demo repository from the generated template, run mocked collection against curated repository data, render README and Pages outputs, and verify drift. |
| Compatibility fixtures | Future requirement: preserve old published template contracts and run new action versions against them. |

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
- Future demo job for mocked demo setup/collect/publish and demo publication dry-run.
- Scenario snapshot job for dashboard rendering stability.
- Security and supply-chain jobs for source-repository action pinning or policy verification, runtime lock, vendored assets, OSV, Scorecard, and SBOM/provenance generation.

This is the right direction. The template job is the key addition made possible by consolidation: it validates action changes with the generated template before either product ships.

### Pre-release Validation

`.github/workflows/pre-release-validation.yml` should be treated as the lightweight staging substitute. It should validate a candidate ref without publishing:

- action metadata and source-repository workflow policy
- generated template build
- generated template smoke checks
- template consumer e2e against the same candidate action source
- template publication dry-run
- generated template artifact upload for inspection

This should be run before action releases that affect runtime behavior used by templates, and before every template release. It does not need to become a full staging environment unless the product later needs persistent external state.

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
  -> run mocked setup/collect/publish lifecycle
  -> verify demo output drift
  -> publish generated tree to reponomics-dashboard-demo main
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
- generated demo publication should also record `Source-Commit`
- generated template output is produced from `template-manifest.yml`
- managed docs output includes a manifest with action repository, action version, UTC timestamp, namespace, and file hashes
- pre-release validation uploads the generated `dist/template` artifact for inspection
- source-repository third-party GitHub Actions are SHA-pinned or covered by repository policy checks; generated template repositories intentionally use the compatible Reponomics action channel by default
- runtime dependency lock and vendored assets are validated
- SBOM/provenance workflow exists for the source repository

Recommended additions:

- add a canonical generated-template tree digest so maintainers and users can verify that `dist/template` and `reponomics-dashboard@main` contain the same payload
- attach an attested generated-template release artifact to template GitHub releases for a stronger release-artifact-backed proof
- record the source commit, template version, and canonical tree digest in a machine-readable generated file in `reponomics-dashboard`, separate from managed docs if needed
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

### Release Artifact Attestation

The second proof should be stronger and release-artifact-backed. For each template release, package `dist/template` as a deterministic or manifest-backed artifact, attach it to the `reponomics-dashboard-vX.Y.Z` GitHub release, publish checksum files, and generate a GitHub artifact attestation for the release artifact.

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

- collect writes source repository, source SHA, workflow run ID, action repository, action ref, resolved action SHA, runtime version, privacy mode, retention settings, Pages setting, and README setting
- publish can require current runtime/action identity to match collect provenance
- artifact mode mismatches are rejected
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

### Do Not Use Release Please As The Template Semantic Releaser

Release Please can continue to automate action release PRs. For the template, prefer human-owned version classification for now. The template has cross-path inputs, compatibility implications, and user setup consequences that are easy for path-based automation to misclassify.

Release Please may still help as process tooling if configured narrowly, for example by drafting notes or reminding maintainers about release files. It should not be the authority that decides template SemVer.

### Suggested Action Release Flow

1. Merge PRs to `main` after CI passes.
2. Release Please opens or updates the action release PR for action-affecting changes.
3. Before merging the release PR, run pre-release validation for the candidate ref when action/template behavior is touched.
4. Publish the action release `vX.Y.Z`.
5. Move floating `vX` and `vX.Y` tags.
6. Once historical compatibility fixtures exist, confirm they pass against the released action major.

### Suggested Template Release Flow

1. Make template-affecting changes in this source repository.
2. Update `template-contract.yml` manually:
   - bump `template_version`
   - adjust `min_action_version` if the template depends on newer action behavior
   - adjust `compatible_action_major` only when intentionally moving to a new action compatibility line
3. Run local gates:
   - `make build-template`
   - `make template-smoke`
   - `make template-consumer-e2e`
   - `make publish-template-dry-run`
4. Run pre-release validation on the candidate ref.
5. Create `reponomics-dashboard-vX.Y.Z`.
6. Let `publish-template.yml` publish the generated output to `reponomics-dashboard`.
7. Add or update compatibility fixtures for this template release.

### Generated Template Regeneration Protocol

`dist/template` is generated output, not source. It is rebuilt from `template/`, `template-manifest.yml`, `template-contract.yml`, and the action-owned managed-docs bundle in `dashboard_action/runtime/managed_docs/`.

The managed-docs snapshot at `dist/template/docs/reponomics/` is generated by `scripts/build_template.py` through `scripts/template_contract.py`. The generated `.manifest.json` records the current action version, managed namespace, source timestamp, and SHA-256 hashes for the rendered managed-doc files. Maintainers should not edit that manifest or its generated hashes by hand.

To regenerate the template locally, run `make build-template`. To prove the generated tree still matches the source contract, run `make verify-template`. If managed docs, action version metadata, template workflow refs, or the template contract change, these commands are the authoritative way to refresh and verify `dist/template`.

Publishing `dist/template` to `reponomics-dashboard` is a product decision, not an automatic consequence of every action release. For action-only fixes that remain compatible with the existing template, no template publication is required. For managed-doc changes bundled in the action, no template publication is required unless new users need the updated initial docs before their first action run. If the first-copy template surface should change for new users, perform a template release or an explicitly recorded manual private publication.

### Template Contract

`template-contract.yml` is the human-owned compatibility contract between this source repository, the generated template repository, and the public action channel that generated workflows invoke. It is intentionally small: it should answer which template is being published, which Reponomics action line the template uses by default, the oldest compatible action version the template requires, and where generated managed docs belong.

The current fields have these meanings:

- `schema_version`: the contract file format. Version `1` means the fields below are required and validated by `scripts/template_contract.py`.
- `template_version`: the SemVer version of the generated template product. Template release tags must be `reponomics-dashboard-v<template_version>`.
- `action_repository`: the GitHub repository that generated workflows invoke. For this product line it must remain `reponomics/reponomics-dashboard-action`.
- `default_action_ref`: the default ref written into executable generated workflows. During the `v0` beta line this should remain the compatible floating major ref `v0`, not a full SHA.
- `compatible_action_major`: the action major line the template is allowed to use. It must match `default_action_ref`, so `compatible_action_major: 0` implies `default_action_ref: v0`.
- `min_action_version`: the oldest action version that contains the behavior this template requires. Increase it when generated workflows, setup behavior, managed docs, provenance, or runtime assumptions depend on newer action behavior.
- `managed_docs_namespace`: the generated repository path that receives the managed Reponomics docs snapshot. It is currently fixed at `docs/reponomics`.

The contract is validated in three layers. Local validation proves the checked-out action version matches `compatible_action_major`, is greater than or equal to `min_action_version`, and still exposes action metadata required by generated workflows. Generated-template validation proves `dist/template` contains the expected managed-docs snapshot and executable workflow refs matching `action_repository@default_action_ref`. Release/publication validation should additionally prove that the public default action ref, such as `v0`, has already moved to an action version satisfying `min_action_version`.

### Coordinated Releases

Some changes legitimately require both products:

- a new generated workflow uses a new action input
- managed docs describe behavior introduced in a new action release
- the template changes default action refs or setup assumptions
- artifact/provenance contracts change

For these changes, release order should be:

1. Release the action first if the new template requires new action behavior.
2. Set the template `min_action_version` to that action release.
3. Release the template after validating it against the released or candidate action.

For action-only fixes that remain compatible with old templates, no template release is required. For docs-only managed-doc updates bundled in the action, no template release is required unless the initial copied docs need to change for new users before they run the action.

### Demo Update Flow

The demo should not drive SemVer, but it should follow product releases:

1. After a template release, regenerate and publish the demo from the new template if the setup surface, docs, workflows, or first-run experience changed.
2. After an action release, regenerate and publish the demo if runtime output, README rendering, Pages rendering, managed docs, doctor/incident guidance, or setup behavior changed.
3. When curated demo data changes, publish the demo without implying an action or template version bump.

The demo should disclose which action version, template version, source commit, mock data revision, and public demo key it uses. That makes it useful both to prospective users and to skeptical reviewers trying to trace what they are seeing.

## Product And Test Boundary Constraints

The consolidated repository should be understood as one source repository with
two product projections, not as two independently rebased product trees:

- Action product projection: `action.yml`, `dashboard_action/`, runtime
  dependency locks/assets, runtime managed-docs bundle, and action release
  metadata.
- Template product projection: `template/`, `template-contract.yml`,
  `template-manifest.yml`, template build/publish scripts, and generated-template
  tests.
- Shared contract/support layer: managed docs, action metadata consumed by
  generated workflows, Make targets, release workflows, and bridge tests.
- Maintainer-only material: non-shipping docs, repository hygiene workflows, and
  local tooling.

The mainline invariant is:

> Every merge to `main` must leave the repository in a state where both products
> can be built and validated from that same commit.

That does not require every deep test from both product pyramids to run on every
PR forever. It does require the mainline merge gate to be an AND over the
defined releasability contract for the current release phase:

- shared source gates such as linting, typing, unit tests, and workflow parsing;
- action core gates for action/runtime behavior;
- template core gates such as build, verify, workflow classification, and
  generated workflow syntax;
- action/template bridge gates proving the generated template from the candidate
  commit can invoke the action from the same candidate commit through the public
  contract.

Deeper product-specific checks may be path-aware or release-only once they become
expensive, but bridge tests should block action-side PRs. A runtime change that
breaks copied generated templates is an action regression even when no template
files changed.

Compatibility fixtures should be phased by release maturity:

- Before beta, compatibility fixtures are regression canaries only. They should
  not prevent intentional last-minute breaking changes while there are no public
  users.
- At beta, keep fixtures for beta surfaces and treat backwards compatibility
  within the `v0` line as a real commitment once live beta users exist. A
  breaking beta reset should be explicitly announced and coordinated.
- At public release, preserve the first public generated template surface as a
  hard compatibility target for the declared compatible action major.
- After public release, every template release should retain a minimal fixture
  capturing generated workflows, `config.yaml` shape, managed-docs manifest
  schema, relevant action refs/inputs, and representative setup state.

Colocated tests are acceptable, but they need explicit ownership and isolation
to avoid environment pollution:

- Prefer clear test groupings such as `action`, `template`, `bridge`, and
  `release` through directories, markers, or CI jobs.
- Consumer-repository simulations should run under `tmp_path` or temporary git
  repositories, not by mutating the source repo root.
- Tests that patch cwd, environment variables, runtime paths, module globals, or
  `sys.path` should restore them through fixtures such as `monkeypatch`.
- Tests should not depend on order or shared generated state. Root-level writes
  should be limited to explicit Make targets like `build-template`.
- CI jobs may separate action, template, and bridge checks for process isolation
  and clearer ownership even when the tests live in one `tests/` tree.

This framing keeps concerns separated without pretending the products are
physically independent. The repository remains one source of truth, while the
action and template remain separate products with explicit projection and bridge
boundaries.

## Current Gaps To Close

Before public release, the most valuable hardening work is:

- Create historical template compatibility fixtures and run current action code against them in CI.
- Add a short template release checklist that encodes the manual SemVer decision points.
- Decide whether generated `reponomics-dashboard` should include a machine-readable template provenance file outside `docs/reponomics/`.
- Define and implement the demo profile for `reponomics-dashboard-demo`, including mocked collection fixtures, public demo key handling, demo-only README generation, and publication verification.
- Review maintainer docs listed in `docs/OBSOLETE_DOCS_INVENTORY.md` and either archive or supersede them.
- Tighten pre-release validation so it is clearly required by policy for product releases, even if GitHub cannot technically force it for every manual tag.
- Keep public beta on the `v0` compatibility line and document the beta compatibility commitment, including the process for any explicitly coordinated breaking beta reset.

## Design Bias

The consolidation is worth keeping. The previous architecture spent too much coordination energy proving that one repository could hand off to another. The co-located architecture lets CI test the real product relationship directly: the generated template invoking the candidate action.

The important guardrail is not to erase the product boundary. One source repository should reduce coordination overhead, but action and template versions should remain separate, explicit, and testable.
