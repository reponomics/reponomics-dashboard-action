# Dashboard Essentials

> [!NOTE] These docs describe the official Reponomics generated workflows for the `v0` external beta. Repository owners can modify their copies; modified workflows may behave differently from what these docs describe.

If you only read one page before running Reponomics, read this one.

## The Short Version

- Use `data_mode: encrypted` unless the dashboard repository is private and you are comfortable storing retained CSV files as plaintext workflow artifacts.
- Public dashboard repositories must use `encrypted`. Plaintext mode fails in public repositories, and plaintext dashboards are not published to GitHub Pages.
- Save `DASHBOARD_SECRET_DO_NOT_REPLACE` in a password manager before you add it as a repository secret. Reponomics cannot recover it for you.
- Do not overwrite `DASHBOARD_SECRET_DO_NOT_REPLACE` to rotate the key. Use the **Rotate Key** workflow so the current retained artifact can be decrypted and re-encrypted.
- `COLLECTION_TOKEN` is for reading repository data. It does not need Pages, Actions, or write permissions.
- Start with one GitHub owner or organization when possible. Fine-grained PATs are scoped to one owner.
- After setup, run **Collect and Publish** manually once if you want the first dashboard immediately. The schedule handles later runs.
- If a workflow fails, run **Doctor** before changing secrets or workflow files.

## The First Run

1. Edit and commit `config.yaml`.
2. Add `COLLECTION_TOKEN`.
3. If `data_mode: encrypted`, add `DASHBOARD_SECRET_DO_NOT_REPLACE`.
4. Run **Actions -> Setup -> Run workflow**.
5. If `publish_pages_dashboard: true`, set **Settings -> Pages -> Build and deployment -> Source** to **GitHub Actions**.
6. Run **Actions -> Collect and Publish -> Run workflow** for the first dashboard.
7. Check the workflow summary, README output, Pages URL, or dashboard artifact.

## The Two Decisions That Matter Most

`data_mode` controls how retained dashboard data is stored.

- `encrypted`: retained data and hosted dashboard data are encrypted with your dashboard secret. This is the default beta path and the only public-repository path.
- `plaintext`: retained CSV files are stored directly in the private repository's `dashboard-data` workflow artifact. This is simpler, but it is private-repository only and does not publish a Pages dashboard.

`publish_pages_dashboard` controls whether Reponomics tries to publish the HTML dashboard through GitHub Pages.

- Pages publication requires `data_mode: encrypted`.
- The repository owner must set Pages source to **GitHub Actions** in repository settings.
- The action checks that setting during publish; it does not enable Pages for you.

## What Not To Do

- Do not put broad write permissions on `COLLECTION_TOKEN`.
- Do not publish README dashboard metrics from a public repository.
- Do not treat GitHub Actions artifacts as permanent backups. `artifact_retention_days` controls how long GitHub keeps backup artifacts if collection stops.
- Do not share dashboard keys, retained artifacts, or private workflow output in public issues.

## When Something Breaks

Run **Doctor** and start from its workflow summary and report artifact.

For beta support, useful diagnostic material usually includes:

- the failed workflow name and run URL;
- the Doctor summary and report artifact;
- the relevant `config.yaml` fields, with secrets omitted;
- the action version shown in the workflow summary;
- a screenshot of the visible failure if the dashboard loads but looks wrong.

Never include `COLLECTION_TOKEN`, `DASHBOARD_SECRET_DO_NOT_REPLACE`, retained artifact contents, or private repository data in a public issue.
