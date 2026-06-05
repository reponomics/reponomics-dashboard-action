# ADR 015: Extreme Recovery Repository Deletion And Reseeding

Date: 2026-06-05

## Status

Accepted

## Context

`incident-reset` is the normal emergency response for suspected dashboard-key
exposure. It restores the latest retained `dashboard-data` artifact, decrypts
it with the old key, re-encrypts it with `DASHBOARD_NEXT_SECRET`, uploads a
fresh retained artifact, and only then purges older GitHub-hosted
dashboard-data history.

For severe incidents, this may still be an unsatisfying boundary. A repository
can contain many operational surfaces beyond current Actions artifacts:

- old workflow runs and logs
- Pages output that may already have been fetched
- cached browser or CDN copies
- workflow configuration history
- collaborator access history
- local downloads outside GitHub's control

When the operator no longer trusts the repository as a control plane, the
cleanest recovery boundary is not deeper in-place cleanup. It is a new dashboard
repository seeded from a verified retained data artifact.

## Decision

Treat repository deletion and fresh-repository reseeding as the extreme recovery
policy.

The recommended severe-incident sequence is:

1. Make the old dashboard repository private and disable any published Pages
   dashboard.
2. Run `incident-reset` to produce a retained artifact encrypted with a new
   dashboard key.
3. Download and independently preserve the new encrypted `dashboard-data`
   artifact.
4. Record the artifact digest and the expected dashboard-data manifest digest
   once canonical artifact lineage is implemented.
5. Delete the old dashboard repository if the operator wants a clean GitHub
   control-plane boundary.
6. Create a fresh dashboard repository from the template.
7. Re-seed the fresh repository from the preserved encrypted artifact through a
   dedicated rehydrate workflow.

The preferred future rehydrate mode is `rehydrate-from-private-repo`.

In that model:

- The preserved encrypted seed is stored in a temporary private repository.
- The new dashboard repository runs a rehydrate workflow with a token that has
  `contents: read` access to the seed repository and write access only where
  required to upload the new repository's `dashboard-data` artifact.
- The workflow downloads the seed, verifies the expected digest, verifies the
  canonical artifact manifest when available, and uploads the seed as the new
  repository's canonical retained artifact.
- After the new repository verifies and publishes successfully, the temporary
  seed repository should be deleted or access-restricted.

This ADR does not make rehydrate a current action contract. It accepts the
policy direction so incident-response documentation, artifact-lineage work, and
future workflow design share the same recovery model.

## Plaintext Mode

`privacy-mode: plain` is different because the retained `dashboard-data`
artifact is not encrypted. Plain mode already treats private repository and
workflow-artifact access as the privacy boundary.

For plain mode, repository deletion can still be useful when the operator wants
to reset the dashboard control plane, remove workflow history, or reduce stale
artifact/log surfaces. It is not a cryptographic remediation for exposed data:
anyone who already downloaded the plaintext artifact or had repository read
access may already have the retained CSV data.

A future plain-mode rehydrate path may still use `rehydrate-from-private-repo`,
but the seed repository must be private and tightly access-controlled because
the seed contains plaintext retained CSV files. Digest verification remains
important for integrity and lineage, but it does not provide confidentiality.

## Rationale

This policy keeps three recovery levels distinct:

- `rotate-key`: routine continuity when the old key remains trusted enough to
  recover retained data.
- `incident-reset`: emergency rekey plus GitHub-hosted history purge when the
  key may be exposed but the repository can remain the control plane.
- repository deletion plus re-seeding: extreme recovery when the repository
  itself should no longer be treated as the durable control plane.

The private-repository seed model is preferable to gist-based transfer because
it preserves GitHub access controls and avoids relying on public raw-file URLs
for sensitive retained data. Advanced operators can still use release assets or
manual downloads for one-off recovery, but the product-supported path should be
private-repository based and digest-verified.

## Consequences

- Rehydrate should be designed as an explicit operator workflow, not as a hidden
  side effect of setup or collect.
- Canonical artifact lineage becomes more important because the rehydrate
  workflow needs a digest and manifest to verify the seed.
- The action should avoid promising that incident reset recalls data already
  downloaded, cached, or served.
- Documentation should present repository deletion as an extreme option, not as
  the normal incident path.

## Alternatives Considered

### 1) In-place cleanup only

Pros:
- no new repository setup
- simpler user journey

Cons:
- does not reset repository-level control-plane trust
- cannot address old Pages/cache/download surfaces
- may spend time deleting old workflow history when repository deletion would
  be cleaner

### 2) Private gist seed

Pros:
- lightweight file transfer
- familiar to advanced GitHub users

Cons:
- gist is effectively another repository with different UX and access semantics
- raw gist URLs can encourage a public-link mental model
- less aligned with repository-scoped GitHub Actions permissions

### 3) Draft release asset seed

Pros:
- supports private assets in private repositories
- can handle larger files

Cons:
- operationally advanced
- poor fit for ordinary template users
- harder to explain than a temporary private seed repository

## Non-Goals

This ADR does not implement:

- `rehydrate-from-private-repo`
- seed repository creation or deletion
- seed artifact schema changes
- user-facing repo deletion automation
- guarantees about data already downloaded or cached outside GitHub
