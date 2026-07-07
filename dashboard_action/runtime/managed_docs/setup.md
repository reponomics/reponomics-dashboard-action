# Setup

Read this page before the first run. It covers the shortest path from a copied template repository to a working dashboard.

## First Run Checklist

1. Edit and commit `config.yaml`.
2. Add a collection credential. Most repositories use `COLLECTION_TOKEN`; advanced GitHub App mode uses `COLLECTION_APP_ID` and `COLLECTION_APP_PRIVATE_KEY`.
3. If `data_mode: encrypted`, generate, save, and add `DASHBOARD_SECRET_DO_NOT_REPLACE`.
4. Run **Actions -> Setup -> Run workflow**.
5. If `publish_pages_dashboard: true`, set **Settings -> Pages -> Build and deployment -> Source** to **GitHub Actions**.
6. Run **Actions -> Collect and Publish -> Run workflow** for the first dashboard.
7. Check the workflow summary, README output, Pages URL, or dashboard artifact.

## What Setup Does

Setup validates `config.yaml`, checks the required secrets for the selected mode, writes `.reponomics/setup-complete`, and replaces the starter root README.

The setup marker is an empty, non-secret file. Generated operational workflows skip their normal work until that marker exists. Deleting it pauses collection, publication, rotation, Doctor, incident reset, update-docs, and keepalive until setup writes it again.

Setup does not collect traffic data. Collection runs on the configured schedule after setup, or manually when you run **Collect and Publish**.

## Recommended Initial Choices

- Use `data_mode: encrypted` unless the dashboard repository is private and plaintext workflow artifacts are acceptable.
- Use a fine-grained `COLLECTION_TOKEN` with repository `Administration: read` for the repositories listed in `collect.repositories`.
- Keep `publish.repositories` narrow. It can contain at most 8 repositories and must be a subset of `collect.repositories`.
- Leave `DASHBOARD_NEXT_SECRET` unset except while running key rotation or incident reset.
- Run **Doctor** before changing secrets or workflow files after a failure.

## Decisions That Affect Setup

`data_mode` controls retained storage and dashboard-output disclosure.

- `encrypted`: retained data and dashboard payloads are encrypted with your dashboard key. It is required for public repositories and Pages dashboards.
- `plaintext`: retained CSV files are stored directly in the private repository's `dashboard-data` workflow artifact. Pages publication is disabled.

`publish_pages_dashboard` controls hosted HTML dashboard publication. Pages requires `data_mode: encrypted`, and the repository owner must configure Pages source as **GitHub Actions**.

`publish_readme_dashboard` controls committed README metrics. It is private-repository only because README output is written to git history.

## Avoid These Mistakes

- Do not overwrite `DASHBOARD_SECRET_DO_NOT_REPLACE` to rotate the key. Use **Rotate Key**.
- Do not publish README dashboard metrics from a public repository.
- Do not give broad write permissions to the collection credential.
- Do not treat GitHub Actions artifacts as permanent backups.
- Do not share dashboard keys, retained artifacts, private workflow logs, or private repository data in public issues.

## Next Reads

- [Configuration](configuration.md)
- [Publication](publication.md)
- [Troubleshooting](troubleshooting.md)
