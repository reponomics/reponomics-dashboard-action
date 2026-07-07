# Configuration

`config.yaml` is the active dashboard configuration. Reponomics reads it during setup, collection, publication, rotation, incident reset, Doctor, and docs updates. Generated workflows fail closed when a configuration would expose plaintext dashboard data in a public place.

This page explains the decisions. The full key table lives in [Configuration Reference](configuration-reference.md).

## Required Decisions

Set `i_have_read_the_readme: true` after reading the setup README. It is not a legal agreement; it is a guard against running setup with the placeholder file untouched.

Choose `data_mode`:

- `encrypted` is the default recommendation. It encrypts retained data and dashboard payloads with `DASHBOARD_SECRET_DO_NOT_REPLACE`, supports hosted Pages dashboards, and is required in public repositories.
- `plaintext` is only for private repositories where GitHub repository and Actions artifact access are the intended privacy boundary. It stores retained CSV files directly in the `dashboard-data` artifact and does not publish Pages.

Choose publication surfaces:

- `publish_pages_dashboard: true` publishes an encrypted hosted dashboard through GitHub Pages. It requires `data_mode: encrypted` and the repository Pages source set to **GitHub Actions**.
- `publish_readme_dashboard: true` writes markdown/SVG metrics to the repository README. It is private-repository only because the output is committed to git history.

Choose repositories:

- `collect.repositories` lists repositories whose history Reponomics should collect and retain.
- `publish.repositories` is the subset, up to 8 repositories, shown in README and Pages dashboards.

Repository entries may be bare names such as `api`, which resolve to the dashboard repository owner, or full names such as `other-owner/api`.

## Optional Settings

`artifact_retention_days` controls how long each uploaded workflow artifact remains downloadable if no successor artifact is uploaded. It is not the dashboard history window.

`auto_doctor_every_n_days` controls whether Collect and Publish periodically invokes Doctor after successful publication. Use `0` to disable it.

`use_github_app` switches collection from PAT mode to a user-owned GitHub App installation token. Reponomics does not provide a shared collection app.

## Credentials

Reponomics uses separate credentials for collection, repository workflow operations, and encrypted dashboard access.

`COLLECTION_TOKEN` is only for repository data collection. It does not need Pages, Actions, or write permissions. For the default PAT mode, create a fine-grained personal access token for the owner whose repositories should be collected and grant repository `Administration: read` for the repositories listed in `collect.repositories`.

Fine-grained PATs are scoped to one GitHub resource owner. If one dashboard must collect repositories across multiple users or organizations, use a classic PAT with `repo` scope where the relevant organizations allow it, and treat that broader token accordingly.

Advanced GitHub App mode uses a user-owned app installation token. Store `COLLECTION_APP_PRIVATE_KEY` as a repository secret and `COLLECTION_APP_ID` as a repository variable or secret. The generated workflow mints a short-lived installation token and passes that token to the Reponomics action as the collection credential.

Encrypted mode requires `DASHBOARD_SECRET_DO_NOT_REPLACE`. Store the same key in a password manager before saving it as a repository secret, because GitHub secrets cannot show the original value later. Key generation, rotation, and recovery limits are covered in [Dashboard Key And Recovery](dashboard-key-and-recovery.md).

The workflow `GITHUB_TOKEN` is separate from the collection credential. Generated workflows use it for checkout, artifact operations, README commits, Pages deployment, managed docs commits, and incident-reset cleanup according to each job's declared permissions.

## Configuration Ownership

Your root `config.yaml` is user-owned. The generated workflows read it but do not silently rewrite it.

`docs/reponomics/config.example.yaml` is the managed reference shape. Docs updates may refresh that reference copy, but they do not upgrade your active root `config.yaml` or old workflow wiring.

## Rejected States

The generated workflows reject these states:

- `data_mode: plaintext` in a public repository.
- `data_mode: plaintext` with `publish_pages_dashboard: true`.
- `publish_readme_dashboard: true` in a public repository.
- `publish.repositories` containing a repository not listed in `collect.repositories`.
- `publish.repositories` containing more than 8 repositories.

Pages publication also requires repository **Settings -> Pages -> Build and deployment -> Source** to be set to **GitHub Actions**.

## Continue

- [Privacy and security](privacy-and-security.md)
- [Configuration Reference](configuration-reference.md)
- [Workflows](workflows.md)
