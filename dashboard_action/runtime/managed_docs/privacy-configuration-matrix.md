# Privacy Configuration Matrix

Repository visibility and Reponomics data mode are separate choices. Repository visibility controls who can read the repository. `data_mode` controls how retained artifacts and dashboard output are stored.

| Mode | Repository visibility | Retained artifact | Hosted Pages dashboard | Downloadable dashboard artifact | README output | Secret policy |
| --- | --- | --- | --- | --- | --- | --- |
| `encrypted` | public or private | encrypted `dashboard-data.enc` | optional encrypted Pages deployment when `publish_pages_dashboard: true` | encrypted dashboard artifact when Pages is disabled | setup README; private repositories may commit README metrics when `publish_readme_dashboard: true` | non-empty `DASHBOARD_SECRET_DO_NOT_REPLACE` required |
| `plaintext` | private only | plaintext retained CSV files | disabled | plaintext HTML dashboard artifact | setup README; private repositories may commit README metrics when `publish_readme_dashboard: true` | no dashboard secret |

## Encrypted Mode

Use `encrypted` by default. It protects retained artifacts and hosted dashboard data from people who do not have the dashboard key.

It does not hide:

- the existence of the Pages site;
- publication timing;
- encrypted dashboard payload size;
- workflow metadata;
- metrics committed to a private repository README dashboard.

Encrypted mode is a shared-secret model, not per-user authentication. The action requires a non-empty key but does not enforce entropy. See [Secure Dashboard Key](secure-dashboard-key.md) and [Security Info](security-info.md).

## Plaintext Mode

Use `plaintext` only in private repositories where GitHub repository and Actions artifact access are the intended privacy boundary.

Plaintext mode stores retained CSV files directly inside the `dashboard-data` artifact, may upload a downloadable plaintext dashboard artifact, and does not publish a hosted Pages dashboard. The action rejects plaintext mode in public repositories.

## CSV Export

Encrypted dashboards expose CSV export after unlock. The browser downloads an encrypted export asset, decrypts it with the dashboard key, verifies SHA-256 digests, and downloads a ZIP of retained CSV files without uploading plaintext CSV back to GitHub.

For plaintext mode, inspect retained CSV files by downloading the `dashboard-data` artifact.
