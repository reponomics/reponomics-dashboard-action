# Data And Artifacts

Reponomics separates retained dashboard data from committed repository files. Collection writes retained data to GitHub Actions artifacts, not to git history.

## Retained State

The canonical retained data store is the `dashboard-data` workflow artifact.

- In `encrypted` mode, retained data is stored as encrypted `dashboard-data.enc`.
- In `plaintext` mode, retained CSV files are stored directly in the artifact.

Collected data is not stored in git unless you enable `publish_readme_dashboard` in a private repository. The retained data store remains the `dashboard-data` artifact.

## Artifact Lineage

`collect` restores the prior `dashboard-data` artifact, collects current GitHub data, merges retained CSV history, verifies lineage, uploads a successor artifact, and cleans up one older superseded artifact when safe.

`publish` restores retained data, migrates it to the runtime's current schema, and renders dashboard output.

`rotate-key` and `incident-reset` both restore retained encrypted state and write a fresh encrypted successor. Use `rotate-key` for normal rotation. Use `incident-reset` only for suspected key exposure after making the dashboard repository private and disabling exposed Pages output.

## Retention Days

`artifact_retention_days` controls GitHub Actions artifact expiry for each uploaded artifact. It does not cap how many days of dashboard history Reponomics can retain.

History can keep growing as long as scheduled collection restores the current artifact and uploads the next one before expiry. If workflows stop, download the latest `dashboard-data` artifact before it expires.

## CSV Export

Encrypted dashboards expose CSV export only after unlock. The browser downloads an encrypted export asset, decrypts it locally with the dashboard key, verifies SHA-256 digests, and downloads a ZIP of retained CSV files. Plaintext CSV is not uploaded back to GitHub during export.

For plaintext mode, download the retained CSV files directly from the `dashboard-data` artifact.

## Offline Viewing

The generated HTML dashboard is not committed to the repository. To view an encrypted dashboard offline, download the dashboard artifact from a successful workflow run, extract it, and open `index.html` with the same dashboard key. If a browser blocks local `file://` fetches, serve the extracted directory over local HTTP.

## Continue

- [Publication](publication.md)
- [Privacy and security](privacy-and-security.md)
- [Workflows](workflows.md)
