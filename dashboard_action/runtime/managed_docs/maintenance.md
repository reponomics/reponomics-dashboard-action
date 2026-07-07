# Maintenance

The dashboard is low-maintenance only if scheduled workflows keep running, credentials stay valid, retained artifacts do not expire without a successor, and the repository owner preserves the dashboard key.

## Scheduled Collection

Collection runs on the generated schedule after setup. GitHub may disable scheduled workflows in inactive public repositories, and inactive schedules are an operational risk for any dashboard repository.

The generated keepalive workflow runs monthly, commits `.reponomics/keepalive.md`, and tries to create one persistent data safety reminder issue.

## Artifact Expiry

`artifact_retention_days` controls how long each uploaded artifact remains downloadable. It is not the dashboard history window.

If scheduled workflows stop unexpectedly, download the latest `dashboard-data` artifact before it expires, then re-enable workflows from the Actions tab.

## Auto-Doctor

`auto_doctor_every_n_days` can run Doctor during the collect-and-publish cadence when the configured number of UTC days has elapsed since the last successful auto-doctor.

Use this as routine validation, not as a substitute for investigating workflow failures.

## Routine Checks

Periodically confirm:

- scheduled Collect and Publish runs are still completing;
- `COLLECTION_TOKEN` or GitHub App credentials have not expired or lost repository access;
- encrypted dashboards still unlock with the saved dashboard key;
- `DASHBOARD_NEXT_SECRET` is unset outside active rotation or incident reset;
- Update Docs has not reported `permission_missing` or `manifest_inconsistent`;
- important retained history has an independent export if artifact loss would matter.

## Continue

- [Data and artifacts](data-and-artifacts.md)
- [Workflows](workflows.md)
- [Troubleshooting](troubleshooting.md)
