# Reponomics Managed Docs

> [!NOTE]
> These docs describe the official Reponomics generated workflows for the `v0` external beta. Repository owners can modify their copies; modified workflows may behave differently from what these docs describe.

> [!WARNING]
> This directory is the default location for Reponomics managed documentation. Local edits in `docs/reponomics/` may be overwritten when the generated `update-docs` workflow runs. Disable or delete `.github/workflows/update-docs.yml` before editing if you want to own this directory manually.

The manifest at `docs/reponomics/.manifest.json` records the action version for this managed-docs snapshot.

`config.example.yaml` is the managed starter/reference configuration shape. New template repositories receive it once as root `config.yaml`; later update-docs runs update only this managed reference copy. Use it when your repository's active `config.yaml` has been edited and you want to compare it against the current action-bundled example. New keys shown in this managed example are only usable when your copied template workflows and local action wrapper can pass them through; update-docs cannot upgrade old workflow wiring by itself.

Start here:

- [Dashboard essentials](dashboard-essentials.md)
- [Troubleshooting](troubleshooting.md)
- [Dashboard repository guide](repository-guide.md)
- [Generated workflow contract](workflow-contract.md)
- [Configuration example](config.example.yaml)
- [Upgrade notes](upgrade.md)
- [Configuration reference](configuration.md)
- [Security info](security-info.md)
- [Secure dashboard key](secure-dashboard-key.md)
- [Privacy configuration matrix](privacy-configuration-matrix.md)
- [Privacy and artifacts](privacy-and-artifacts.md)
- [Repository access and trust boundary](trust-boundary.md)
- [FAQ](faq.md)
- [Provenance and verification materials](provenance.md)
- [Security guidance](security.md)
- [Support guidance](support.md)

For complete release history, see the upstream Reponomics Dashboard Action releases.
