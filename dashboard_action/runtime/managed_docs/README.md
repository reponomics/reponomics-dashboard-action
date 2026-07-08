# Reponomics Managed Docs

These are the action-managed docs for generated Reponomics dashboard repositories in the `v0` beta line. They are written for repository owners who maintain the copied dashboard repository, its GitHub Actions workflows, repository secrets, Pages settings, and retained dashboard artifacts.

`docs/reponomics/.manifest.json` records the action version and file hashes for this managed-docs snapshot.

> [!WARNING]
> Local edits in `docs/reponomics/` may be overwritten when `.github/workflows/update-docs.yml` runs. Disable or delete that workflow before editing this directory manually.

## Start Here

- [Setup](setup.md): first-run sequence, setup marker, and the shortest path to a working dashboard.
- [Configuration](configuration.md): `config.yaml` choices, collection credentials, GitHub App mode, and workflow tokens.
- [Configuration reference](configuration-reference.md): supported keys, defaults, secrets, variables, and rejected combinations.
- [Configuration example](config.example.yaml): managed reference copy of the starter `config.yaml`.

New template repositories receive `config.example.yaml` once as root `config.yaml`. Later docs updates refresh only this managed reference copy. If your active root `config.yaml` is older, compare it with this file before opting into newer keys.

## Concepts

- [Managed documentation](managed-docs.md): how docs updates work and what namespace Reponomics owns.
- [Data and artifacts](data-and-artifacts.md): retained state, artifact retention, lineage, CSV export, and offline viewing.
- [Publication](publication.md): Pages, README metrics, and downloadable dashboard artifacts.

## Operations

- [Workflows](workflows.md): setup, collection, publishing, diagnostics, updates, rotation, reset, keepalive, permissions, artifacts, outputs, and expected failures.
- [Troubleshooting](troubleshooting.md): Doctor-first checks for setup, collection, publish, Pages, unlock, and mode failures.
- [Upgrades](upgrades.md): action refs, `v0` beta upgrades, full-SHA pinning, and docs update behavior.

## Security And Privacy

- [Privacy and security](privacy-and-security.md): data modes, artifact visibility, Pages exposure, browser-side limits, shared-secret boundaries, and repository access.
- [Dashboard key and recovery](dashboard-key-and-recovery.md): key generation, storage, rotation, lost-key limits, and incident reset.
- [Vulnerability reporting](vulnerability-reporting.md): private reporting, sensitive support material, and supported beta line.

## Reference

- [Provenance and verification](provenance.md): manifests, attestations, release materials, and local checks.
- [FAQ](faq.md): concise answers for common beta-user questions.
- [Support](support.md): where to report problems and what diagnostic material to include.

For complete release history, see the [Reponomics Dashboard Action releases](https://github.com/reponomics/reponomics-dashboard-action/releases).
