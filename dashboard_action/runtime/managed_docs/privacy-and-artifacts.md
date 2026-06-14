# Privacy And Artifacts

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

Reponomics separates retained dashboard data from committed repository files. Collection writes retained data to GitHub Actions artifacts, not to git history.

`artifact_retention_days` controls GitHub Actions artifact expiry for each uploaded artifact. It does not cap how many days the dashboard can keep collecting data. Retained CSV history can continue growing across unbounded scheduled collection runs as long as each run restores the current `dashboard-data` artifact and uploads a successor before the prior artifact expires.

`encrypted` data mode encrypts retained data and hosted dashboard export assets with `DASHBOARD_SECRET_DO_NOT_REPLACE`. Public dashboard repositories must use this mode.

`plaintext` data mode stores retained CSV artifacts without encryption and is allowed only for private repositories. It does not publish a public GitHub Pages dashboard. During `publish`, Reponomics uploads the rendered HTML dashboard as a private workflow artifact named `html-dashboard-plaintext`. That artifact uses the same summary plus per-repository chunk dashboard data model as encrypted dashboards so large dashboards do not need to parse every repository detail object on first render.

Encrypted mode requires a non-empty dashboard key, but the action does not enforce key length, complexity, or entropy. See [Security Info](security-info.md) for key-generation and threat-model guidance.

Workflow artifacts are readable by anyone with repository read access. In public repositories, that means public artifact access according to GitHub's artifact visibility rules. In private repositories, collaborators who can read workflow runs can read artifacts.

Anyone who can modify repository secrets and run trusted workflows is inside the dashboard trust boundary. A hostile collaborator with that power can replace dashboard secrets, run rotation or incident workflows, exfiltrate retained data they can access, and delete old workflow runs or artifacts if the workflow grants that permission.
