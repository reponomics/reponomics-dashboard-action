# Configuration Reference

> [!NOTE]
> These docs describe the official Reponomics generated workflows for the `v0` external beta. Repository owners can modify their copies; modified workflows may behave differently from what these docs describe.

> [!NOTE]
> These docs describe how the official generated workflows and action runtime behave. When a configuration is described as rejected or unsupported, that means the generated workflow or action fails, skips publication, or stops setup for that state.

## About

The Reponomics Dashboard template repo uses a pre-defined set of template workflows that invoke the Reponomics Dashboard [public GitHub action](https://github.com/reponomics/reponomics-dashboard-action). Those workflows read `config.yaml` at runtime, validate the selected data-mode and publication settings, then pass the resolved values to the action. For security reasons, invalid or syntactically ill-formed `config.yaml` files will cause the workflow to fail with a notice.

## Setup

To get started, edit `config.yaml`, commit the change, add the required secrets, and run **Actions -> Setup -> Run workflow**. Setup reads `config.yaml`, validates it, and writes `.reponomics/setup-complete`. Other generated workflows are gated on that marker so they do not collect, publish, rotate, reset, or update docs before setup has completed.

Setup also replaces the template's initial root `README.md` with either a markdown dashboard, if you opt in and the repository is private, or a generic post-setup notice. The original root `README.md` remains available at `README.backup.md`.

Setup does not collect traffic immediately. After setup succeeds, run **Actions -> Collect and Publish -> Run workflow** once if you want the first dashboard before the next scheduled run.

## Config Options - Reference

The setup fields at the top of `config.yaml` represent important user preferences and do not ship with default values.

- `i_have_read_the_readme`: required boolean; set to `true` after you have read the root README. (NOTE: This is only meant to emphasize the importance of "reading the manual" - it does not represent any legal agreement, and any legal requirements are summarized in the template repo's LICENSE file)

- `data_mode`: required string; `encrypted` stores retained dashboard data encrypted, while `plaintext` stores it unencrypted and is only supported in private repositories.

- `publish_pages_dashboard`: required boolean; when `true`, publish an HTML dashboard through GitHub Pages and require `data_mode: encrypted`.

- `publish_readme_dashboard`: required boolean; when `true`, publish a markdown/SVG metrics dashboard to the repository `README.md`; only supported in private repositories.

- `artifact_retention_days`: integer from `14` to `90`; controls GitHub Actions artifact expiry, not how long the dashboard can keep collecting data.

- `use_github_app`: boolean; when `true`, collection uses a user-owned GitHub App installation token instead of `COLLECTION_TOKEN` as a PAT.

- `auto_doctor_every_n_days`: integer from `0` to `30`; `0` disables automatic doctor diagnostics. When set from `1` to `30`, collect-and-publish runs check the auto-doctor marker and run doctor when at least that many UTC days have elapsed since the last successful auto-doctor.

- `collect.repositories`: required list of repositories to collect. Entries may be bare repository names such as `api`, which resolve to the dashboard repository owner, or full names such as `other-owner/api`. Reponomics does not auto-discover or add repositories by default.

- `publish.repositories`: required list of repositories to render in the README and Pages dashboards. Every entry must also be present in `collect.repositories`, and the list can contain at most 8 repositories.

`collect.repositories` is usually append-mostly: add a repository when you want Reponomics to start keeping history for it. To change what appears in dashboards, edit `publish.repositories`; removing a repository from `publish.repositories` does not stop collection.

## Constraints

The official generated workflows fail closed for configurations that would publish or store unencrypted dashboard data in a public place. Public repositories cannot use `plaintext` data-mode. Pages dashboards also require `encrypted` data-mode, because ordinary GitHub Pages sites are publicly reachable unless your GitHub plan and repository settings provide a different boundary.

The following configuration choices are not supported, and the workflows will fail closed if they are found in the `config.yaml`:

- `data_mode: plaintext` for public repositories.
- `data_mode: plaintext` and `publish_pages_dashboard`.
- `publish_readme_dashboard` for public repositories.

Please keep in mind that other configurations do not represent any guarantee of privacy. In particular, the privacy benefits offered by the `encrypted` data-mode are wholly dependent on the use of a _high-entropy encryption key_ - without this, you should assume that `encrypted` data-mode by itself can only protect your data from easy access by "passers-by". Since we do not have adequate means to accurately assess whether a key is sufficiently high-entropy (and we deem that a false sense of privacy is worse than none at all), we do not attempt to block access on the basis of key strength. Instead, we try to provide (i) clear information about the kind of risk involved; (ii) guidance on how to easily generate a high-entropy key. For more information, see [Security Info](./security-info.md).
