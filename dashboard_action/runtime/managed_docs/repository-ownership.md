# Repository Ownership

These docs describe generated Reponomics `v0` dashboard repositories. Local workflow edits can change behavior and may move the repository outside what these docs describe.

Reponomics is a GitHub-native traffic and growth dashboard. It collects repository views, clones, referrers, popular paths, and growth counters, stores retained state in GitHub Actions artifacts, and renders static dashboard outputs during workflow runs.

## Thin Repository Model

Generated dashboard repositories stay intentionally thin. The local wrapper at `.github/actions/reponomics/action.yml` calls the configured `reponomics/reponomics-dashboard-action` release.

The copied dashboard repository owns:

- `config.yaml`
- repository secrets and variables
- generated workflow files and job permissions
- workflow schedules
- the `.reponomics/setup-complete` marker
- the configured Reponomics action ref
- retained `dashboard-data` workflow artifacts
- static setup README output
- optional private-repository README dashboard output
- optional managed docs under `docs/reponomics/`

The versioned action owns collection, artifact restore/upload, schema migration, encryption, dashboard rendering, CSV export packaging, key rotation, incident reset behavior, and managed docs payload generation.

## User-Owned Files

`config.yaml` is user-owned. The generated workflows read it but do not silently rewrite it.

Root repository policy files such as `README.md`, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `LICENSE` are owner-owned after the template is copied. Setup may replace the starter README, and private repositories can opt into README dashboard output, but managed docs updates do not own those root files.

## Reponomics-Managed Files

`docs/reponomics/` is the managed documentation namespace. It is refreshed by the generated `Update Docs` workflow when that workflow is enabled and has permission to write.

The manifest at `docs/reponomics/.manifest.json` records the action repository, action version, managed namespace, update timestamp, and file hashes for the managed docs snapshot.

See [Managed Documentation](managed-docs.md) for the write boundary and opt-out behavior.

## Normal Operation

Normal use does not require local Python. Workflows run in GitHub Actions. Self-hosted runners should provide Python `3.11+` and GitHub CLI (`gh`) for setup token validation.

Collect and publish runs are serialized for `main`. A later scheduled run waits for an older collect-and-publish run so retained artifact lineage advances in workflow order.

## Continue

- [Setup](setup.md)
- [Configuration](configuration.md)
- [Workflows](workflows.md)
- [Data and artifacts](data-and-artifacts.md)
