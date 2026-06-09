# Reponomics Privacy Configuration Matrix

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

Status: current for action `{{ACTION_VERSION}}`.

Repository visibility and Reponomics privacy mode are separate concepts. Repository visibility controls who can read the repository. `privacy-mode` controls how retained artifacts and hosted dashboard output are stored.

## Current Modes

| Mode | Repository visibility | Retained artifact | Hosted Pages dashboard | Downloadable dashboard artifact | README output | Secret policy |
| --- | --- | --- | --- | --- | --- | --- |
| `strong` | public or private | encrypted `dashboard-data.enc` | optional encrypted Pages deployment | encrypted dashboard artifact when hosted publication is disabled | setup commits a static README; private repos may commit a markdown dashboard to the README when `generate-readme=true`; public repos do not commit README dashboards | generated high-entropy `DASHBOARD_SECRET_DO_NOT_REPLACE` required |
| `casual` | public or private | encrypted `dashboard-data.enc` | optional encrypted Pages deployment | encrypted dashboard artifact when hosted publication is disabled | same as `strong` | any non-empty `DASHBOARD_SECRET_DO_NOT_REPLACE`; weak-secret risk is accepted |
| `plain` | private only | plaintext retained CSV files | disabled | plaintext HTML artifact | setup commits a static README; private repos may commit README dashboards when `generate-readme=true` | no dashboard secret |

## Strong

Use `strong` as the default. It protects retained artifacts and hosted dashboard data from people who do not have the dashboard key. It does not hide:

- the existence of the Pages site
- publication timing
- encrypted dashboard data size
- workflow metadata
- metrics included in a private repository's README dashboard

`strong` is still a shared-secret model, not per-user authentication.

## Casual

Use `casual` only when the goal is preventing accidental viewing, crawling, or casual discovery. It encrypts the same surfaces as `strong`, but allows weak or memorable secrets. A weak secret can be guessed offline from the encrypted artifact or dashboard data object.

## Plain

Use `plain` only in private repositories where GitHub repository and artifact access are the intended privacy boundary. It uploads retained CSV files directly inside the `dashboard-data` artifact, may upload a downloadable plaintext dashboard artifact, and does not publish a hosted Pages dashboard. The plaintext HTML artifact uses the same summary plus per-repository chunk data model as encrypted dashboards for runtime memory behavior, but without encryption.

The action rejects `plain` in public repositories.

## CSV Export

Encrypted dashboards expose CSV export only after unlock. Export is browser-local: the page downloads an encrypted export asset, decrypts with the dashboard key, verifies SHA-256 digests, and downloads a ZIP of retained CSV files without uploading plaintext CSV back to GitHub.

For `plain`, users inspect the retained CSV files by downloading the `dashboard-data` workflow artifact.
