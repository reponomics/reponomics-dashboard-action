# Reponomics Managed Docs

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

> [!WARNING]
> This directory is the default location for Reponomics managed documentation. If `allow_docs_sync` is `true`, local edits in `docs/reponomics/` may be overwritten automatically when docs sync runs. Set `allow_docs_sync: false` before editing if you want to own this directory manually.

The manifest at `docs/reponomics/.manifest.json` records the action version for this managed-docs snapshot.

`config.example.yaml` is the managed starter/reference configuration shape. New template repositories receive it once as root `config.yaml`; later docs sync updates only this managed reference copy. Use it when your repository's active `config.yaml` has been edited and you want to compare it against the current action-bundled example. New keys shown in this managed example are only usable when your copied template workflows and local action wrapper can pass them through; docs sync cannot upgrade old workflow wiring by itself.

Start here:

- [Dashboard repository guide](repository-guide.md)
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
