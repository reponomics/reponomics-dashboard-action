# Troubleshooting

Start with **Actions -> Doctor -> Run workflow**. Doctor writes a workflow summary and, when available, uploads a machine-readable report artifact named `reponomics-doctor-report`.

For the expected workflow modes, permissions, secrets, artifacts, and failure classes, see [Workflows](workflows.md).

## Setup Fails

Check:

- `config.yaml` is committed on the default branch.
- `i_have_read_the_readme` is `true`.
- `data_mode`, `publish_pages_dashboard`, and `publish_readme_dashboard` are filled in.
- Required secrets exist for the selected mode.

If setup succeeds, it writes `.reponomics/setup-complete`. Other generated workflows skip their normal work until that marker exists.

## Collection Fails

Check:

- `COLLECTION_TOKEN` exists and is not expired, unless advanced GitHub App mode is enabled.
- For a fine-grained PAT, the token has repository `Administration: read` for every repository in `collect.repositories`.
- The token owner can access the listed repositories.
- Bare repository names belong to the dashboard repository owner; use `owner/repo` for repositories owned elsewhere.
- `DASHBOARD_NEXT_SECRET` is not still set from an unfinished key rotation.

## Publish Or Pages Fails

Check:

- **Settings -> Pages -> Build and deployment -> Source** is set to **GitHub Actions**.
- `publish_pages_dashboard: true` is paired with `data_mode: encrypted`.
- The publish job has `pages: write` and `id-token: write`.
- A current `dashboard-data` artifact exists. If artifacts expired or were deleted, collection must run again.

Plaintext mode does not publish a Pages dashboard. In plaintext mode, publish uploads a downloadable `html-dashboard-plaintext` artifact instead.

## Dashboard Does Not Unlock

Check:

- You are using the same key stored as `DASHBOARD_SECRET_DO_NOT_REPLACE`.
- The key was not overwritten directly in repository secrets.
- If rotation was started, finish **Rotate Key** before deleting `DASHBOARD_NEXT_SECRET`.
- Run Doctor with a comparison key if you want to test whether a user-held key can decrypt the current artifact.

Reponomics cannot recover a lost dashboard key unless a usable old or current key still exists outside the encrypted artifact.

## Public Or Private Mode Rejection

The official runtime fails closed for these states:

- `data_mode: plaintext` in a public repository;
- `data_mode: plaintext` with Pages publication;
- README metric dashboard generation in a public repository.

These failures describe generated workflow behavior. Repository owners can modify their copies, but modified behavior is outside what these docs describe.

## What To Share In A Beta Report

Useful diagnostic material:

- workflow name and run URL;
- Doctor summary and report artifact;
- relevant `config.yaml` fields, with secrets omitted;
- action version shown in the workflow summary;
- screenshot for visual dashboard problems.

Do not share dashboard keys, GitHub tokens, retained artifact contents, private repository data, or vulnerability details in public issues.

## Continue

- [Support](support.md)
- [Dashboard key and recovery](dashboard-key-and-recovery.md)
