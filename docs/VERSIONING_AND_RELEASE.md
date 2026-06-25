# Versioning And Release Protocol

This repository publishes two versioned products and one generated public demo:

- `reponomics-dashboard-action`: the Marketplace action in this repository.
- `reponomics-dashboard`: the generated template repository users copy.
- `reponomics-dashboard-demo`: the public generated showcase repository. It is not a SemVer product.

The release rule is simple: release the action when existing users should receive new runtime behavior through the compatible action channel, publish a corresponding template acceptance release for every public action release, release the template when template features or fixes should be published for newly copied repositories, and refresh the demo every day so the public synthetic data window stays current.

## Version Sources

| Surface | Version source | Tag shape | Release owner |
| --- | --- | --- | --- |
| Action | `pyproject.toml`, `dashboard_action/run_modules/core.py`, `.github/.release-please-manifest.json` | `vX.Y.Z`, plus floating `vX` and `vX.Y` | Release Please |
| Template | `template-contract.yml` `template_version` | `reponomics-dashboard-vX.Y.Z` in `reponomics-dashboard`, plus a matching immutable source tag | Automated action-release acceptance or maintainer-created template release |
| Demo | none | none | Generated from an approved source ref |

Do not use bare `v*` tags for template releases. Do not use `reponomics-dashboard-v*` tags for action releases. The public generated-template GitHub Release belongs in `reponomics/reponomics-dashboard`, not in this Action repository's release feed.

`template-contract.yml` is the source of truth for the generated template version, generated action ref, accepted action release metadata, and action/template compatibility line. Generated templates ship against the current compatible action channel. Action releases must continue to pass against both the current generated template and the minimum compatible template version.

Every public action release publishes a corresponding template acceptance release. The acceptance PR records the released action version, tag, resolved commit SHA, and default compatible ref in `template-contract.yml`; merging that PR is the maintainer approval for the template release. The Template Release workflow then runs the release gates, prepares the publication handoff, requests `template-publication` deployment approval only when publication is needed, creates the immutable source tag after approval, publishes `reponomics/reponomics-dashboard`, and creates the public generated-template release there. Generated template provenance carries the same accepted action metadata. The generated managed-docs manifest still records the bundled action version in `docs/reponomics/.manifest.json`.

Generated dashboard repositories are supported on released action refs: floating major/minor release refs, exact release tags, or full commit SHAs for released action commits. Branch refs such as `main` are not a supported generated-template runtime channel because they can run unreleased action behavior outside the accepted template contract.

ADR 020 records the compatibility-gate rationale and the contract-field cleanup for the minimum compatible template version. ADR 022 records the action-release template acceptance model.

After a major consolidation or other release-cadence reset, it is reasonable to bump `template_version` and, only for an explicit compatibility reset, move `minimum_compatible_template_version` forward. Do that in `template-contract.yml`, not by recording the concrete version values here. Do not move `minimum_compatible_template_version` for ordinary action acceptance releases.

## Compatibility Policy

The project is still on the `v0` action/template compatibility line. Before public beta, intentional breaking changes are still allowed when they simplify the product. Once live beta users exist, treat backwards compatibility within `v0` as a real commitment unless a breaking beta reset is explicitly announced and coordinated.

Action changes are breaking when they invalidate a previously published template contract within the declared compatible action major. Examples include removing inputs or outputs used by generated workflows, changing mode semantics, changing required secrets without migration behavior, or changing retained-artifact/provenance formats without compatibility handling.

Template changes are breaking when newly copied repositories require different user setup, repository permissions, secrets, Pages behavior, or action capabilities than older template versions required.

Retained data compatibility is part of that same contract. Generated template users can stay pinned to the action version they started with and later upgrade directly to a newer release. If the newer runtime cannot migrate retained packet schemas produced by a previously supported template/action pairing, the release has broken the upgrade path for those users. Treat that as a breaking compatibility reset, not as a separate template-versus-runtime compatibility floor. The retained packet migration policy is maintained in [Retained Data Migrations](./RETAINED_DATA_MIGRATIONS.md).

When changing the action input schema, update the full boundary, not just `action.yml`. This often includes `action.yml`, `dashboard_action/run.py`, `dashboard_action/run_modules/config.py`, `dashboard_action/run_modules/core.py`, `dashboard_action/run_modules/validation.py`, `scripts/template_consumer_e2e.py`, `scripts/template_contract.py`, and tests such as `tests/test_action_metadata.py`, `tests/test_run_unit.py`, and `tests/runner/`. This list is a search aid, not an exhaustive contract; update it when those files stop owning the relevant boundary.

## Staging Before Release

Merging to `main` does not require cutting an action release immediately. `main` may serve as a short staging line where maintainers run CI, candidate validation, local smoke tests, demo checks, and private template staging publication if the staging protocol is later resumed.

Use this staging period when a change has meaningful surface area, such as dashboard rendering, artifact format, generated workflows, setup behavior, managed docs, release tooling, or demo publication behavior.

Recommended staging flow:

1. Merge the candidate work to `main` after PR CI passes.
2. Let scheduled and push CI run on `main`.
3. Run `.github/workflows/pre-release-validation.yml` against `main`.
4. Run local or manual smoke checks against a copied generated template when the change is user-visible.
5. If the paused staging protocol has been resumed, publish `main` to `reponomics-dashboard-staging` with `.github/workflows/publish-template-staging.yml` when the generated template should be exercised as a persistent private surface.
6. Refresh the demo from `main` if the public demo is intentionally allowed to show staging behavior.
7. Cut the action release only after the soak period has not exposed release-blocking regressions.

There is one hard boundary: do not publish an official generated template that requires unreleased action behavior through `default_action_ref: v0`. If a candidate template needs newer action behavior, test it with candidate-source bridge tests or temporary testing repositories until the action release has moved `v0`. After that, publish the template against the current released compatible action channel.

The public demo can either follow staging `main` or follow a promoted stable ref. During pre-release, following `main` is acceptable if the demo is deliberately acting as a public smoke surface. At beta or wider public release, prefer setting `vars.DEMO_DAILY_SOURCE_REF` to a promoted ref such as `demo-stable` or a release tag, then move that ref only after staging checks pass.

## Template Staging Repository

Status: staging publication and copied-repository smoke work is paused and is not a live release gate. The effort was started to provide realistic generated-template staging coverage, then paused because the protocol became complex while more urgent release hardening work took priority. The helper scripts, Make targets, and workflow remain in the repository, but staging smoke tests are skipped until the protocol is revisited with a lighter contract model.

When resumed, `reponomics-dashboard-staging` should be provisioned as a private generated-output repository. It should mirror the production generated-template repository closely enough to support realistic copy/smoke testing, but it is not the canonical user template and should not be advertised.

Staging publication is handled by `.github/workflows/publish-template-staging.yml`. It is manual, restricted to `main` or release tags, runs the generated-template gates, dry-runs the staging target, then publishes `dist/template` to `reponomics-dashboard-staging`.

Use a dedicated staging publication GitHub App installed only on `reponomics-dashboard-staging`. Configure `vars.TEMPLATE_STAGING_PUBLISH_APP_CLIENT_ID` and `secrets.TEMPLATE_STAGING_PUBLISH_APP_PRIVATE_KEY` at repository or organization scope in this source repository. The app needs `contents: write` and `workflows: write` on the staging repository.

Staging setup checklist:

1. Create `reponomics/reponomics-dashboard-staging` as a private repository.
2. Keep it generated-output only; do not hand-maintain source files there.
3. Optionally enable GitHub's template-repository setting if maintainers should click-copy it for smoke tests.
4. Install the staging publication app only on `reponomics-dashboard-staging`.
5. Configure `TEMPLATE_STAGING_PUBLISH_APP_CLIENT_ID` and `TEMPLATE_STAGING_PUBLISH_APP_PRIVATE_KEY` in this source repository.
6. Run `.github/workflows/publish-template-staging.yml` from `main` with confirmation enabled.
7. Run the private consumer staging smoke protocol in `docs/STAGING_SMOKE.md` when the change warrants it.

Normal public template releases use `.github/workflows/template-release.yml`; routine private staging should use `publish-template-staging.yml`. There is no manual production template publication workflow.

## When To Release The Action

Cut an action release when a merged change should reach existing generated repositories through `reponomics/reponomics-dashboard-action@v0`. This includes runtime bug fixes, security fixes, collection/publish behavior changes, dashboard rendering changes, managed-docs runtime changes, and action metadata changes.

Do not cut an action release only because template source files changed, unless the action runtime or user-visible action behavior also changed.

Action releases are managed by `.github/workflows/release-please.yml`. Release Please creates or updates a release PR from `main`. When that release PR is merged, Release Please creates the GitHub Release and exact `vX.Y.Z` tag, then the workflow moves the floating `vX` and `vX.Y` tags to the release commit.

Before merging an action release PR:

1. Confirm normal CI is green.
2. Confirm the candidate action passes against the current/latest generated template.
3. Confirm the candidate action passes against the minimum compatible template version recorded by `template-contract.yml`.
4. Confirm retained artifacts produced by the minimum compatible template's original accepted action/schema migrate to the candidate runtime's current retained packet schema.
5. Confirm any intended staging/soak period is complete.
6. Run `.github/workflows/pre-release-validation.yml` on the release candidate ref if the action change touches rendering, artifacts, managed docs, action metadata, generated workflow behavior, or any template-facing contract.
7. Confirm the candidate has already exercised the template publication dry-run path through CI, `pre-release-validation.yml`, or local `make template-release-gates`. This gives the highest available confidence that template publication will succeed before the final action release SHA exists.
8. Confirm the changelog entry and SemVer bump match the change.

After the action release:

1. Confirm the exact `vX.Y.Z` tag exists.
2. Confirm floating `vX` and `vX.Y` point to the release SHA.
3. Confirm the template acceptance PR was created or was already current.
4. Review and merge the template acceptance PR as the effective template release approval.
5. Confirm the matching source tag and `reponomics/reponomics-dashboard` release `reponomics-dashboard-vX.Y.Z` were created with the template version from `template-contract.yml`.
6. Confirm the release provenance/SBOM workflow completed or failed for an understood reason.
7. If the release changes the public dashboard experience, refresh the demo.

## When To Release The Template

Cut a template release independently when template features or fixes should be published for newly copied dashboard repositories. This includes generated workflows, setup surface, config defaults, template README content, managed-docs initial snapshots, template provenance, repository policy files, or assumptions that depend on current released action behavior.

Every public action release also creates a template acceptance release, even for compatible action-only fixes. Existing generated repositories consume compatible fixes through the floating action channel; the corresponding template release records the accepted action version/tag/SHA for new copies and for users who choose SHA-pinned workflows.

If a user or organization requires SHA-pinned Actions, the generated template metadata should point them to `.reponomics/template-provenance.json` for the accepted action repository, version, tag, SHA, and default compatible ref associated with that template snapshot. `docs/reponomics/.manifest.json` also records the managed-docs action version. SHA-pinning is an opt-in policy choice; users who pin own the update cadence that the default floating compatible ref normally handles.

The template version is `template-contract.yml` `template_version`. For template-only releases, maintainers should use `.github/workflows/prepare-template-release.yml` to create the release-prep PR that bumps this value; do not hand-edit the contract unless repairing automation. Normal template publication creates an immutable source tag and a generated-repository GitHub Release whose tag is exactly:

```text
reponomics-dashboard-v<template_version>
```

If `template-contract.yml` contains `template_version: X.Y.Z`, the source tag and generated repository release tag must be `reponomics-dashboard-vX.Y.Z`.

The `.github/workflows/template-release.yml` workflow runs after an accepted template PR changes `template-contract.yml` on `main`. Ordinary template-source PRs do not publish directly; the contract bump is the release approval boundary for both action-coupled template acceptance and template-only releases. The workflow reads the merged PR release notes, runs `make template-release-gates`, validates the public action ref used by generated workflows, validates the accepted action tag/version/SHA metadata, runs template smoke and generated-template e2e checks against the accepted action release, dry-runs publication, packages deterministic template release artifacts, checks whether the generated repository release already exists with fail-closed HTTP status handling, and verifies any existing generated release tag against the expected generated payload before requesting protected `template-publication` deployment approval. If publication is needed and approved, the workflow downloads the publication handoff, creates GitHub artifact attestations, creates the immutable source tag, and only then mints the template publication app token. It appends a generated publication commit to `reponomics/reponomics-dashboard`, creates or verifies the generated release tag, pushes `main` and the tag atomically, then creates the public generated-repository release with `--verify-tag`.

The workflow intentionally does not upload assets to a GitHub Release after publication. Release evidence is carried as source workflow artifacts, artifact attestations, generated `.reponomics/template-provenance.json`, and the generated repository release body.

## Template Release Sequence

For a template-only release:

1. Open a PR with the template-source changes.
2. Confirm CI is green.
3. Merge the template-source PR.
4. Run `.github/workflows/prepare-template-release.yml` with `base_ref` left at its default `main` and `release_type` set to `patch`, `minor`, or `major`. Do not use the latest action tag as the base for a normal template-only release; action tags mark the action product release boundary and may omit later template-source changes. The workflow derives release notes from merged PRs since the previous source template tag, preferring each PR's `## Template release notes` section and falling back to PR titles.
5. Review the generated `chore: prepare template release reponomics-dashboard-vX.Y.Z` PR. That PR bumps only `template-contract.yml` and carries the generated `## Template release notes` section used by the public generated-template release.
6. Run `.github/workflows/pre-release-validation.yml` on the release-prep PR ref when the change has user-visible setup, workflow, managed-docs, or runtime-contract impact.
7. Review and merge the release-prep PR as the effective template release approval.
8. Let `.github/workflows/template-release.yml` run from the merged `main` commit. It verifies the matching generated repository release if it already exists; otherwise it reads the merged PR body, runs `make template-release-gates`, prepares the publication handoff, requests the protected `template-publication` deployment approval, creates the immutable source tag, publishes the generated repository, and creates `reponomics-dashboard-vX.Y.Z` in `reponomics/reponomics-dashboard`, where `X.Y.Z` equals `template-contract.yml`.
9. Confirm `reponomics-dashboard` `main` has a new generated publication commit containing the expected `Source-Commit`, `Template-Version`, `Payload-Digest`, and `Accepted-Action` trailers.
10. Confirm the generated release tag points to that generated commit.
11. Download or inspect the workflow artifact and attestations if release evidence needs to be verified.
12. Refresh the demo if the public showcase should reflect the new template before the next scheduled daily refresh.

For a coupled action/template release where the template requires new action behavior:

1. Land the runtime and template changes on `main`.
2. Cut the action release first, so `default_action_ref: v0` resolves to the intended released action behavior.
3. Let `.github/workflows/release-please.yml` open or update the template acceptance PR. That PR class-locks the template SemVer bump to the action release class: action patch implies template patch, action minor implies template minor, and an explicitly approved action major implies template major plus a `default_action_ref`/`compatible_action_major` transition to the new action major line. Major action releases require a matching `Release-As: X.Y.Z` trailer before Release Please is allowed to create the release.
4. Review and merge the template acceptance PR as the effective template release approval. The generated PR body includes a `## Template release notes` section with a terse `Updated action to ...` note; edit that section before merging if the template release needs fuller notes.
5. Let `.github/workflows/template-release.yml` pass the release gates, request `template-publication` approval, create the source tag, publish the generated template, and create the matching `reponomics-dashboard-vX.Y.Z` release in `reponomics/reponomics-dashboard` from the merged acceptance commit.
6. Refresh the demo from the released template ref if the public showcase should reflect the new release before the next scheduled daily refresh.

Routine private staging should use `publish-template-staging.yml`, and normal public template releases should use `.github/workflows/template-release.yml`. Production generated-template publication has no manual workflow-dispatch mutator; operator repair should be handled explicitly for the incident at hand.

## Local Release Gates

For day-to-day test selection before a change is release-shaped, see [TESTING.md](./TESTING.md). Before a release or publication handoff, the local equivalent of the release gates is:

```sh
make lint
make type-check
make validate
make test
make coverage
make verify-workflow-classification
make verify-template
make validate-template-action-ref
make validate-template-accepted-action
make template-smoke
make template-consumer-e2e
make template-accepted-action-e2e
make template-release-gates
make publish-template-dry-run
```

For demo-affecting changes, also run:

```sh
make verify-demo
make publish-demo-dry-run
```

The workflows rerun the publication-critical gates; local gates are for catching issues before an operator starts release machinery.

## Demo Publication

The demo has no independent version and is not a formal release surface. It is a generated public showcase that should refresh daily so its synthetic data remains current.

Refresh the demo:

- every day from the approved demo source ref;
- when an action release changes dashboard rendering, setup behavior, managed docs, artifact behavior, or any visible user experience;
- when a template release changes generated repository setup or docs;
- when `demo/dataset.yml` changes;
- when the relative synthetic data window needs to move forward.

The `.github/workflows/publish-demo.yml` workflow supports both manual publication and scheduled daily refresh. It builds and verifies the demo, uploads the generated demo tree and encrypted retained-data seed as source workflow artifacts, force-pushes `reponomics-dashboard-demo`, and dispatches the generated target workflow that imports the seed as the demo repository's `dashboard-data` artifact and deploys the committed Pages dashboard shell.

Daily demo refresh must not require human approval. Demo publication has two operator modes:

- manual publication for unusual refs, recovery, or action/template release-time confirmation;
- scheduled daily refresh from an approved source ref, without required reviewers, with no arbitrary `source_ref` input, and with the demo publication app token minted only after `make verify-demo` and dry-run validation pass.

The demo publication app is the primary blast-radius control. Keep it installed only on `reponomics-dashboard-demo`, keep its requested permissions limited to the current publication needs, and configure `DEMO_PUBLISH_APP_CLIENT_ID` plus `DEMO_PUBLISH_APP_PRIVATE_KEY` at repository or organization scope in this source repository. With that app installation scope, a separate approval environment is optional ceremony rather than a required security boundary.

During pre-release, the scheduled approved source ref defaults to `main`, which is appropriate while the demo is intentionally showing current mainline behavior. At beta or public release, prefer a stable source ref policy so the daily refresh does not accidentally showcase unreleased behavior; set `vars.DEMO_DAILY_SOURCE_REF` to `demo-stable` or to a release tag chosen by an explicit promotion step.

A scheduled demo refresh is not an action release and not a template release. It is a regenerated showcase commit plus a refreshed encrypted retained-data artifact.

## Recommended Cadence

- Action release: whenever existing users should receive a compatible runtime fix or feature.
- Template release: whenever template features or fixes should be published for newly copied repositories.
- Demo daily refresh: run every day to keep the 90-day synthetic window current.
- Demo event-driven refresh: after any action/template release or demo-data change that should be visible before the next scheduled refresh.
- Security or urgent bug fix: action release first if existing users are affected; template release only if new copied repositories need changed files or setup defaults.

## Verification After Publication

After action release, verify the GitHub Release, exact tag, floating tags, and release provenance/SBOM workflow.

After template publication, verify the source tag, generated repository release/tag, generated repository publication commit, `Source-Commit`, `Template-Version`, `Payload-Digest`, `Accepted-Action`, `.reponomics/template-provenance.json`, package artifacts, checksums, and attestations.

After demo publication, verify the demo repository commit, `.reponomics/demo-provenance.json`, absence of `data/` and `dist/` in git, presence of the target `dashboard-data` artifact, and the live Pages dashboard at `https://reponomics.github.io/reponomics-dashboard-demo/`.
