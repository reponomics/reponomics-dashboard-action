# Configuration Reference

The dashboard repository normally uses the Reponomics template workflows. Those workflows pass action inputs for runtime mode, tokens, privacy mode, retention, README rendering, and managed documentation sync.

The main modes are `collect`, `publish`, `rotate-key`, `incident-reset`, and `docs-sync`. `collect` stores retained dashboard data in workflow artifacts. `publish` renders the dashboard from retained data. `rotate-key` re-encrypts retained data and generated encrypted assets with a new dashboard secret. `incident-reset` rotates to a new secret and deletes old workflow runs and dashboard-data artifacts for the current workflow. `docs-sync` updates this managed documentation namespace.

`allow_docs_sync` controls whether Reponomics may update `docs/reponomics/` automatically when the repo's version of the action is updated. The default is `true`, but if the user prefers the action to not write directly to their repo, they may set it to `false` either in the workflow action input or in `config.yaml` as `allow_docs_sync: false`, in that order of precedence.

Example `config.yaml` opt-out:

```yaml
allow_docs_sync: false
```

Repository selection remains caller-owned. Managed docs sync does not mutate `config.yaml`, write retained CSV data to git, or write outside `docs/reponomics/`.
