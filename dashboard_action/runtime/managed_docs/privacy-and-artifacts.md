# Privacy And Artifacts

Reponomics separates retained dashboard data from committed repository files. Collection writes retained data to GitHub Actions artifacts, not to git history.

## Retained Data

The canonical retained data store is the `dashboard-data` workflow artifact.

- In `encrypted` mode, retained data is stored as encrypted `dashboard-data.enc`.
- In `plaintext` mode, retained CSV files are stored directly in the artifact.

`artifact_retention_days` controls GitHub Actions artifact expiry for each uploaded artifact. It does not cap how many days of dashboard history Reponomics can retain. History can keep growing as long as collection restores the current artifact and uploads a successor before expiry.

## Dashboard Output

Generated HTML dashboards are rendered during workflow runs.

- Encrypted Pages dashboards publish encrypted dashboard payloads.
- Encrypted non-Pages dashboards upload `html-dashboard-encrypted`.
- Plaintext dashboards upload `html-dashboard-plaintext` and do not publish Pages.

Generated dashboards load a summary first and per-repository detail chunks as repositories are selected. In encrypted mode, the summary and chunks are encrypted. In plaintext mode, the same chunking improves runtime behavior but does not add confidentiality.

## Artifact Visibility

Workflow artifacts are readable by anyone with repository read access. In public repositories, treat Actions artifacts as public according to GitHub's artifact visibility rules. In private repositories, collaborators who can read workflow runs can read artifacts.

Anyone who can modify secrets and run trusted workflows is inside the dashboard trust boundary. That person can replace dashboard keys, exfiltrate retained data through workflow changes, run rotation or incident workflows, and delete old workflow runs or artifacts when workflow permissions allow it.

## CSV Export

Encrypted dashboards expose CSV export only after unlock. The browser downloads an encrypted export asset, decrypts it locally with the dashboard key, verifies SHA-256 digests, and downloads a ZIP of retained CSV files. Plaintext CSV is not uploaded back to GitHub during export.

For plaintext mode, download the retained CSV files directly from the `dashboard-data` artifact.
