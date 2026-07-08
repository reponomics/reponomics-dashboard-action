# Reponomics Dashboard Action

The Reponomics Dashboard Action is a special-purpose GitHub action specifically designed to integrate with the Reponomics Dashboard template repository. It serves as the main runtime for the primary features and functionality of Dashboard repositories, which are shipped with workflows that are also designed specifically to consume this action. Although you may find the action to be useful for whatever purpose you deem fit, development and maintenance efforts by the Reponomics organization will be focused exclusively on serving the Dashboard template repository and its users. The two public entities (the action and the template repo) are simply two surfaces of the same product, and neither one has much independent value. If you are interested in creating your own Dashboard repository, you are encouraged to visit the [template repo](https://github.com/reponomics/reponomics-dashboard) and create your own repository based on that template, which is already engineered for the specific purpose of interacting with this action. The Dashboard Action:

- Queries the GitHub API on a regular (by default, daily) cadence to obtain growth and traffic metrics about the repository owner's projects across GitHub.
- Retains and aggregates the collected data in a common CSV format, which it stores in GitHub workflow artifact storage.
- Generates the HTML analytics dashboard that users/owners may elect to serve via GitHub Pages.
- Generates the lightweight Markdown+SVG dashboards that users who own a private repository may elect to publish to their repo's README.
- Handles the encryption and decryption of dashboard artifacts so that data is never exposed in plaintext form. (Those who own a private repo may opt to store the data in plaintext if they wish, relying instead on the privacy boundary offered by GitHub's authentication protocols.)

## Recommended Use

There is only one recommended way to use this action, and that is by way of the free and open-source Reponomics Dashboard template repository. You are free to adapt it to your own purposes as you see fit, but in its current shape, all maintainance efforts will be directed at the officially recommended workflows provided by the Reponomics organization. As mentioned above, these are really two parts of a single product - the Reponomics Dashboard - but for a variety of logistical reasons, it is necessary to split the product into two public surfaces. The action is published to the GitHub marketplace to ensure visibility and accessibility for owners of a dashboard repo, and we do not wish to mislead anyone into thinking it has some other purpose.

For information about the Reponomics Dashboard project, and to view the development repository for this action, you may visit [reponomics-dashboard-action](https://github.com/reponomics/reponomics-dashboard-action). This is also where all issues, bug reports, feature requests, security disclosures, or other communication should be directed.

In what follows, we provide basic information about the inputs and outputs of this composite action - for more detail, and to understand these details in their full context, you are encouraged to visit the repository mentioned above, which has more extensive documentation about this project. 

## Modes

| Mode | Purpose |
| --- | --- |
| `collect` | Collect GitHub data about the owner's GitHub repositories, according to the options and token permissions enabled by the repo owner; merge newly collected data with retained history; upload the data to GitHub's artifact storage for persistence; and manage the cleanup of older artifacts as new data is collected. |
| `publish` | Render the repository data in HTML form and optionally deploy a static HTML page to GitHub Pages. |
| `rotate-key` | Allow the user to change their encryption key by creating a new repository secret, which is then used to re-encrypt the existing data. This is also the way in which users/owners may recover their data using a new encryption secret if they have lost access to the existing secret (assuming that the previous secret is still present as a GitHub secret.)  |
| `incident-reset` | In the event of a compromise of the user/owner's encryption key, allow the key to be rotated, and additionally delete any previously retained artifacts encrypted under the previous secret. |
| `update-docs` | Deliver updated Dashboard documentation to a designated path in the repository, so that users may stay up-to-date and well informed of any new features, bug fixes, or security updates. |
| `doctor` | Check retained artifacts, rendered dashboards, keys, and provide the user with a report summarizing the health of their dashboard - especially useful in the case of debugging any issues encountered. |

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `mode` | Always | `collect` | Runtime mode: `collect`, `publish`, `rotate-key`, `incident-reset`, `update-docs`, or `doctor`. |
| `collection-token` | When using a PAT for `collect` (default case) | `""` | GitHub API token for repository data collection. Template workflows pass `secrets.COLLECTION_TOKEN`. Must have `Administration: Read` privileges to access repository traffic data. |
| `use-github-app` | Not required | `""` | Set to `true` in order to use a personal GitHub App installation token for `collect`, instead of a PAT (advanced usage). |
| `github-token` | Required | `""` | Token used for all internal dashboard-repository operations.. |
| `dashboard-secret` | Required when `data-mode: encrypted` | `""` | Current dashboard/artifact encryption key. In template workflows, stored under `secrets.DASHBOARD_SECRET_DO_NOT_REPLACE`. |
| `dashboard-next-secret` | Required for `rotate-key` and `incident-reset` | `""` | When resetting/rotating a key, this value will be used to re-encrypt the data. |
| `comparison-secret` | Optional `doctor` key check | `""` | Second dashboard key used in `doctor` mode to test a user-held key without changing the main secret. |
| `incident-confirm-mode` | `incident-reset` | `""` | Must be `INCIDENT_RESET_CONFIRMED`. |
| `incident-confirm-purge` | `incident-reset` | `""` | Must be `PURGE_OLD_HISTORY_CONFIRMED`. |
| `incident-confirm-next-secret` | `incident-reset` | `""` | Must be `NEXT_SECRET_CONFIRMED`. |
| `incident-confirm-irreversible` | `incident-reset` | `""` | Must be `IRREVERSIBLE_ACTION_CONFIRMED`. |
| `data-mode` | Required | `""` | `encrypted` or `plaintext`. Public repositories must use `encrypted`. |
| `config-path` | Collection and README rendering | `config.yaml` | Repository selection config path. |
| `retention-days` | Not required | `""` | GitHub Actions artifact retention period, from 14 to 90 days. |
| `publish-pages` | `publish`, `rotate-key` | `""` | Set `false` to render dashboard output without deploying GitHub Pages. Plaintext mode always disables Pages deployment. |
| `artifact-run-id` | Optional publish/doctor restore target | `""` | Workflow run ID whose `dashboard-data` artifact should be restored. Blank restores the latest available artifact. |
| `require-collect-provenance` | Deprecated compatibility only | `false` | Ignored by the runtime. Kept for older generated templates. |
| `generate-readme` | Optional private-repository README dashboard | `""` | Generate README dashboard output and commit it back to the caller repository. Public repositories are rejected. |
| `readme-path` | Optional README output path | `README.md` | Destination path for generated README output. |

## Outputs

| Output | Description |
| --- | --- |
| `tracked-repos` | Comma-separated repositories observed in canonical data. |
| `collected-at` | Latest manifest update timestamp. |
| `data-mode` | Resolved data mode. |
| `publish-pages` | Whether the run publishes the rendered dashboard to GitHub Pages. |
| `readme-updated` | Whether README output changed. |
| `dashboard-updated` | Whether dashboard output changed. |
| `pages-path` | Rendered dashboard directory uploaded to Pages or a downloadable dashboard artifact. |
| `page-url` | Deployed GitHub Pages URL when Pages publication succeeds. |
| `schema-version` | Retained dashboard data artifact schema version. |
| `runtime-version` | Reponomics action runtime version. |
| `retention-days` | Resolved artifact retention period. |
| `update-docs-state` | Managed documentation update state. |
| `docs-action-version` | Action version that generated the local managed documentation. |
| `docs-updated-at` | Timestamp recorded when local managed documentation was last written. |
| `doctor-report-path` | Machine-readable Doctor report path when `mode: doctor` emits one. |

## Permissions

Keep top-level workflow permissions minimal, then grant write permissions only at the job that needs them.

| Job or mode | Typical job permissions | Why |
| --- | --- | --- |
| `collect` | `contents: read`, `actions: write` | Checkout, collect data, upload retained state, and clean up old `dashboard-data` artifacts. |
| `publish` | `contents: write`, `actions: read`, `pages: write`, `id-token: write` | Restore retained state, commit README output when enabled, upload Pages artifacts, and deploy Pages. |
| `rotate-key` | `contents: write`, `actions: read`, `pages: write`, `id-token: write` | Restore retained state, write rotated dashboard output, and publish or upload refreshed dashboard output. |
| `incident-reset` | `contents: read`, `actions: write` | Restore retained state, upload fresh retained state, and purge old workflow runs or fallback artifacts. |
| `doctor` | `contents: read`, `actions: read` | Restore selected artifacts and upload the diagnostic report. |
| `update-docs` | `contents: write` | Commit refreshed managed documentation. |

## Tokens And Secrets

`COLLECTION_TOKEN` is for GitHub repository data collection. For PAT collection, use a fine-grained token with repository `Administration: read` for the repositories listed in `collect.repositories`. It does not need Pages, Actions, or write permissions.

Advanced users may pass a user-owned GitHub App installation token as `collection-token` and set `use-github-app: true`. Reponomics does not provide or operate a shared collection app.

Encrypted mode uses `DASHBOARD_SECRET_DO_NOT_REPLACE`. Save this key outside GitHub secrets, for example in a password manager. Do not overwrite it for normal rotation; set `DASHBOARD_NEXT_SECRET` and run `rotate-key` instead.

## Data Modes

| Mode | Repository visibility | Retained artifact | Pages dashboard |
| --- | --- | --- | --- |
| `encrypted` | public or private | encrypted `dashboard-data.enc` | supported |
| `plaintext` | private only | plaintext retained CSV files | disabled |

In `encrypted` mode, the action will encrypt dashboard data upon collection, using AES-256-GCM and PDKDF2 with 600,000 iterations, and AAD for each "chunk" of encrypted data.

> [!IMPORTANT]
> In order for these encryption protocols to serve their purpose, a high-entropy (256-bit random) encryption key must be generated and supplied _by the repo owner_. 

## Artifacts

| Artifact | Produced by | Contents |
| --- | --- | --- |
| `dashboard-data` | `collect`, `rotate-key`, `incident-reset` | Retained dashboard data, encrypted or plaintext depending on `data-mode`. |
| `html-dashboard-encrypted` | encrypted `publish` or `rotate-key` | Encrypted dashboard HTML and assets, either deployed to Pages or uploaded as a downloadable artifact. |
| `html-dashboard-plaintext` | plaintext `publish` | Downloadable private-repository HTML dashboard artifact. |
| `reponomics-doctor-report` | `doctor` | Machine-readable diagnostic report. |

## Links

- Template repository: <https://github.com/reponomics/reponomics-dashboard>
- Releases: <https://github.com/reponomics/reponomics-dashboard-action/releases>
- Security policy: [SECURITY.md](SECURITY.md)
- Incident response: [docs/INCIDENT_RESPONSE.md](docs/INCIDENT_RESPONSE.md)
- CSV export details: [docs/CSV_EXPORT.md](docs/CSV_EXPORT.md)
- Release and versioning notes: [docs/VERSIONING_AND_RELEASE.md](docs/VERSIONING_AND_RELEASE.md)
