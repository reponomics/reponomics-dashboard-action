# Workflows

Generated Reponomics dashboard repositories use a small set of GitHub Actions workflows. This page explains how a maintainer should think about them. The strict mode, permission, artifact, output, and failure contract lives in [Workflow Contract](../reference/workflow-contract.md).

## Setup

Run **Setup** once after editing `config.yaml` and adding required secrets. Setup validates configuration and credentials, writes `.reponomics/setup-complete`, and replaces the starter README.

Operational workflows skip normal work until the setup marker exists.

## Collect And Publish

Collect restores retained state, collects current GitHub data, verifies lineage, and uploads the next `dashboard-data` artifact.

Publish restores retained state from the current collect run, renders dashboard output, and deploys Pages, uploads an HTML dashboard artifact, or commits README dashboard output according to configuration.

Manual dispatch with `skip_collect: true` republishes existing retained data without collecting new data.

## Doctor

Run **Doctor** first when a workflow fails, a dashboard does not unlock, or output looks wrong. Doctor restores dashboard and retained artifacts from a selected workflow run, checks payloads and keys, and uploads `reponomics-doctor-report`.

## Rotate Key

Use **Rotate Key** for ordinary encrypted-mode key rotation. Set `DASHBOARD_NEXT_SECRET`, run the workflow, confirm the dashboard opens with the new key, then replace `DASHBOARD_SECRET_DO_NOT_REPLACE` and delete `DASHBOARD_NEXT_SECRET`.

Normal collection refuses to run while `DASHBOARD_NEXT_SECRET` is still set.

## Incident Reset

Use **INCIDENT - Reset** only for suspected key exposure. Make the dashboard repository private and disable exposed Pages output before relying on the reset workflow.

Incident reset re-encrypts retained state with `DASHBOARD_NEXT_SECRET`, uploads a fresh `dashboard-data` artifact, and purges old workflow history associated with prior retained artifacts.

## Update Docs

**Update Docs** refreshes `docs/reponomics/` from the managed docs payload shipped with the action version. Disable or delete the workflow before making local edits under that namespace.

## Keep Alive

**Keep Alive** runs monthly to create repository activity and a persistent data safety reminder. It is a best-effort guard against scheduled workflows becoming inactive; it is not a backup strategy.

## Continue

- [Troubleshooting](troubleshooting.md)
- [Maintenance](maintenance.md)
- [Workflow Contract](../reference/workflow-contract.md)
