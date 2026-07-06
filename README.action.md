# Reponomics Dashboard Action

Collect GitHub repository traffic and growth data, retain it in workflow artifacts, and render Reponomics dashboard outputs from GitHub Actions.

Most users should start from the [Reponomics Dashboard template](https://github.com/reponomics/reponomics-dashboard). The template supplies the workflows, configuration file, and managed docs that call this action correctly. This README documents the action runtime for Marketplace-style review, generated-template maintainers, and advanced users wiring the action directly.

> [!NOTE]
> The pre-wide-release beta uses the `v0` action line. The generated template follows that compatible line. The direct workflow examples below pin the current `v0.32.0` release SHA; replace it with a newer release SHA when you upgrade.

## What It Does

- Collects repository views, clones, referrers, popular paths, growth counters, and community-health profile signals from the GitHub API.
- Retains dashboard history in a `dashboard-data` workflow artifact instead of committing retained CSV data to git.
- Renders encrypted or plaintext HTML dashboard artifacts.
- Optionally deploys encrypted dashboard output through GitHub Pages.
- Optionally commits a private-repository README metrics dashboard.
- Rotates encrypted dashboard keys and supports incident reset for suspected key exposure.
- Refreshes Reponomics-managed local docs in generated dashboard repositories.
- Runs Doctor diagnostics against retained data and rendered dashboard artifacts.

## Recommended Use

Create a repository from the [dashboard template](https://github.com/reponomics/reponomics-dashboard), edit `config.yaml`, add the required secrets, and run the generated setup workflow.

Use this action directly only if you are prepared to own the surrounding workflow contract: checkout, job permissions, secrets, Pages settings, artifact retention, scheduling, setup gating, and repository configuration.

## Modes

| Mode | Purpose |
| --- | --- |
| `collect` | Collect GitHub data, merge retained history, upload `dashboard-data`, and clean up one older superseded retained artifact when safe. |
| `publish` | Restore retained data and render dashboard output; deploy encrypted Pages output or upload a downloadable dashboard artifact. |
| `rotate-key` | Re-encrypt retained state and dashboard output with `dashboard-next-secret`. |
| `incident-reset` | Re-encrypt retained state after suspected key exposure and purge old workflow history associated with prior retained artifacts. |
| `update-docs` | Refresh Reponomics-managed docs under `docs/reponomics/` in generated dashboard repositories. |
| `doctor` | Check retained artifacts, rendered dashboards, keys, and upload `reponomics-doctor-report`. |

## Minimal Example

```yaml
name: Reponomics Collect

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  collect:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      actions: write
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6.0.3

      - uses: reponomics/reponomics-dashboard-action@4dc56246357cb60605cc7169e8df115222e81e92 # v0.32.0
        with:
          mode: collect
          collection-token: ${{ secrets.COLLECTION_TOKEN }}
          github-token: ${{ github.token }}
          dashboard-secret: ${{ secrets.DASHBOARD_SECRET_DO_NOT_REPLACE }}
          data-mode: encrypted
          config-path: config.yaml
          retention-days: "90"
```

## Publish Example

```yaml
jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      actions: read
      pages: write
      id-token: write
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6.0.3

      - uses: reponomics/reponomics-dashboard-action@4dc56246357cb60605cc7169e8df115222e81e92 # v0.32.0
        with:
          mode: publish
          github-token: ${{ github.token }}
          dashboard-secret: ${{ secrets.DASHBOARD_SECRET_DO_NOT_REPLACE }}
          data-mode: encrypted
          publish-pages: "true"
          generate-readme: "false"
```

For Pages deployment, the repository Pages source must already be set to **GitHub Actions**. The action verifies that setting; it does not enable Pages for you.

## Inputs

| Input | Required when | Default | Description |
| --- | --- | --- | --- |
| `mode` | Always | `collect` | Runtime mode: `collect`, `publish`, `rotate-key`, `incident-reset`, `update-docs`, or `doctor`. |
| `collection-token` | `collect` with PAT collection | `""` | GitHub API token for repository data collection. Template workflows pass `secrets.COLLECTION_TOKEN`. |
| `use-github-app` | Optional collect mode | `""` | Set `true` when `collection-token` is a user-owned GitHub App installation token. |
| `github-token` | `collect`, `incident-reset`, artifact/repository operations | `""` | Workflow token for artifact cleanup, artifact restore, repository writes, and incident purge operations. |
| `dashboard-secret` | `data-mode: encrypted` | `""` | Current dashboard/artifact encryption key. |
| `dashboard-next-secret` | `rotate-key`, `incident-reset` | `""` | Next dashboard/artifact encryption key. |
| `comparison-secret` | Optional `doctor` key check | `""` | Second dashboard key used by Doctor to test a user-held key without changing the main secret. |
| `incident-confirm-mode` | `incident-reset` | `""` | Must be `INCIDENT_RESET_CONFIRMED`. |
| `incident-confirm-purge` | `incident-reset` | `""` | Must be `PURGE_OLD_HISTORY_CONFIRMED`. |
| `incident-confirm-next-secret` | `incident-reset` | `""` | Must be `NEXT_SECRET_CONFIRMED`. |
| `incident-confirm-irreversible` | `incident-reset` | `""` | Must be `IRREVERSIBLE_ACTION_CONFIRMED`. |
| `data-mode` | Recommended for all modes | `""` | `encrypted` or `plaintext`. Public repositories must use `encrypted`; `plaintext` is private-repository only. |
| `config-path` | Collection and README rendering | `config.yaml` | Repository selection config path. |
| `retention-days` | Optional artifact upload setting | `""` | GitHub Actions artifact retention period, from 14 to 90 days. |
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

Encrypted mode requires a non-empty dashboard key, but this action does not enforce key strength. Use a high-entropy random key for public repositories, Pages dashboards, sensitive metrics, or any threat model that includes offline guessing of downloaded artifacts.

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
