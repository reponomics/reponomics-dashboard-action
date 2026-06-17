# ADR 022: Action Release Template Acceptance

Date: 2026-06-17

## Status

Accepted

## Context

Reponomics publishes two versioned products:

- `reponomics-dashboard-action`, consumed by existing dashboard repositories through a compatible action ref such as `v0`.
- `reponomics-dashboard`, the generated template copied by new dashboard repositories.

ADR 020 made action releases responsible for proving compatibility with the current generated template and the minimum compatible published template. That gate protects existing copied repositories, but it does not by itself publish a new generated template snapshot.

Every public action release should have a corresponding generated-template release. The template release is the point where the project says: this generated starting point is compatible with, and recommends, the released action version. This matters especially for users whose organization requires SHA-pinned Actions. Those users need template metadata that records the action version/tag/SHA the project accepted for the template snapshot.

The current release model cannot honestly record the final action release SHA inside the same commit that creates the action release. Release Please determines the action release commit, creates the action tag, and then the workflow moves floating refs such as `v0` and `v0.x`. A source file committed before that automation finishes can only predict the release SHA, not record it as observed release evidence.

## Decision

Use a two-step coupled release model for action-triggered template releases.

1. Release the action first.
2. After the action release exists and floating refs have moved, open or update a follow-up template acceptance PR.
3. In that acceptance PR and its eventual merge commit, record the accepted action release metadata:
   - action repository;
   - action version;
   - action release tag;
   - resolved action commit SHA;
   - default compatible action ref, such as `v0`.
4. After maintainer approval and merge, publish the generated template release from the merged template acceptance commit.

The merged template acceptance PR is the auditable statement that the project accepts the released action as the recommended base for the generated template. The generated template should carry that accepted action metadata in provenance or an equivalent generated metadata file.

Action and template releases are class-locked but not version-number-locked:

- action patch release implies template patch release;
- action minor release implies template minor release;
- action/template major release policy is out of scope while the project remains on the `v0` line.

Template-only releases remain allowed. They choose their own SemVer bump based on template impact and do not require a corresponding action release.

## Release Gates

Before the action release, the action candidate must pass against:

- the current generated template; and
- the minimum compatible protected template recorded in `template-contract.yml`.

Before the template publication, the merged template acceptance commit must prove that:

- the recorded action tag resolves to the recorded SHA;
- the default compatible action ref resolves to the accepted action release or an explicitly compatible newer release;
- the generated template builds and verifies from the acceptance commit;
- generated-template smoke and consumer checks pass against the accepted public action release;
- template release artifacts and provenance are deterministic and attestable.

## Consequences

- The generated template can record concrete action release evidence without pretending the release SHA was known before release automation ran.
- The source commit used to publish a template acceptance release will usually differ from the action release commit.
- Users who pin actions by SHA get a clear metadata trail from template version to accepted action version/tag/SHA.
- A failed template acceptance step does not invalidate the action release, but it leaves the release train incomplete until the acceptance PR and template publication succeed.
- Release automation should create or update the template acceptance PR automatically so maintainers do not hand-edit the contract after every action release.
- Branch protection remains the approval boundary: automation proposes the acceptance, but the source-repository template release is created only after the acceptance PR lands on `main`.

## Non-Goals

- Do not require action and template version numbers to match.
- Do not publish a generated template directly from the action release commit when concrete action release SHA metadata must be recorded.
- Do not move `minimum_compatible_template_version` forward unless the release intentionally resets action/template compatibility.
