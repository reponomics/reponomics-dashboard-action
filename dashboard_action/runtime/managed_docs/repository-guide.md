# Reponomics Dashboard Repository Guide

These docs describe the official generated Reponomics `v0` workflows. Local workflow edits can change behavior.

Reponomics is a GitHub-native traffic and growth dashboard. It collects repository views, clones, referrers, popular paths, and growth counters, then renders static dashboard output during workflow runs.

Generated dashboard repositories stay intentionally thin. The local wrapper at `.github/actions/reponomics/action.yml` calls the configured `reponomics/reponomics-dashboard-action` release. That action owns collection, artifact restore/upload, schema migration, encryption, README rendering, HTML dashboard rendering, CSV export packaging, key rotation, incident reset behavior, and managed docs updates.

Normal use does not require local Python. Workflows run in GitHub Actions. Self-hosted runners should provide Python `3.11+` and GitHub CLI (`gh`) for setup token validation.

## Repository Model

Your dashboard repository owns:

- `config.yaml`
- repository secrets and variables
- workflow schedules and job permissions
- the `.reponomics/setup-complete` marker
- the configured Reponomics action ref
- retained `dashboard-data` workflow artifacts
- static setup README output
- optional private-repository README dashboard output
- optional managed docs under `docs/reponomics/`

Collected data is not stored in git unless you enable `publish_readme_dashboard` in a private repository. The retained data store is the `dashboard-data` GitHub Actions artifact.

Collect and publish runs are serialized for `main`. A later scheduled run waits for an older collect-and-publish run so retained artifact lineage advances in workflow order.

## First Setup

1. Edit and commit `config.yaml`.
2. Add the required secrets for the selected mode.
3. Run **Actions -> Setup -> Run workflow**.
4. If Pages is enabled, set **Settings -> Pages -> Build and deployment -> Source** to **GitHub Actions**.
5. Run **Actions -> Collect and Publish -> Run workflow** once if you want the first dashboard before the next schedule.

Setup validates `config.yaml`, checks required secrets, writes `.reponomics/setup-complete`, and replaces the starter root README with either a generic post-setup notice or a private-repository README dashboard.

The setup marker is empty and non-secret. Deleting it pauses generated operational workflows until setup writes it again.

## Configuration Ownership

`config.yaml` is user-owned. Generated workflows read it but do not silently rewrite it.

`docs/reponomics/config.example.yaml` is the managed reference shape. Docs updates may refresh that reference copy, but they do not upgrade your active root `config.yaml` or old workflow wiring.

Use `collect.repositories` for repositories whose history Reponomics should retain. Use `publish.repositories` for the subset, up to 8 repositories, shown in README and Pages dashboards.

See [Configuration Reference](configuration.md) for supported keys.

## Collection Credentials

`COLLECTION_TOKEN` is only for repository data collection. It does not need Pages, Actions, or write permissions.

For the default PAT mode, create a fine-grained personal access token for the owner whose repositories should be collected and grant repository `Administration: read` for the repositories listed in `collect.repositories`.

This template currently supports one collection credential. Fine-grained PATs are scoped to one GitHub resource owner. If one dashboard must collect repositories across multiple users or organizations, use a classic PAT with `repo` scope where the relevant organizations allow it, and treat that broader token accordingly.

Advanced option: set `use_github_app: true` to use a user-owned GitHub App installation token. Reponomics does not provide or operate a shared collection app. Store `COLLECTION_APP_PRIVATE_KEY` as a repository secret and `COLLECTION_APP_ID` as a repository variable or secret.

## Data Modes

`data_mode` controls how retained artifacts and dashboard output are stored.

| Mode | Retained artifact | Hosted dashboard | Secret |
| --- | --- | --- | --- |
| `encrypted` | encrypted `dashboard-data.enc` | optional encrypted Pages deployment | `DASHBOARD_SECRET_DO_NOT_REPLACE` |
| `plaintext` | plaintext retained CSV files | disabled | none |

Use `encrypted` by default. It is required for public repositories and hosted Pages dashboards.

Use `plaintext` only in private repositories where repository and Actions artifact access are the intended boundary. Public repositories reject plaintext mode. Public repositories also reject README dashboard generation so metrics are not committed to public git history.

See [Privacy Configuration Matrix](privacy-configuration-matrix.md) and [Security Info](security-info.md).

## Storage And Artifacts

`collect` restores the prior `dashboard-data` artifact, collects current GitHub data, merges retained CSV history, verifies lineage, uploads a successor artifact, then cleans up one older superseded artifact when safe.

`publish` restores retained data, migrates it to the runtime's current schema, renders dashboard output, and either deploys encrypted Pages output or uploads a downloadable dashboard artifact.

`rotate-key` and `incident-reset` both restore retained encrypted state and write a fresh encrypted successor. Use `rotate-key` for normal rotation. Use `incident-reset` only for suspected key exposure after making the dashboard repository private and disabling exposed Pages output.

`artifact_retention_days` controls how long each artifact remains downloadable if no successor is uploaded. It is not the dashboard history window. Retained CSV history can keep growing as long as scheduled collection keeps restoring the current artifact and uploading the next one before expiry.

## GitHub Pages

For a hosted encrypted dashboard, set **Settings -> Pages -> Build and deployment -> Source** to **GitHub Actions**. The publish workflow verifies that setting during deployment, but it does not enable Pages or change the source.

Unless your GitHub plan provides Pages access controls, a GitHub Pages site is reachable on the internet even when the repository is private. Use `data_mode: encrypted` for hosted dashboards that should not disclose metrics without the dashboard key.

## CSV Export And Offline Viewing

Encrypted dashboards include an `Export CSV` control after unlock. The browser downloads an encrypted export asset, decrypts it locally with the dashboard key, verifies SHA-256 digests, and downloads a ZIP of retained CSV files. Plaintext CSV is not uploaded back to GitHub during export.

For plaintext retained data, download the `dashboard-data` artifact directly.

The generated HTML dashboard is not committed to the repository. To view an encrypted dashboard offline, download the dashboard artifact from a successful workflow run, extract it, and open `index.html` with the same dashboard key. If a browser blocks local `file://` fetches, serve the extracted directory over local HTTP.

## Scheduled Workflow Liveness

GitHub may disable scheduled workflows in inactive public repositories. The generated keepalive workflow runs monthly, commits `.reponomics/keepalive.md`, and tries to create one persistent data safety reminder issue.

If scheduled workflows stop, download the latest `dashboard-data` artifact before it expires, then re-enable workflows from the Actions tab.

## Where To Continue

- First-run checklist: [Dashboard Essentials](dashboard-essentials.md)
- Workflow details: [Generated Workflow Contract](workflow-contract.md)
- Privacy and repository access: [Privacy And Artifacts](privacy-and-artifacts.md) and [Repository Access And Trust Boundary](trust-boundary.md)
- Release and verification materials: [Provenance And Verification Materials](provenance.md)
