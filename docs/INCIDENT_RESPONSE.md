# Incident Response

This guide provides guidance on how to respond to incidents where a dashboard repository's encryption secret may have been exposed, or if a hostile actor has gained access.

## Primary Response: Incident Reset

Use `mode: incident-reset` when `DASHBOARD_SECRET_DO_NOT_REPLACE` may be known to someone who should not have it. In the template repository, this can be manually triggered by running the `INCIDENT - Reset` workflow.

The workflow will (a) rotate your key; (b) re-encrypt your data with the new key; (c) delete any retained data artifacts encrypted with the old key.

> [!WARNING]
> This a _destructive action_. Do not modify `DASHBOARD_SECRET_DO_NOT_REPLACE` until _AFTER_ successful completion of the workflow. The Reponomics organization cannot recover lost keys.

Before running the workflow:

1. For increased protection, make the dashboard repository private if it is public. (Public repository workflow artifact are generally available for download by any user.)
2. Disable the GitHub Pages site if an encrypted dashboard was published with the exposed key.
3. Set `DASHBOARD_NEXT_SECRET` to a new dashboard key.
4. Run `incident-reset` with all required confirmation inputs.

`incident-reset` intentionally performs recovery before cleanup - it will:

1. Restore the current `dashboard-data` artifact.
2. Decrypt retained data with `DASHBOARD_SECRET_DO_NOT_REPLACE`.
3. Re-encrypt retained data with `DASHBOARD_NEXT_SECRET`.
4. Upload the new encrypted `dashboard-data` artifact.
5. Find prior `dashboard-data` artifacts, excluding the artifact uploaded by the current reset run.
6. Delete workflow runs associated with those prior artifacts. GitHub deletes a run's artifacts when the run is deleted.
7. Delete only those old `dashboard-data` artifacts that GitHub reports without an associated workflow run id.

After a successful run, promote `DASHBOARD_NEXT_SECRET` into `DASHBOARD_SECRET_DO_NOT_REPLACE`, then delete `DASHBOARD_NEXT_SECRET`. (This is one of the rare instances where you should do what the name of the secret says you should not do.)

## Extreme Recovery Patterns

If a hostile actor or collaborator has elevated access to your repository, such as permissions to modify secrets, it may be necessary to delete the repository.

1. Run `incident-reset` so retained data is re-encrypted with a new key.
2. Download the new encrypted `dashboard-data` artifact.
3. Delete the old dashboard repository.
4. Create a fresh dashboard repository later.

A future rehydrate path can support seeding a fresh dashboard repository from a
preserved encrypted `dashboard-data.enc` file. The likely safe version is
`rehydrate-from-private-repo`: store the encrypted seed in a temporary private
repository, run a rehydrate workflow in the new dashboard repository with
`contents: read` access to the seed repository, verify the seed hash, and upload
it as the new repository's canonical `dashboard-data` artifact.

This rehydrate workflow is not part of the current action contract. The accepted
policy direction is recorded in
[ADR 015](./adr/015-extreme-recovery-repository-deletion-and-reseeding.md).
