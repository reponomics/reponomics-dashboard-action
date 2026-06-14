# Configuration Reference

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

## About

The Reponomics Dashboard template repo uses a pre-defined set of template workflows that invoke the Reponomics Dashboard [public GitHub action](https://github.com/reponomics/reponomics-dashboard-action). Those workflows read `config.yaml` at runtime, validate the selected data-mode and publication settings, then pass the resolved values to the action. For security reasons, invalid or syntactically ill-formed `config.yaml` files will cause the workflow to fail with a notice.

## Setup

To get started, you must edit the `config.yaml` file according to your preferences and then commit the file changes. Afer that, you must run the `setup` workflow before any other template workflow will run. This workflow reads the `config.yaml`, ensures that it is valid, and then writes a `setup-complete` marker file to `.reponomics/setup-complete`. (The purpose of this gate is to prevent any other workflows from running before you have made your configuration selections.) The other workflows are gated on the existence of this file and also read and validate the config each time. If you decide to change your mind about any of your initial configuration choices, you can simply edit `config.yaml` and commit the changes, and the edits will flow through to the workflows, assuming the new configuration is valid and accepted. The `setup` workflow also over-writes the template's initial root `README.md` - either with a markdown dashboard, if you opt in to this and your repo is private, or with a generic post-setup notice otherwise. The original root `README.md` will be available at `README.backup.md` for future reference, if needed.

## Config Options - Reference

The setup fields at the top of `config.yaml` must be filled before setup can proceed and do not ship with default values.

```yaml
i_have_read_the_readme: true
data_mode: encrypted
publish_pages_dashboard: true
publish_readme_dashboard: false
allow_docs_sync: true
artifact_retention_days: 90
use_github_app: false
```

`publish_pages_dashboard: true` requires `data_mode: encrypted`. Public repositories must use `data_mode: encrypted` and cannot enable `publish_readme_dashboard`.


`allow_docs_sync` controls whether Reponomics may update `docs/reponomics/` automatically when the repo's version of the action is updated. Set it to `false` before editing the managed docs directory yourself.

Example `config.yaml` opt-out:

```yaml
allow_docs_sync: false
```

Repository selection remains caller-owned. Managed docs sync does not mutate `config.yaml`, write retained CSV data to git, or write outside `docs/reponomics/`, or the root `README.md` if `publish-readme-dashboard` is selected.
