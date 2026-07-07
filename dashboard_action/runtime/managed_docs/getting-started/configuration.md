# Configuration

`config.yaml` is the active dashboard configuration. Reponomics reads it during setup, collection, publication, rotation, incident reset, Doctor, and docs updates. Generated workflows fail closed when a configuration would expose plaintext dashboard data in a public place.

This page explains the decisions. The full key table lives in [Configuration Reference](../reference/configuration-reference.md).

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

- [Credentials](credentials.md)
- [Privacy and security](../security-privacy/privacy-and-security.md)
- [Configuration Reference](../reference/configuration-reference.md)
