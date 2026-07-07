# Privacy And Security

Repository visibility and Reponomics data mode are separate choices. Repository visibility controls who can read the repository. `data_mode` controls how retained artifacts and dashboard output are stored.

## Data Modes

| Mode | Repository visibility | Retained artifact | Hosted Pages dashboard | Downloadable dashboard artifact | README output | Secret policy |
| --- | --- | --- | --- | --- | --- | --- |
| `encrypted` | public or private | encrypted `dashboard-data.enc` | optional encrypted Pages deployment when `publish_pages_dashboard: true` | encrypted dashboard artifact when Pages is disabled | setup README; private repositories may commit README metrics when `publish_readme_dashboard: true` | non-empty `DASHBOARD_SECRET_DO_NOT_REPLACE` required |
| `plaintext` | private only | plaintext retained CSV files | disabled | plaintext HTML dashboard artifact | setup README; private repositories may commit README metrics when `publish_readme_dashboard: true` | no dashboard secret |

Use `encrypted` by default. It is required for public repositories and hosted Pages dashboards.

Use `plaintext` only in private repositories where GitHub repository and Actions artifact access are the intended privacy boundary.

## What Encryption Protects

Encrypted mode encrypts retained CSV artifacts and dashboard payloads before storage or publication. It protects those payloads from people who can download them but do not have the dashboard key.

It does not hide:

- the existence of the Pages site;
- publication timing;
- encrypted dashboard payload size;
- workflow metadata;
- metrics committed to a private repository README dashboard.

Encrypted mode is a shared-secret model, not per-user authentication.

## Artifact Visibility

Workflow artifacts are readable by anyone with repository read access. In public repositories, treat Actions artifacts as public according to GitHub's artifact visibility rules. In private repositories, collaborators who can read workflow runs can read artifacts.

Plaintext mode relies on GitHub repository and Actions artifact access as the privacy boundary. That is why it is rejected in public repositories.

## Browser-Side Limits

Browser-side encryption does not protect against malicious browser extensions, compromised devices, malicious JavaScript in the trusted dashboard shell, compromised CI/CD, or supply-chain compromise of the action version your workflow runs.

Encrypted artifacts can be downloaded and attacked offline by anyone who obtains them. Use a high-entropy random key for public Pages dashboards, public repositories, sensitive metrics, or targeted-threat models.

## Trust Boundary

Encryption does not protect against people or systems that can run trusted workflows with access to repository secrets. Anyone who can alter trusted workflows, manage repository secrets, approve protected environments, or administer the repository can affect the dashboard control plane.

For repository access implications, see [Repository Access And Trust Boundary](trust-boundary.md).

## Continue

- [Dashboard key and recovery](dashboard-key-and-recovery.md)
- [Data and artifacts](../concepts/data-and-artifacts.md)
- [Publication](../concepts/publication.md)
