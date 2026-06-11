# Consolidated Action And Template Architecture

This note describes the architecture this repository should converge on after the action/template transfer. It is partly descriptive and partly normative: some pieces already exist on this branch, while others are recommendations for the next hardening pass.

It is not an ADR. The goal is to make the intended operating model legible now that the source has been co-located.

## Architectural Thesis

Reponomics has one development repository and two independently versioned products:

- `reponomics-dashboard-action`: the GitHub Marketplace action and runtime update channel.
- `reponomics-dashboard`: the generated template repository users copy.

The generated template is not a second development repository. It is a published artifact built from this source tree. The retired `reponomics-dashboard-dev` repository should not sit in the release path.

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

## Development Tooling

The Makefile should remain the primary local interface. That keeps local development, CI, and release workflows speaking the same commands.

Recommended command groups:

- `make lint`, `make type-check`, `make test`: normal action/runtime quality gates.
- `make validate`: action metadata, workflow syntax, action pins, runtime lock, and vendored asset checks.
- `make build-template`: generate `dist/template`.
- `make verify-template`: verify an existing generated output tree.
- `make template-smoke`: check generated workflow and publication shape.
- `make template-consumer-e2e`: run generated template consumers against the local action source.
- `make publish-template-dry-run`: verify the publication target without pushing.
- `make publish-template`: operator-only push to the generated template repo.

Python development should continue to use `venv/` and Python 3.11 as the release workflow baseline, while CI also checks newer supported Python versions for runtime compatibility. GitHub Actions should remain full-SHA pinned, with top-level workflow permissions read-only or empty and write permissions scoped to the specific job that needs them.

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
- Scenario snapshot job for dashboard rendering stability.
- Security and supply-chain jobs for pinned actions, runtime lock, vendored assets, OSV, Scorecard, and SBOM/provenance generation.

This is the right direction. The template job is the key addition made possible by consolidation: it validates action changes with the generated template before either product ships.

### Pre-release Validation

`.github/workflows/pre-release-validation.yml` should be treated as the lightweight staging substitute. It should validate a candidate ref without publishing:

- action metadata and workflow pins
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

## Provenance And Attestation

There are two provenance layers and they should not be conflated.

### Product Provenance

Product provenance answers: "What source produced this action or generated template?"

Current controls:

- action releases are tied to Git tags in this source repository
- floating action tags are moved by release automation
- generated template publication records `Source-Commit`
- generated template output is produced from `template-manifest.yml`
- managed docs output includes a manifest with action repository, action version, UTC timestamp, namespace, and file hashes
- pre-release validation uploads the generated `dist/template` artifact for inspection
- GitHub Actions are SHA-pinned
- runtime dependency lock and vendored assets are validated
- SBOM/provenance workflow exists for the source repository

Recommended additions:

- attach the generated `dist/template` artifact to template GitHub releases if that would make release inspection easier
- record the source commit and template version in a machine-readable generated file in `reponomics-dashboard`, separate from managed docs if needed
- keep template release tags immutable once public
- require the template publish workflow to validate both the release tag and the generated output contract before push

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

## Current Gaps To Close

Before public release, the most valuable hardening work is:

- Create historical template compatibility fixtures and run current action code against them in CI.
- Add a short template release checklist that encodes the manual SemVer decision points.
- Decide whether generated `reponomics-dashboard` should include a machine-readable template provenance file outside `docs/reponomics/`.
- Review maintainer docs listed in `docs/OBSOLETE_DOCS_INVENTORY.md` and either archive or supersede them.
- Tighten pre-release validation so it is clearly required by policy for product releases, even if GitHub cannot technically force it for every manual tag.
- Decide whether action major `v0` remains acceptable for public launch or whether the first public release should establish a `v1` compatibility line.

## Design Bias

The consolidation is worth keeping. The previous architecture spent too much coordination energy proving that one repository could hand off to another. The co-located architecture lets CI test the real product relationship directly: the generated template invoking the candidate action.

The important guardrail is not to erase the product boundary. One source repository should reduce coordination overhead, but action and template versions should remain separate, explicit, and testable.
