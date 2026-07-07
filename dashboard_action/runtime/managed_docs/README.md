# Reponomics Managed Docs

These are the action-managed docs for generated Reponomics dashboard repositories in the `v0` beta line. They are written for repository owners who maintain the copied dashboard repository, its GitHub Actions workflows, repository secrets, Pages settings, and retained dashboard artifacts.

`docs/reponomics/.manifest.json` records the action version and file hashes for this managed-docs snapshot.

> [!WARNING]
> Local edits in `docs/reponomics/` may be overwritten when `.github/workflows/update-docs.yml` runs. Disable or delete that workflow before editing this directory manually.

## Start Here

- [Setup](getting-started/setup.md): first-run sequence, setup marker, and the shortest path to a working dashboard.
- [Configuration](getting-started/configuration.md): how to make the main `config.yaml` choices without reading the full reference.
- [Credentials](getting-started/credentials.md): collection tokens, GitHub App mode, and dashboard secrets.
- [Configuration reference](reference/configuration-reference.md): supported keys, defaults, secrets, variables, and rejected combinations.
- [Configuration example](config.example.yaml): managed reference copy of the starter `config.yaml`.

New template repositories receive `config.example.yaml` once as root `config.yaml`. Later docs updates refresh only this managed reference copy. If your active root `config.yaml` is older, compare it with this file before opting into newer keys.

## Concepts

- [Repository ownership](concepts/repository-ownership.md): what the copied repository owns and what the versioned action owns.
- [Managed documentation](concepts/managed-docs.md): how docs updates work, what Reponomics owns, and how to opt out.
- [Data and artifacts](concepts/data-and-artifacts.md): retained state, artifact retention, lineage, CSV export, and offline viewing.
- [Publication](concepts/publication.md): Pages, README metrics, and downloadable dashboard artifacts.

## Operations

- [Workflows](operations/workflows.md): maintainer guide to setup, collection, publishing, diagnostics, updates, rotation, reset, and keepalive.
- [Troubleshooting](operations/troubleshooting.md): Doctor-first checks for setup, collection, publish, Pages, unlock, and mode failures.
- [Maintenance](operations/maintenance.md): scheduled workflow liveness, artifact expiry, auto-doctor cadence, and routine preservation tasks.
- [Upgrades](operations/upgrades.md): action refs, `v0` beta upgrades, full-SHA pinning, and docs update behavior.
- [Workflow contract](reference/workflow-contract.md): strict workflow-mode, permission, artifact, output, and expected-failure reference.

## Security And Privacy

- [Privacy and security](security-privacy/privacy-and-security.md): data modes, artifact visibility, Pages exposure, browser-side limits, and shared-secret boundaries.
- [Dashboard key and recovery](security-privacy/dashboard-key-and-recovery.md): key generation, storage, rotation, lost-key limits, and incident reset.
- [Repository access and trust boundary](security-privacy/trust-boundary.md): collaborator, organization, and public-repository access implications.
- [Vulnerability reporting](security-privacy/vulnerability-reporting.md): private reporting, sensitive support material, and supported beta line.

## Reference

- [Provenance and verification](reference/provenance.md): manifests, attestations, release materials, and local checks.
- [FAQ](reference/faq.md): concise answers that point back to the canonical topic pages.
- [Support](reference/support.md): where to report problems and what diagnostic material to include.

For complete release history, see the [Reponomics Dashboard Action releases](https://github.com/reponomics/reponomics-dashboard-action/releases).
