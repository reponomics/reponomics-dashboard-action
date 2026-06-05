# Incident Response

This guide covers Reponomics dashboard incidents where an encrypted dashboard
key may have been exposed.

## Primary Response: Incident Reset

Use `mode: incident-reset` when `DASHBOARD_SECRET_DO_NOT_REPLACE` may be known
to someone who should not have it.

Before running the workflow:

1. Make the dashboard repository private if it is public.
2. Disable or close the GitHub Pages site if an encrypted dashboard was
   published with the exposed key.
3. Set `DASHBOARD_NEXT_SECRET` to a new dashboard key.
4. Run `incident-reset` with all three confirmation inputs.

`incident-reset` intentionally performs recovery before cleanup:

1. Restore the current `dashboard-data` artifact.
2. Decrypt retained data with `DASHBOARD_SECRET_DO_NOT_REPLACE`.
3. Re-encrypt retained data with `DASHBOARD_NEXT_SECRET`.
4. Upload the new encrypted `dashboard-data` artifact.
5. Find prior `dashboard-data` artifacts, excluding the artifact uploaded by the
   current reset run.
6. Delete workflow runs associated with those prior artifacts. GitHub deletes a
   run's artifacts when the run is deleted.
7. Delete only those old `dashboard-data` artifacts that GitHub reports without
   an associated workflow run id.

This purge is expected to be small once canonical artifact lineage and active
retention are in place. It is not a long-tail archival cleanup strategy; it is
the incident-specific cleanup of remaining GitHub-hosted dashboard-data history
after a fresh encrypted successor exists.

After a successful run, promote `DASHBOARD_NEXT_SECRET` into
`DASHBOARD_SECRET_DO_NOT_REPLACE`, then delete `DASHBOARD_NEXT_SECRET`.

## Scope And Limits

`incident-reset` is best-effort cleanup for repository-local GitHub Actions
history. It cannot recall data that was already downloaded, cached in a
browser, captured by a user, or served from an already-fetched Pages asset.

Forks are not a meaningful exposure surface for this model: ordinary forks do
not preserve the source repository's workflow runs, Actions artifacts, or
repository secrets.

## Extreme Recovery Patterns

If the concern is severe, the cleanest response may be:

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
