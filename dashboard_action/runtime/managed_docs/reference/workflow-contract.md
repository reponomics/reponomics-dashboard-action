# Workflow Contract

This page summarizes the public contract of the official generated Reponomics `v0` workflows. It is written for copied dashboard repositories, not for people embedding the composite action directly in unrelated workflows.

## Modes And Workflows

| Workflow | Action mode | What it does |
| --- | --- | --- |
| `Setup` | setup scripts only | Validates `config.yaml`, creates `.reponomics/setup-complete`, and replaces the starter README. |
| `Collect and Publish`, collect job | `collect` | Restores prior retained state, collects GitHub data, writes lineage, verifies the upload packet, uploads `dashboard-data`, and cleans up one old superseded retained artifact after upload. |
| `Collect and Publish`, publish job | `publish` | Restores the retained artifact from the current collect run, renders dashboard output, and either deploys encrypted Pages or uploads a downloadable dashboard artifact. |
| `Collect and Publish` with `skip_collect: true` | `publish` | Republishes existing retained data without collecting new GitHub data. |
| `Rotate Key` | `rotate-key` | Decrypts retained state with the current dashboard key, re-encrypts retained state and dashboard output with `DASHBOARD_NEXT_SECRET`, and publishes or uploads refreshed dashboard output. |
| `INCIDENT - Reset` | `incident-reset` | Re-encrypts retained state with `DASHBOARD_NEXT_SECRET`, uploads a fresh `dashboard-data` artifact, then purges old workflow history associated with prior retained artifacts. |
| `Doctor` | `doctor` | Restores dashboard and retained artifacts from a selected workflow run, checks dashboard payloads and keys, and uploads `reponomics-doctor-report`. |
| `Update Docs` | `update-docs` | Refreshes the managed docs under `docs/reponomics/` and commits them when the generated workflow has `contents: write`. |

## Secrets And Tokens

| Name | Used by | Required when |
| --- | --- | --- |
| `COLLECTION_TOKEN` | `collect` | PAT-based collection mode. Use repository `Administration: read` for repositories listed in `collect.repositories`. |
| `COLLECTION_APP_ID` and `COLLECTION_APP_PRIVATE_KEY` | `collect` | Advanced GitHub App collection mode. The workflow mints a short-lived installation token and passes it as `collection-token`. |
| `DASHBOARD_SECRET_DO_NOT_REPLACE` | encrypted `collect`, `publish`, `rotate-key`, `incident-reset`, `doctor` | `data_mode: encrypted`. Do not overwrite this directly for normal rotation. |
| `DASHBOARD_NEXT_SECRET` | `rotate-key`, `incident-reset` | Key rotation and incident reset. Leave it unset during normal collection. |
| `COMPARISON_SECRET` | `doctor` | Optional second key check when you want Doctor to test a user-held key without changing the main dashboard secret. |

The workflow `GITHUB_TOKEN` is passed as `github-token` for artifact and repository operations. It is separate from `COLLECTION_TOKEN`.

## Workflow Permissions

The generated workflows keep top-level permissions at `contents: read` and declare higher permissions on the jobs that need them.

| Job | Required job permissions | Why |
| --- | --- | --- |
| `collect` | `contents: read`, `actions: write` | Checkout, collect data, upload retained state, and clean up old `dashboard-data` artifacts. |
| `publish` | `contents: write`, `actions: read`, `pages: write`, `id-token: write` | Restore retained state, commit README dashboard output when enabled, upload Pages artifacts, and deploy Pages. |
| `rotate` | `contents: write`, `actions: read`, `pages: write`, `id-token: write` | Restore retained state, write rotated dashboard output, and publish or upload the refreshed dashboard. |
| `incident-reset` | `contents: read`, `actions: write` | Restore retained state, upload a new retained artifact, and purge old workflow runs or fallback artifacts. |
| `doctor` | `contents: read`, `actions: read` | Restore selected dashboard and retained artifacts and upload the diagnostic report. |
| `update-docs` | `contents: write` | Commit refreshed managed documentation. |

Pages publication also requires repository **Settings -> Pages -> Build and deployment -> Source** to be set to **GitHub Actions**. The action verifies this; it does not enable Pages or change the source setting.

## Artifacts And Outputs

| Name | Produced by | Contents |
| --- | --- | --- |
| `dashboard-data` | `collect`, `rotate-key`, `incident-reset` | Retained dashboard data. In encrypted mode this is `.dashboard-data-artifact/dashboard-data.enc`; in plaintext mode it is the registered retained CSV files under `data/`. |
| `html-dashboard-encrypted` | encrypted `publish` or `rotate-key` when Pages is disabled, and as the Pages artifact before deployment | Encrypted dashboard HTML and assets. |
| `html-dashboard-plaintext` | plaintext `publish` | Downloadable private-repository dashboard HTML and assets. Plaintext mode does not publish Pages. |
| `reponomics-doctor-report` | `doctor` | Machine-readable Doctor diagnostics, paired with the workflow summary. |

Action outputs used by generated workflows include `data-mode`, `publish-pages`, `pages-path`, `page-url`, `schema-version`, `runtime-version`, `retention-days`, managed-docs status fields, and `doctor-report-path`.

## Expected Failure Classes

These failures are deliberate runtime behavior:

- `COLLECTION_TOKEN` is missing, expired, outside the configured repository set, or lacks repository `Administration: read`.
- Advanced GitHub App collection is enabled but the app token cannot be minted or does not have access to the collected repositories.
- `data_mode: plaintext` is used in a public repository.
- `data_mode: plaintext` is combined with Pages publication.
- README dashboard publication is enabled in a public repository.
- Pages publication is enabled but repository Pages source is not set to **GitHub Actions**.
- The requested `dashboard-data` artifact is missing, expired, unreadable, from the wrong run, or fails retained-lineage validation.
- The dashboard key cannot decrypt the retained artifact or the published encrypted dashboard payload.
- `DASHBOARD_NEXT_SECRET` is still set during ordinary collection, which indicates unfinished key rotation.
- `rotate-key` or `incident-reset` is run without the required next key or confirmation inputs.

When one of these occurs, run **Doctor** when artifacts exist, then use the workflow summary and `reponomics-doctor-report` as the first support evidence.

For the maintainer-oriented workflow overview, see [Workflows](../operations/workflows.md).
