# Publication

Reponomics can render dashboard output in three places: GitHub Pages, downloadable HTML workflow artifacts, and the repository README. Each surface has different privacy and maintenance implications.

## GitHub Pages

Hosted Pages dashboards require:

- `data_mode: encrypted`;
- `publish_pages_dashboard: true`;
- repository **Settings -> Pages -> Build and deployment -> Source** set to **GitHub Actions**.

The publish workflow verifies the Pages source setting during deployment. It does not enable Pages or change the source setting.

Unless your GitHub plan provides Pages access controls, a GitHub Pages site is reachable on the internet even when the repository is private. Encrypted mode protects dashboard payloads from readers who do not have the dashboard key, but it does not hide the existence of the site, publication timing, workflow metadata, or encrypted payload size.

## Downloadable HTML Artifacts

When Pages is disabled, encrypted publish uploads `html-dashboard-encrypted` as a downloadable workflow artifact.

Plaintext mode never publishes Pages. It uploads `html-dashboard-plaintext` for private-repository use.

## README Dashboard

`publish_readme_dashboard: true` writes markdown/SVG metrics into the repository README. It is private-repository only because README output is committed to git history.

Public repositories reject README dashboard generation.

## Republish Without Collection

The **Collect and Publish** workflow can run with `skip_collect: true` to republish existing retained data without collecting new GitHub data. This is useful after changing publication settings or recovering a dashboard output when the retained artifact still exists.

## Continue

- [Configuration](configuration.md)
- [Data and artifacts](data-and-artifacts.md)
- [Troubleshooting](troubleshooting.md)
