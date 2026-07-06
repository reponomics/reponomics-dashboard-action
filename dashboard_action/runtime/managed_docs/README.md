# Reponomics Managed Docs

These are the action-managed docs for Reponomics dashboard repositories in the `v0` beta line. They are written for early adopters who are comfortable with GitHub Actions, repository settings, secrets, and maintainer workflows.

`docs/reponomics/.manifest.json` records the action version and file hashes for this managed-docs snapshot.

> [!WARNING]
> Local edits in `docs/reponomics/` may be overwritten when `.github/workflows/update-docs.yml` runs. Disable or delete that workflow before editing this directory manually.

## Start And Setup

- [Dashboard essentials](dashboard-essentials.md): first-run checklist and the decisions most users need before setup.
- [Dashboard repository guide](repository-guide.md): repository model, data flow, tokens, storage, Pages, and CSV export.
- [Configuration reference](configuration.md): supported `config.yaml` keys and rejected combinations.
- [Configuration example](config.example.yaml): managed reference copy of the starter `config.yaml`.

New template repositories receive `config.example.yaml` once as root `config.yaml`. Later docs updates refresh only this managed reference copy. If your active root `config.yaml` is older, compare it with this file before opting into newer keys.

## Workflows And Operations

- [Generated workflow contract](workflow-contract.md): workflow modes, secrets, permissions, artifacts, outputs, and expected failures.
- [Troubleshooting](troubleshooting.md): first checks for setup, collection, publish, Pages, and unlock failures.
- [Upgrade notes](upgrade.md): action refs, `v0` beta upgrades, and full-SHA pinning.
- [Support guidance](support.md): where to report problems and what diagnostic material to include.

## Security And Privacy

- [Security guidance](security.md): vulnerability reporting, supported beta line, and data-loss boundaries.
- [Secure dashboard key](secure-dashboard-key.md): key generation, storage, rotation, and recovery limits.
- [Security info](security-info.md): encryption model, key strength, recovery, and trust boundaries.
- [Privacy configuration matrix](privacy-configuration-matrix.md): encrypted vs plaintext behavior by repository visibility.
- [Privacy and artifacts](privacy-and-artifacts.md): where dashboard data is stored and who can read artifacts.
- [Repository access and trust boundary](trust-boundary.md): collaborator, organization, and public-repository access implications.

## Verification And Background

- [Provenance and verification materials](provenance.md): manifests, attestations, release materials, and local checks.
- [FAQ](faq.md): concise answers for common beta-user questions.

For complete release history, see the [Reponomics Dashboard Action releases](https://github.com/reponomics/reponomics-dashboard-action/releases).
