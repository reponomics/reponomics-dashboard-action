# Configuration Reference

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

The dashboard repository normally uses the Reponomics template workflows. Those workflows read `config.yaml` at runtime, validate the selected data mode and publication settings, then pass the resolved values to the action.

The main modes are `collect`, `publish`, `rotate-key`, `incident-reset`, and `docs-sync`. `collect` stores retained dashboard data in workflow artifacts. `publish` renders the dashboard from retained data. `rotate-key` re-encrypts retained data and generated encrypted assets with a new dashboard secret. `incident-reset` restores retained data, re-encrypts it with `DASHBOARD_NEXT_SECRET`, uploads the new encrypted artifact, then finds prior `dashboard-data` artifacts and deletes their associated workflow runs. `docs-sync` updates this managed documentation namespace.

For serious dashboard-key exposure, make the dashboard repository private and disable any published Pages dashboard before relying on `incident-reset`. After the run succeeds, promote `DASHBOARD_NEXT_SECRET` into `DASHBOARD_SECRET_DO_NOT_REPLACE`, then delete `DASHBOARD_NEXT_SECRET`.

The setup fields at the top of `config.yaml` must be filled before setup can proceed:

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

After setup succeeds, the repository contains `.reponomics/setup-complete`. This empty, non-secret file is the setup-completion marker used by generated workflows. If it is deleted, operational workflows skip their normal work until setup writes it again. If you deliberately complete `config.yaml` and manage setup manually, recreating the empty marker is acceptable.

`allow_docs_sync` controls whether Reponomics may update `docs/reponomics/` automatically when the repo's version of the action is updated. Set it to `false` before editing the managed docs directory yourself.

Example `config.yaml` opt-out:

```yaml
allow_docs_sync: false
```

Repository selection remains caller-owned. Managed docs sync does not mutate `config.yaml`, write retained CSV data to git, or write outside `docs/reponomics/`.
