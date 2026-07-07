# Configuration Reference

These options apply to the official generated Reponomics `v0` workflows. Local workflow edits can change behavior.

For configuration concepts and recommended choices, start with [Configuration](configuration.md).

`config.yaml` is the active repository configuration. Reponomics reads it during setup, collection, publication, rotation, incident reset, Doctor, and docs updates.

`docs/reponomics/config.example.yaml` is the managed reference copy. Docs updates refresh that reference, but they do not rewrite your active root `config.yaml`.

## Required Choices

These fields must be explicit in `config.yaml`.

| Key | Type | Meaning |
| --- | --- | --- |
| `i_have_read_the_readme` | boolean | Set `true` after reading the setup README. It is not a legal agreement. |
| `data_mode` | `encrypted` or `plaintext` | Controls retained artifact and dashboard-output storage. |
| `publish_pages_dashboard` | boolean | Publishes an encrypted HTML dashboard through GitHub Pages when `true`. |
| `publish_readme_dashboard` | boolean | Publishes a markdown/SVG README dashboard when `true`; private repositories only. |
| `collect.repositories` | list | Repositories whose history Reponomics should collect and retain. |
| `publish.repositories` | list | Repositories rendered in README and Pages dashboards; must be a subset of `collect.repositories` and at most 8 entries. |

Repository entries may be bare names such as `api`, which resolve to the dashboard repository owner, or full names such as `other-owner/api`.

## Optional Choices

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `artifact_retention_days` | integer `14` to `90` | `90` | GitHub Actions artifact expiry for each uploaded artifact. |
| `use_github_app` | boolean | `false` | Uses a user-owned GitHub App installation token for collection. |
| `auto_doctor_every_n_days` | integer `0` to `30` | `0` | Runs Doctor during collect-and-publish when at least this many UTC days have elapsed since the last successful auto-doctor. |

`artifact_retention_days` is not the dashboard history window. Retained CSV history can keep accumulating as long as each run restores the current `dashboard-data` artifact and uploads its successor before expiry.

## Secrets And Variables

| Name | Type | Required when |
| --- | --- | --- |
| `COLLECTION_TOKEN` | repository secret | Default PAT-based collection mode. |
| `COLLECTION_APP_PRIVATE_KEY` | repository secret | `use_github_app: true`. |
| `COLLECTION_APP_ID` | repository variable or secret | `use_github_app: true`. |
| `DASHBOARD_SECRET_DO_NOT_REPLACE` | repository secret | `data_mode: encrypted`. |
| `DASHBOARD_NEXT_SECRET` | repository secret | Key rotation or incident reset only. Leave unset during normal collection. |

For PAT mode, use a fine-grained token with repository `Administration: read` for the repositories in `collect.repositories`. If collection spans multiple GitHub resource owners and fine-grained PAT scope is too narrow, use a classic PAT only where the relevant organizations allow it.

## Rejected Configurations

The generated workflows reject these states:

- `data_mode: plaintext` in a public repository.
- `data_mode: plaintext` with `publish_pages_dashboard: true`.
- `publish_readme_dashboard: true` in a public repository.
- `publish.repositories` containing a repository not listed in `collect.repositories`.
- `publish.repositories` containing more than 8 repositories.

Pages publication also requires repository **Settings -> Pages -> Build and deployment -> Source** to be set to **GitHub Actions**.

## Related Topics

- [Configuration](configuration.md)
- [Publication](publication.md)
- [Privacy and security](privacy-and-security.md)
