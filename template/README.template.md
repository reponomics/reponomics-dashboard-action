# Reponomics Dashboard

> [!NOTE]
> This template is on the `v0` external beta line. These instructions describe the official generated workflows; after copying the template, the repository owner may modify them.

Welcome to your personal repository analytics dashboard. Reponomics helps maintainers collect GitHub traffic and growth data, keep that data in their own repository's workflow artifacts, and render a dashboard without involving any third-party services.

Once you copy the template, the repository is yours. The generated workflows use your credentials, your repository secrets, and the action ref configured by the local wrapper at `.github/actions/reponomics/action.yml`. This README helps you configure collection, data storage, and dashboard publication before the first setup run. Setup may replace this file with a shorter post-setup README, and private repositories can later opt into a generated README dashboard for a quick overview of your repo metrics.

This repository contains a number of workflow files that integrate with the Reponomics Dashboard GitHub Action in order to provide the functionality that makes the dashboard possible. The workflows collects GitHub traffic and growth data, stores retained state in GitHub Actions artifacts, and renders optional dashboard outputs through GitHub Actions. The action itself is imported into all of the necessary workflows as a local action at a single path:

```yaml
uses: ./.github/actions/reponomics
```

This allows you to manage the version of the action uniformly in a single place. By default the action is configured to follow the current major line (`@v0`), so that new features, bug fixes, and security patches will flow automatically into your repo. If your organization requires full-SHA-pinned Actions, use `docs/reponomics/.manifest.json` to find the action repository and action version for this template snapshot, resolve that version tag to a commit SHA, and update the nested Reponomics `uses:` line in `.github/actions/reponomics/action.yml` only if you intend to own manual action updates. Organization-wide SHA policies may also require pinning other workflow action refs, such as `actions/checkout`, in the generated workflow files.

## Get Started

Before proceeding, please read through this README file, and take a moment to review some of the other documentation in the repository, in particular those pertaining to privacy, security, and secure key generation. Then proceed as follows:

### 1. Enter your preferences in `config.yaml`. REQUIRED: `encrypted` or `plain` data-mode; whether to publish a Pages dashboard and/or a README dashboard; which repositories to track and publish in your dashboard.
### 2. Create the following: (a) a Personal Access Token with `Administration: read` permissions for every repository that you would like to include in collection - store that as a repo secret named `COLLECTION_TOKEN`; (b) a high-entropy encryption key (`openssl rand --hex 32`) - store that as `DASHBOARD_SECRET_DO_NOT_REPLACE`.
### 3. If you want a Pages dashboard (must choose `encrypted` data-mode): Go to Settings > Pages > Build and Deployment - select Source: GitHub Actions.
### 4. Go to the Actions tab, click on the `Setup` workflow from the side, then dispatch the workflow.
### 5. If everything passes, you can go ahead and run the `Collect and Publish` workflow manually to start gathering some data. Within minutes you'll have two weeks of traffic data to admire. Click over to your Pages site and use your encryption key to unlock the vault.

Setup validates `config.yaml`, creates the empty `.reponomics/setup-complete` marker, and replaces this README. Operational workflows are present before setup but do no work until that marker exists. Setup does not collect traffic immediately. Collection runs on the configured schedule and stores retained data in the `dashboard-data` Actions artifact; run **Collect and Publish** manually after setup when you want the first dashboard without waiting for the schedule.

The `.reponomics/setup-complete` marker is an empty, non-secret file and does not contain dashboard data. It is a git-tracked switch that tells the generated workflows the repository has completed initial setup. If it is deleted, collect, publish, rotate-key, doctor, incident-reset, update-docs, and keepalive workflows will treat setup as incomplete and skip their normal work until setup writes the marker again. If you intentionally complete `config.yaml` and choose to manage setup manually, recreating the empty marker is acceptable; normal setup writes it for you.

## Configuration

`config.yaml` is owned by this repository. Reponomics reads it during setup and workflow runs but does not silently rewrite it. The setup fields without defaults must be filled before setup can proceed:

```yaml
# required fields below
i_have_read_the_readme:   # true/false
data_mode:                # encrypted/plaintext
publish_pages_dashboard:  # true/false
publish_readme_dashboard: # true/false (must be false for public repos)
###

artifact_retention_days: 90 # integer between 14-90

auto_doctor_every_n_days: 0 # 0 disables; otherwise integer between 1-30

collect:
  repositories:
    # - repo-name
    # - other-owner/repo-name

publish:
  repositories:
    # - repo-name

# Advanced: set to `true` if you wish to use your own GitHub App installation token.
use_github_app: false
```

The template starts with `artifact_retention_days: 90`, `use_github_app: false`, and `auto_doctor_every_n_days: 0`; these are validated by setup and workflow runs. Set `auto_doctor_every_n_days` to `1` through `30` to check the marker and run doctor as part of the collect-and-publish cadence when that many UTC days have elapsed since the last successful auto-doctor.

Add repositories to `collect.repositories` when you want Reponomics to keep history for them. Add up to 8 of those same repositories to `publish.repositories` when you want them shown in the README and Pages dashboards. For more detail, see [Configuration](docs/reponomics/configuration.md) and [Workflows](docs/reponomics/workflows.md).

### Token Scope And Repository Owners

Repository entries can use bare names such as `api` for repositories owned by the dashboard repository owner. Use full `owner/repo` names when a dashboard is configured against repositories owned by another user or organization. The token you choose still controls which owners can actually be collected.

Fine-grained personal access tokens are scoped to one GitHub resource owner. If your dashboard only tracks repositories under one user or one organization, a fine-grained token with repository `Administration: read` is the preferred path.

This template currently supports one collection credential. If one dashboard needs to track repositories under multiple users or organizations, the fine-grained token flow is not the right fit for the current single-token setup. Use a classic PAT with `repo` scope where the relevant organizations allow it. Classic PATs are broader and can access repositories your GitHub account can access, so use this fallback only when the dashboard really needs to span owners.

## Privacy And Output

The canonical store is the `dashboard-data` Actions artifact.

- `encrypted` stores retained data encrypted with `DASHBOARD_SECRET_DO_NOT_REPLACE`.
- `plaintext` stores retained CSV files directly in the artifact and is rejected in public repositories.
- Hosted encrypted dashboard publication is optional and requires GitHub Pages to use GitHub Actions as the deployment source.
- Plain-mode HTML dashboards are private-repository downloadable artifacts only and are not published to Pages.
- Metric README dashboard generation is only available in private repositories.
- `artifact_retention_days` configures the retention period for dashboard data workflow artifacts, in the event that there is an interruption in the collection routine. Normally, only a small number of data artifacts are stored in the repository's artifact storage, and each time collection runs, the oldest artifact is deleted. `artifact_retention_days` can be thought of as the number of days GitHub should save your backup artifacts if the repository workflows stop functioning, credentials expire, etc.

For the one-minute setup checklist, see [Setup](docs/reponomics/setup.md). If a workflow fails, start with [Troubleshooting](docs/reponomics/troubleshooting.md). For publication choices, see [Publication](docs/reponomics/publication.md). For data-mode, privacy, and repository access tradeoffs, see [Privacy And Security](docs/reponomics/privacy-and-security.md). Common questions are answered in the [FAQ](docs/reponomics/faq.md).

## Managed Docs

Reponomics updates action-managed local documentation under `docs/reponomics/` after successful collect-and-publish runs so local guidance matches the action version this repository runs. It writes only that namespace and commits with `[skip ci]`. If you choose to own that directory yourself, disable or delete `.github/workflows/update-docs.yml` before editing it.

The generated repository ships this setup README as `README.backup.md` before setup writes the shorter post-setup README. That backup is user-owned historical context; it is not managed by docs update.
