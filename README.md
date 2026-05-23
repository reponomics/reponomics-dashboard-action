# Reponomics Dashboard Action

[![CI](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/ci.yml)
[![Action pins](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/validate-action-pins.yml/badge.svg?branch=main)](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/validate-action-pins.yml)
[![Vendored assets](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/validate-vendored-assets.yml/badge.svg?branch=main)](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/validate-vendored-assets.yml)

GitHub Action for Reponomics dashboards.

> [!WARNING]
> Public pre-release: this repository is visible for review and hardening, but it is not yet promoted for general use. Do not expect stable behavior or seamless upgrades before `v1`.

This action collects GitHub traffic data, keeps retained CSV data in a GitHub Actions artifact, renders the dashboard shell during `publish`, and supports dashboard/artifact key rotation.

## Upgrade Model

Before `v1`, users should not expect seamless updates between versions. Pre-release versions may change action inputs, generated dashboard structure, retained artifact schema, or migration behavior while the project is being hardened. Pin exact refs and review release notes before moving between pre-`v1` versions.

Use normal GitHub Action refs to choose the upgrade cadence:

- `reponomics/reponomics-dashboard-action@v1` receives compatible fixes and feature additions published on the `v1` major line.
- `reponomics/reponomics-dashboard-action@v1.2.3` is pinned. Pinned workflows are not automatically upgraded; they receive update notices during `publish` runs when a compatible newer release advertises one.

Retained traffic artifacts are migrated by the runtime during `collect`, `publish`, and `rotate-key`. These schema migrations are internal compatible runtime behavior, not a public action mode, and they do not rewrite the caller-owned `config.yaml`.

New metrics can appear after a compatible upgrade once collection has run with the newer runtime. Historical rows keep blank values unless a safe migration default exists.

## Usage

Caller workflows are responsible for checkout, scheduling, permissions, secrets, and version pinning. Hosted Pages dashboards are deployed with GitHub Pages Actions artifacts during `publish` and `rotate-key` runs for `strong` and `casual` privacy modes, so those workflows need `pages: write` and `id-token: write`. Workflows only need `contents: write` when `commit-outputs: true` is used to commit README output.

```yaml
steps:
  - uses: actions/checkout@v6

  - uses: reponomics/reponomics-dashboard-action@v1
    with:
      mode: collect
      traffic-token: ${{ secrets.TRAFFIC_TOKEN }}
      github-token: ${{ github.token }}
      dashboard-secret: ${{ secrets.TRAFFIC_DASHBOARD_SECRET }}
      privacy-mode: strong
```

## Inputs

| Input | Default | Notes |
|---|---:|---|
| `mode` | `collect` | `collect`, `publish`, or `rotate-key`. |
| `traffic-token` | empty | Token for GitHub traffic/repository APIs. Falls back to `TRAFFIC_TOKEN` or `GH_TOKEN`. |
| `github-token` | empty | Token for artifact/repository workflow operations. Falls back to `GITHUB_TOKEN` or `GH_TOKEN`. |
| `dashboard-secret` | empty | Current dashboard/artifact encryption key. Falls back to `TRAFFIC_DASHBOARD_SECRET`. |
| `dashboard-next-secret` | empty | Next key for `rotate-key`. Falls back to `TRAFFIC_DASHBOARD_NEXT_SECRET`. |
| `privacy-mode` | `strong` | `strong`, `casual`, or `plain`. Public repositories may use `strong` or `casual`; `plain` is private-repository only. |
| `config-path` | `config.yaml` | Repository selection config in the caller repo. |
| `retention-days` | `90` | Artifact retention, 1-90 days. |
| `commit-outputs` | `false` | Commit rendered README output. Generated Pages dashboard files are deployed as GitHub Pages artifacts instead of committed. |
| `readme-path` | `README.md` | README output path. |
| `update-notices` | `true` | Best-effort metadata-only update notices from constrained Reponomics GitHub Release metadata. Set `false` to disable. |

## Outputs

The action emits metadata for workflow summaries and later automation:

- `tracked-repos`
- `collected-at`
- `artifact-mode`
- `dashboard-mode`
- `pages-path`
- `page-url`
- `readme-updated`
- `dashboard-updated`
- `schema-version`
- `runtime-version`

`collect` updates only the retained `traffic-data` artifact. `publish` restores that artifact, renders any allowed README summary and dashboard shell from retained data, and deploys an encrypted dashboard for `strong` and `casual` privacy modes. The retained CSV data is not committed to the repository. `rotate-key` re-encrypts encrypted retained state and encrypted dashboard output.

README metrics are derived from repository visibility: private dashboard repositories may render README metrics, while public dashboard repositories render a non-metric README status block. Plain mode stores plaintext CSV artifacts and is rejected in public repositories.

## Offline Viewing

Generated dashboard files are not committed to the repository. This keeps traffic history out of git, but it means offline viewing starts from a workflow artifact rather than from `docs/index.html` in the repo.

After a successful encrypted `publish` run, open the workflow run's **Summary** page, download the GitHub Pages artifact before it expires, extract it, and open `index.html`. Use the same dashboard key that unlocks the hosted Pages dashboard.

After unlock, use the dashboard `Export CSV` control to download a canonical
ZIP of retained CSV files. Export delivery is browser-local: ciphertext is
fetched from a published encrypted asset and decrypted in memory before
download. Plaintext export data is not uploaded back to GitHub by this path.

Local-file browser restrictions can block `fetch()` for `file://` origins in
some environments. When that happens, use the hosted Pages dashboard or serve
the extracted artifact directory over local HTTP.

Artifact availability follows `retention-days`; the default is 90 days.

## Privacy Modes

`strong` mode encrypts retained artifacts and hosted dashboards with a generated high-entropy secret. Store the secret in a secret manager or GitHub Actions secret. Prefer a shell-safe 256-bit hex secret:

```bash
openssl rand -hex 32
```

Base64 secrets with the same entropy are also acceptable, but characters such as `+`, `/`, and `=` are easier to mishandle in shells, URLs, and copy/paste flows.

`casual` mode also encrypts retained artifacts and hosted dashboards, but accepts any non-empty dashboard secret. It prevents casual viewing, crawling, and accidental discovery. It is not target-resistant because a weak or shared secret can be brute-forced offline from the encrypted payload.

`plain` mode stores retained CSV artifacts without encryption and does not require a dashboard secret. It is only supported for private dashboard repositories. Public repositories must use `strong` or `casual`.

Encrypted Pages protects the static payload from disclosure without the key, but browser-side crypto cannot defend against malicious JavaScript, compromised CI/deployment, malicious browser extensions, endpoint compromise, or accidental secret leakage.

## Growth Metrics

Repository growth metrics use the GitHub repository detail API fields with their GitHub meanings:

- Stars are `stargazers_count`.
- Watchers are GitHub repository subscribers from `subscribers_count`.
- Forks are `forks_count`.
- GitHub's `watchers_count` field is not used as true watchers because that field mirrors stargazers on GitHub repository responses.

## Local Development

```bash
make install
make pre-commit-install
make ci
```

Individual targets include `make lint`, `make type-check`, `make validate`,
`make test`, and `make coverage`.

Run the configured commit hooks across the full tree with:

```bash
make pre-commit-run
```

Fixture checks stop before any live GitHub staging validation:

```bash
make fixture-collect
make fixture-publish
make fixture-rotate-key
```

## Maintainer Release Policy

Release notes that should trigger an in-dashboard update notice must include one constrained metadata block:

```markdown
<!-- reponomics-update {"title":"Upgrade available","summary":"Compatible runtime and artifact migration update.","min_runtime_version":"0.1.0","action_refs":["v1"]} -->
```

Supported keys are `title`, `summary`, `min_runtime_version`, `max_runtime_version`, `action_refs`, and `action_repository`. `action_refs` may be `"*"` or a list of exact refs such as `["v1", "v1.2.3"]`. `action_repository`, when present, must be `reponomics/reponomics-dashboard-action`. Only the parsed metadata is rendered; arbitrary remote release Markdown is not rendered into user dashboards.

Validate release-note files before publication:

```bash
venv/bin/python scripts/validate_release_notice.py path/to/release-notes.md
make validate-release-notice
```

Compatibility fixtures are part of the action CI policy. For each supported prior artifact/config shape, keep deterministic tests that run old config plus old retained artifact data through `collect`, `publish`, and encrypted `rotate-key` where encryption applies. These checks must verify migrated artifact schema, preserved historical data, rendered output compatibility, and that normal modes do not silently mutate user-owned `config.yaml`.
