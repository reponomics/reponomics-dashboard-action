# Privacy And Artifacts

Reponomics separates retained dashboard data from committed repository files. Collection writes retained data to GitHub Actions artifacts, not to git history.

`strong` privacy mode encrypts retained data and hosted dashboard export assets with a high-entropy dashboard secret. Public dashboard repositories should normally use this mode.

`casual` privacy mode also encrypts retained data and hosted dashboard export assets, but accepts any non-empty dashboard secret. It is meant for non-targeted access control, not resistance to offline brute-force attacks.

`plain` privacy mode stores retained CSV artifacts without encryption and is allowed only for private repositories. It does not publish a public GitHub Pages dashboard. During `publish`, Reponomics uploads the rendered HTML dashboard as a private workflow artifact named `html-dashboard-plain`.

Workflow artifacts are readable by anyone with repository read access. In public repositories, that means public artifact access according to GitHub's artifact visibility rules. In private repositories, collaborators who can read workflow runs can read artifacts.

Anyone who can modify repository secrets and run trusted workflows is inside the dashboard trust boundary. A hostile collaborator with that power can replace dashboard secrets, run rotation or incident workflows, exfiltrate retained data they can access, and delete old workflow runs or artifacts if the workflow grants that permission.
