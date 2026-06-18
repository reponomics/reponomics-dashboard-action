# ADR 024: Template Release Publication Surface

Date: 2026-06-18

## Status

Proposed

## Context

Reponomics currently behaves like a small monorepo even though the public
distribution surfaces are GitHub-native rather than registry-native:

- `reponomics-dashboard-action` is released from this source repository and is
  consumed by copied dashboard repositories through Git refs such as `v0`.
- `reponomics-dashboard` is generated from this source repository and is
  consumed as a template repository that users copy.

ADR 020 and ADR 022 established the important compatibility and provenance
model. A public action release must be accepted into `template-contract.yml`
after the action release exists, so the generated template can record the real
action version, tag, SHA, and default compatible ref. That acceptance step is
also the maintainer approval boundary for the corresponding template
publication.

The current implementation represents that approval by creating a
source-repository GitHub Release with a `reponomics-dashboard-vX.Y.Z` tag. The
production template publication workflow listens for that release, runs the
template release gates, packages deterministic release artifacts, creates
attestations, and force-publishes the generated template repository.

That model preserves release evidence, but it creates an awkward public product
surface:

- GitHub Releases are repository-scoped, not package-scoped.
- This repository has one public releases feed and one repository-global
  "Latest" release marker.
- Template acceptance releases are published after action releases, so they can
  appear above action releases in the source repository's release list.
- Marking template releases as not latest can protect the "Latest" badge, but
  it does not create separate Action and Template release feeds.

Because Reponomics does not publish these products to a package registry, there
is no registry page that can carry separate package release history. GitHub's
repository release UI is therefore part of the product narrative. Mixing
template publication releases into the Action repository's release feed makes
the source repository look like the generated template is the latest Action
release, even when the template event is only accepting an already-published
action.

The generated template repository is the public artifact users copy. It is
therefore the more natural public home for generated-template release history.
At the same time, source-repository provenance must remain strong: the source
commit, release gates, generated tree digest, artifact attestations, accepted
action metadata, and generated publication commit must remain traceable.

## Decision

Move the public generated-template GitHub Release surface to the generated
template repository, `reponomics/reponomics-dashboard`, while keeping
source-repository template acceptance and publication gates as the provenance
authority.

The intended public release surfaces become:

- `reponomics/reponomics-dashboard-action` GitHub Releases: action releases
  only, using bare `vX.Y.Z` tags and floating action refs.
- `reponomics/reponomics-dashboard` GitHub Releases: generated template releases
  only, using `reponomics-dashboard-vX.Y.Z` tags or an equivalent generated
  template tag shape.
- This source repository: template acceptance PRs, source tags if needed for
  immutable source anchors, workflow artifacts, attestations, SBOM/provenance
  evidence, and maintainer documentation.

Normal template publication should no longer require a user-facing
source-repository GitHub Release. Instead, the source repository should retain
an auditable approval and evidence chain:

1. Merge a template acceptance PR or template-only release PR.
2. Record `template-contract.yml` with the template version and accepted action
   metadata.
3. Run the template release gates from the merged source commit.
4. Build deterministic template release artifacts and attest them from the
   source repository workflow.
5. Publish the generated tree to `reponomics/reponomics-dashboard`.
6. Create an immutable generated-repository tag and GitHub Release that points
   to the generated template commit.
7. Include links from the generated-repository release notes back to the source
   commit, source workflow run, artifact attestations, template provenance file,
   and accepted action release.

The generated template release body should distinguish first-copy template
changes from action acceptance metadata. A template acceptance release that has
no generated template surface changes should say so explicitly rather than
duplicating the action changelog.

Because production template publication force-pushes the generated repository's
default branch, publication should also protect direct recoverability of prior
template snapshots. Before replacing the generated repository's `main`, the
workflow should verify that the current generated commit is already reachable
from an immutable generated-template release tag. If it is not, the workflow
should either create a recovery tag from the current generated commit using the
template version recorded in `.reponomics/template-provenance.json`, or stop and
require operator recovery.

Release-named branches can serve as an emergency compatibility bridge if tags
cannot yet be created in the generated repository, but they should not be the
preferred archive shape. Branches are mutable working refs and can be confused
with supported template lines. Immutable generated-repository tags and GitHub
Releases better match GitHub's release model and the project's provenance
claims.

## Release Notes Shape

Generated template releases should use a stable structure:

```markdown
## Template publication

Template version: reponomics-dashboard vX.Y.Z
Accepted action: reponomics-dashboard-action vA.B.C (<sha>)
Source commit: <source-sha>
Published generated commit: <target-sha>
Generated template tag: reponomics-dashboard-vX.Y.Z

### New-copy template changes

- ...

### Existing dashboard owners

- Existing copied dashboards receive compatible runtime changes through the
  accepted action release.
- If there are no template-surface changes, say: No new-copy template surface
  changes beyond accepting action vA.B.C.

### Provenance

- Source workflow run: <url>
- Template provenance: .reponomics/template-provenance.json
- Artifact attestations: <url>
```

Action releases should remain action-centered, but action release notes can link
to the corresponding template publication after the acceptance release train
completes.

## Provenance Requirements

Moving the public template GitHub Release to the generated repository must not
weaken the current provenance model.

The source repository remains the authority for:

- deciding the template version in `template-contract.yml`;
- recording accepted action version, tag, SHA, and default compatible ref;
- proving compatibility against the current generated template and protected
  minimum compatible template refs;
- building the generated template from a known source commit;
- producing deterministic template release artifacts;
- creating artifact attestations before publication credentials are minted;
- recording source commit and accepted action metadata in generated provenance.
- verifying that the generated repository's previous public template snapshot
  remains reachable before force-pushing a new generated `main`.

The generated repository release is the public release announcement for the
template artifact, not the authority that decides or builds the artifact.

The generated repository remains the direct recovery surface for published
template snapshots. A user or maintainer should be able to inspect or copy a
previously published template from the generated repository tag for that
template version without regenerating it from the source repository.

## Compatibility With ADR 022

This proposal keeps ADR 022's two-step acceptance model:

1. Release the action first.
2. Accept the released action into the template contract after the action tag and
   SHA exist.
3. Publish the generated template only after maintainer approval and release
   gates.

The change is the public release location. ADR 022 currently assumes a
source-repository template release event. This ADR proposes replacing that
public source-repository release with a source approval/evidence event plus a
generated-repository release.

## Consequences

- The Action repository's GitHub Releases page can remain focused on the Action
  product and Marketplace consumers.
- The generated template repository carries the release history for the artifact
  users actually copy.
- Previously published generated template snapshots become directly recoverable
  from generated-repository tags instead of requiring regeneration from the
  source repository.
- Template-only releases have a public home that matches their distribution
  surface.
- Coupled action/template release trains become easier to explain: action
  release in the Action repo, template publication in the Template repo, linked
  by source provenance and accepted action metadata.
- The publication workflow becomes more complex because it must create a release
  in the generated repository after force-publishing the generated tree.
- Release recovery documentation must distinguish source acceptance evidence
  from generated-repository public release state.
- Source-repository tags may still be useful as immutable source anchors, but
  they should not be confused with the user-facing generated template release.

## Migration Sketch

If accepted, implementation should proceed conservatively:

1. Teach the production template publication workflow to create the generated
   repository tag and GitHub Release after the generated tree has been pushed
   and verified.
2. Preserve current template release gates, deterministic artifact packaging,
   and attestations in the source repository.
3. Before force-pushing the generated repository's `main`, verify that the
   current target commit is already reachable from a generated-template release
   tag. If not, create a recovery tag from the current target commit or stop
   before overwriting it.
4. Change the normal trigger from a source-repository published GitHub Release
   to a source tag, merged acceptance commit, workflow run, or other auditable
   source event.
5. Mark any remaining transitional source-repository template releases as
   `--latest=false` while the migration is incomplete.
6. Update `docs/VERSIONING_AND_RELEASE.md`, `.github/workflows/README.md`,
   `docs/BAD_RELEASE_REPONSE_RUNBOOK.md`, and the release-manager skill once
   the workflow behavior changes.
7. Backfill generated-repository release tags or releases only if the historical
   value is worth the risk of confusing source and generated provenance.

## Open Questions

- Should the generated repository tag point only to the generated commit, or
  should there also be an immutable source-repository tag for the acceptance
  commit?
- During migration, should missing generated-repository archive refs be
  backfilled as tags only, or should temporary release-named branches also be
  created for operator convenience?
- Should generated-repository release creation happen in `publish-template.yml`
  or in a follow-up workflow that verifies the publication commit first?
- What is the best durable link format from generated-repository release notes
  to source-repository attestations and workflow artifacts?
- Should GitHub's template repository release feed be advertised to users, or
  should the generated repository README point primarily to a curated release
  train index in the source repository?
- How should failed generated-repository release creation be recovered when the
  generated tree has already been published correctly?

## Non-Goals

- Do not collapse Action and Template SemVer into one version number.
- Do not remove the template acceptance PR approval boundary.
- Do not publish generated templates directly from action release commits when
  accepted action SHA metadata is not yet recorded.
- Do not weaken template release gates, deterministic artifacts, or artifact
  attestations.
- Do not treat the demo repository as a SemVer release surface.
