# Template Release Process

This document describes the current maintainer process for releasing the generated `reponomics-dashboard` template. It is intentionally narrower and more operational than `docs/VERSIONING_AND_RELEASE.md`.

## Current Operating Model

The action repository, `reponomics-dashboard-action`, is the source and build authority. The generated template repository, `reponomics-dashboard`, is the product users copy.

At the moment, normal template publication is triggered by a source-repository GitHub Release with a tag shaped like `reponomics-dashboard-vX.Y.Z`. The `publish-template.yml` workflow validates the source tree, builds `dist/template`, packages and attests generated template release artifacts, then publishes generated output to `reponomics-dashboard`.

This is acceptable during the current private/pre-public template phase. A future improvement may create the visible product release in `reponomics-dashboard` after publication, so that the generated repository owns the public release record while the source repository remains the build authority.

## What Is Released

A template release promotes a generated repository state for newly copied dashboard repositories.

Template releases are appropriate when changes affect:

- generated workflows;
- setup workflow inputs or generated config shape;
- `template/config.yaml` or `template/config.example.yaml`;
- managed documentation snapshots copied into new repositories;
- template README or repository policy files;
- template provenance files;
- the minimum action behavior required by generated workflows.

Do not cut a template release for an action-only fix that existing and new repositories can receive through `reponomics/reponomics-dashboard-action@v0` without changing generated files.

## Version Source

`template-contract.yml` is the source of truth for template release metadata.

The key fields are:

- `template_version`: the generated template version. A release tag must be `reponomics-dashboard-v<template_version>`.
- `default_action_ref`: the action ref generated workflows use, currently `v0`.
- `compatible_action_major`: the compatible action major line.
- `min_action_version`: the minimum action version required by the generated template.

When the generated template requires new action behavior, release the action first or release the action and template from the same reviewed source commit. Confirm `default_action_ref` resolves to the required action behavior before publishing the template.

## Current Staging Position

The repository contains staging documentation and a `publish-template-staging.yml` workflow, but staging is not part of the default current release process because the staging surface has not been fully relaunched.

For now, use local gates and the production template publication workflow for approved private/pre-public releases. Revisit staging before public beta or before releases where a persistent generated-template staging repository would materially reduce risk.

## Normal Template Release Flow

1. Merge the template-affecting changes to `main`.
2. Confirm an action release exists if the generated template requires new action behavior.
3. Confirm `template-contract.yml` has the intended `template_version` and `min_action_version`.
4. Run the local release gates, including `make template-compat-e2e` for action/template compatibility.
5. Create a GitHub Release in `reponomics-dashboard-action` tagged `reponomics-dashboard-vX.Y.Z`.
6. Approve the `template-publication` environment when the workflow waits for it.
7. Watch the `publish-template.yml` run to completion.
8. Confirm the generated output was published to `reponomics-dashboard`.
9. Inspect `.reponomics/template-provenance.json`, the workflow artifact package, checksums, and attestations when release evidence needs review.

## Release Evidence

For release-triggered template publication, the workflow builds deterministic release artifacts from `dist/template`:

- `reponomics-dashboard-template-vX.Y.Z.tar.gz`;
- `reponomics-dashboard-template-vX.Y.Z.tree.jsonl`;
- `SHA256SUMS`.

The workflow uploads these as workflow artifacts and creates GitHub artifact attestations before minting the app token that can write to `reponomics-dashboard`.

The workflow does not attach these files to the already-published source-repository GitHub Release. This avoids mutating immutable releases after publication.

## Generated Repository Publication

The publication workflow force-pushes generated output to `reponomics-dashboard/main`. This is an intentional generated-output publication style, not a source development workflow.

Released generated commits should remain recoverable through release tags or other durable references when the generated repository becomes public-facing. Until that product-level release record exists, the source workflow run, generated commit message, and `.reponomics/template-provenance.json` are the primary trace from generated output back to source.

## Manual Publication Escape Hatch

`publish-template.yml` supports manual dispatch with `confirm_unreleased_template_publish`. Treat this as a recovery or operator escape hatch, not the normal release path.

Use the release-tag path for normal template releases, because it validates the tag against `template-contract.yml`, packages release artifacts, and creates attestations.

## Coupled Action And Template Releases

A coupled release may use one source commit for both products. In that case, the Release Please PR should update the action version metadata and any template contract changes, and the same merged commit can later receive both the action tag (`vX.Y.Z`) and the template tag (`reponomics-dashboard-vX.Y.Z`).

This keeps the compatibility claim in the immutable source state being released. It also avoids a post-action-release documentation PR whose only purpose is to record compatibility that was already verified before the release.
