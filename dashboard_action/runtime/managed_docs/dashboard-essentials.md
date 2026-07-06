# Dashboard Essentials

Read this page before the first run.

## First Run Checklist

1. Edit and commit `config.yaml`.
2. Add `COLLECTION_TOKEN`, unless you are using the advanced GitHub App mode.
3. If `data_mode: encrypted`, generate, save, and add `DASHBOARD_SECRET_DO_NOT_REPLACE`.
4. Run **Actions -> Setup -> Run workflow**.
5. If `publish_pages_dashboard: true`, set **Settings -> Pages -> Build and deployment -> Source** to **GitHub Actions**.
6. Run **Actions -> Collect and Publish -> Run workflow** for the first dashboard.
7. Check the workflow summary, README output, Pages URL, or dashboard artifact.

## Default Choices

- Use `data_mode: encrypted` unless the dashboard repository is private and plaintext workflow artifacts are acceptable.
- Use a fine-grained `COLLECTION_TOKEN` with repository `Administration: read` for the repositories you list in `collect.repositories`.
- Keep `publish.repositories` narrow. It can contain at most 8 repositories and must be a subset of `collect.repositories`.
- Leave `DASHBOARD_NEXT_SECRET` unset except while running key rotation or incident reset.
- Run **Doctor** before changing secrets or workflow files after a failure.

## Decisions That Matter

`data_mode` controls retained storage and dashboard-output disclosure.

- `encrypted`: retained data and dashboard payloads are encrypted with your dashboard key. Required for public repositories and Pages dashboards.
- `plaintext`: retained CSV files are stored directly in the private repository's `dashboard-data` workflow artifact. Pages publication is disabled.

`publish_pages_dashboard` controls hosted HTML dashboard publication.

- Pages requires `data_mode: encrypted`.
- The repository owner must configure Pages source as **GitHub Actions**.
- The action verifies that setting during publish; it does not enable Pages.

`publish_readme_dashboard` controls committed README metrics.

- It is private-repository only.
- It writes dashboard output into git history.

## Avoid These Mistakes

- Do not overwrite `DASHBOARD_SECRET_DO_NOT_REPLACE` to rotate the key. Use **Rotate Key**.
- Do not publish README dashboard metrics from a public repository.
- Do not give broad write permissions to `COLLECTION_TOKEN`.
- Do not treat GitHub Actions artifacts as permanent backups.
- Do not share dashboard keys, retained artifacts, private workflow logs, or private repository data in public issues.

## When Something Breaks

Run **Actions -> Doctor -> Run workflow**. Useful beta-support material usually includes:

- failed workflow name and run URL;
- Doctor summary and `reponomics-doctor-report` artifact;
- relevant `config.yaml` fields, with secrets omitted;
- action version shown in the workflow summary;
- screenshot for visual dashboard problems.

Never include `COLLECTION_TOKEN`, `DASHBOARD_SECRET_DO_NOT_REPLACE`, `DASHBOARD_NEXT_SECRET`, retained artifact contents, or private repository data in a public issue.
