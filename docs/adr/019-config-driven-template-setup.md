# ADR 019: Config-Driven Template Setup

Date: 2026-06-14

## Status

Accepted

## Context

The generated dashboard template previously used setup workflow inputs for important first-run choices such as data mode and publication targets. That made setup intent split across two places: committed repository configuration and one-off workflow dispatch parameters. It also left operational workflows with their own defaults or input-derived assumptions after setup had completed.

Those choices affect privacy, publication surface, and artifact behavior. They should be reviewable in git before setup runs, and subsequent collection, publication, key rotation, doctor, and incident-reset workflows should keep reading the same committed source of truth.

## Decision

Use the generated repository's committed `config.yaml` as the source of truth for setup and operational workflow behavior.

The setup configuration fields at the top of `config.yaml` are:

```yaml
i_have_read_the_readme: # true/false
data_mode: # encrypted/plaintext
publish_pages_dashboard: # true/false
publish_readme_dashboard: # true/false
allow_docs_sync: # true/false
artifact_retention_days: 90 # artifact expiry, not dashboard history length
use_github_app: false # you may use your own GitHub App installation token if you prefer; this does not refer to a Reponomics Dashboard app
```

Setup validates this file before making repository changes. It fails closed when required fields are blank, malformed, or incompatible with repository visibility and privacy rules.

The enforced setup constraints are:

- `i_have_read_the_readme` must be `true`.
- `data_mode` must be `encrypted` or `plaintext`.
- Public repositories must use `data_mode: encrypted`.
- `publish_pages_dashboard: true` requires `data_mode: encrypted`.
- Public repositories cannot use `publish_readme_dashboard: true`.
- `artifact_retention_days` must remain within GitHub's supported artifact retention range.

Setup no longer accepts workflow-dispatch inputs for these choices. Once validation and setup complete, setup writes `.reponomics/setup-complete`. Operational workflows are gated on that marker and should do no collection or publication work before it exists.

After the marker exists, operational workflows still resolve `config.yaml` at runtime rather than relying on values captured during setup. This preserves a simple rule: committed configuration controls current behavior, while the setup marker records that the repository completed initial validation and enablement.

`artifact_retention_days` remains an artifact-expiry setting only. It does not limit how long the dashboard can collect data; retained dashboard history can continue across unbounded scheduled runs as long as each run restores the current `dashboard-data` artifact and uploads a successor before the prior artifact expires.

## Decision Points

- Keep one setup marker for now. Because setup cannot proceed until the user commits explicit `config.yaml` choices, the marker only needs to represent completed setup, not every individual option.
- Keep `artifact_retention_days: 90` in the template because it matches GitHub's usual default and is safer than a shorter initial expiry window.
- Keep `use_github_app: false` as an explicit starting value because it is an advanced collection-token option and should not be confused with a Reponomics-operated app.
- Do not silently rewrite `config.yaml` during setup. The file is user-owned configuration, and setup should validate it rather than normalize or mutate it.
- Keep the action's lower-level inputs available for workflow-to-action plumbing. The generated workflows now resolve user intent from `config.yaml` and pass the resulting values into the action.

## Consequences

- First setup becomes more auditable: a pull request or commit diff shows the privacy and publication choices before workflows are enabled.
- Setup failures should be earlier and clearer when a public repository asks for plaintext data or a public README dashboard.
- Generated workflows must keep a lightweight config-resolution step in each operational job that depends on data mode, publication targets, retention, docs sync, or GitHub App collection.
- Template tests need to cover both generated workflow shape and resolver failure modes because the config file is now part of the action/template contract.
- Existing copied repositories from pre-public releases may need coordinated migration or reset before beta if their workflows still depend on setup dispatch inputs.

## Open Questions

None at this point.

## Resolved Follow-Ups

- Keep the generated resolver as a copied local script rather than a reusable workflow. The resolver now keeps the small scalar parser but treats it as a fail-closed validation boundary: malformed top-level syntax, duplicate setup keys, unterminated quoted values, control characters, and unsafe environment-file assignments stop the workflow before normalized config values are exported.
- Keep `doctor` aligned with runtime configuration by resolving `config.yaml` like the other operational workflows and passing normalized publication settings into the action. The doctor workflow should not become a second source of configuration reporting; human-facing diagnostic reporting belongs in doctor mode output and targeted workflow summaries.
- The first beta compatibility fixture should capture this config-driven setup shape as the initial supported template surface, including the required setup keys, `.reponomics/setup-complete` gating, runtime config resolution, and fail-closed validation expectations.
