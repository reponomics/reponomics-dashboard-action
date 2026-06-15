# Configuration Reference

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

> [!NOTE]
> Whenever these documents describe what you may, must, or should do (or not do), this should be interpreted as, "if you choose to use the software in the way it is intended, designed, and supported". The software is open source, and we do not impose any restrictions on your usage beyond those stated in the LICENSE.

## About

The Reponomics Dashboard template repo uses a pre-defined set of template workflows that invoke the Reponomics Dashboard [public GitHub action](https://github.com/reponomics/reponomics-dashboard-action). Those workflows read `config.yaml` at runtime, validate the selected data-mode and publication settings, then pass the resolved values to the action. For security reasons, invalid or syntactically ill-formed `config.yaml` files will cause the workflow to fail with a notice.

## Setup

To get started, you must edit the `config.yaml` file according to your preferences and then commit the file changes. Afer that, you must run the `setup` workflow before any other template workflow will run. This workflow reads the `config.yaml`, ensures that it is valid, and then writes a `setup-complete` marker file to `.reponomics/setup-complete`. (The purpose of this gate is to prevent any other workflows from running before you have made your configuration selections.) The other workflows are gated on the existence of this file and also read and validate the config each time. If you decide to change your mind about any of your initial configuration choices, you can simply edit `config.yaml` and commit the changes, and the edits will flow through to the workflows. The `setup` workflow also over-writes the template's initial root `README.md` - either with a markdown dashboard, if you opt in to this and your repo is private, or with a generic post-setup notice otherwise. The original root `README.md` will be available at `README.backup.md` for future reference, if needed.

## Config Options - Reference

The setup fields at the top of `config.yaml` represent important user preferences and do not ship with default values.

- `i_have_read_the_readme`: required boolean; set to `true` after you have read the setup README.

- `data_mode`: required string; `encrypted` stores retained dashboard data encrypted, while `plaintext` stores it unencrypted and is only supported in private repositories.

- `publish_pages_dashboard`: required boolean; when `true`, publish an HTML dashboard through GitHub Pages and require `data_mode: encrypted`.

- `publish_readme_dashboard`: required boolean; when `true`, publish a markdown/SVG metrics dashboard to the repository `README.md`; only supported in private repositories.

- `allow_docs_sync`: required boolean; when `true`, allow the action to update managed documentation in `docs/reponomics/`.

- `artifact_retention_days`: integer from `1` to `90`; controls GitHub Actions artifact expiry, not how long the dashboard can keep collecting data.

- `use_github_app`: boolean; when `true`, collection uses a user-owned GitHub App installation token instead of `COLLECTION_TOKEN` as a PAT.

- `max_repos`: positive integer; caps how many repositories the dashboard tracks.

- `include_only`: list of `owner/repo` names; when non-empty, track only these repositories and ignore automatic discovery.

- `include`: list of `owner/repo` names; always include these repositories when the collection token can access them.

- `exclude`: list of `owner/repo` names; never include these repositories through automatic selection.

- `include_others`: boolean; when `true`, fill remaining `max_repos` slots from automatically discovered eligible repositories.

- `include_new`: boolean; when `true`, allow repositories created after the initial automatic-selection baseline into the automatic pool.

- `include_private`: boolean; when `true`, allow private repositories into the automatic pool when the collection token can access them.

## Constraints

There are some configurations that the Dashboard action currently does not support. That's not because we wish to limit your choices, but because they have a strong potential to expose data that we assume most users would prefer to keep private, and we try to design things so that it's really, really hard for users to expose their data without modifying the software. Ideally, if a user prefers one of these options, it won't be too hard for them to modify the software to suit their needs.

In general, we just try to limit options that involve publishing or storing unencrypted data in a publicly accessible way. For public repos, this covers everything, including the workflow logs and artifact storage system. Workflow artifacts in public repositories may be accessed and downloaded by anyone whatsoever, via the API, CLI, or Web UI, including authenticated requests. So, we do not permit `plaintext` data-mode in public repositories. Except for users with a GHES plan, GitHub Pages sites are also accessible to the general public, regardless of the repo's visibility (public or private). So, we don't support publishing Pages dashboards in `plaintext` data-mode, even for private repos.

The following configuration choices are not supported, and the workflows will fail closed if they are found in the `config.yaml`:

- `data_mode: plaintext` for public repositories.
- `data_mode: plaintext` and `publish_pages_dashboard`.
- `publish_readme_dashboard` for public repositories.

These options involve publication or storage of repository data in a way that is directly accessible to the general public.

Please keep in mind that other configurations do not represent any guarantee of privacy. In particular, the privacy benefits offered by the `encrypted` data-mode are wholly dependent on the use of a _high-entropy encryption key_ - without this, you should assume that `encrypted` data-mode by itself can only protect your data from easy access by "passers-by". Since we do not have adequate means to accurately assess whether a key is sufficiently high-entropy (and we deem that a false sense of privacy is worse than none at all), we do not attempt to block access on the basis of key strength. Instead, we try to provide (i) clear information about the kind of risk involved; (ii) guidance on how to easily generate a high-entropy key. For more information, see [security-boundary.md](./security-info.md).
