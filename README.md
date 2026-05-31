# Reponomics Dashboard Action


![GitHub License](https://img.shields.io/github/license/reponomics/reponomics-dashboard-action)
![GitHub Release](https://img.shields.io/github/v/release/reponomics/reponomics-dashboard-action)
![GitHub Release Date](https://img.shields.io/github/release-date/reponomics/reponomics-dashboard-action)
![GitHub commits since latest release](https://img.shields.io/github/commits-since/reponomics/reponomics-dashboard-action/latest)

[![CI](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/ci.yml)
[![Action pins](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/validate-action-pins.yml/badge.svg?branch=main)](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/validate-action-pins.yml)
[![Vendored assets](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/validate-vendored-assets.yml/badge.svg?branch=main)](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/validate-vendored-assets.yml)
[![Runtime lock](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/validate-runtime-lock.yml/badge.svg?branch=main)](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/validate-runtime-lock.yml)
[![Scorecard supply-chain security](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/scorecard.yml/badge.svg)](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/scorecard.yml)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/12954/badge)](https://www.bestpractices.dev/projects/12954)

[![CodeQL](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/github-code-scanning/codeql)
[![Dependabot Updates](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/dependabot/dependabot-updates/badge.svg)](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/dependabot/dependabot-updates)
[![Dependency Graph](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/dependabot/update-graph/badge.svg)](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/dependabot/update-graph)
[![OSV SARIF scan](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/osv-scanner.yml/badge.svg)](https://github.com/reponomics/reponomics-dashboard-action/actions/workflows/osv-scanner.yml)

GitHub Action for the [Reponomics Dashboard template repository](https://github.com/reponomics/reponomics-dashboard). A composite action that handles data collection through the GitHub API, artifact storage in CSV format, data encryption, and rendering of the README and HTML dashboard for the Reponomics Dashboard. You're welcome to use it in any way you like (and if you do, we'd love to hear about what you built!). But for the purposes of explanation, we will mostly assume that it is being used in the workflows provided by our template repo.

The Reponomics Dashboard provides a simple, free, and private way to collect, aggregate, store, and analyze traffic and growth data for all of your GitHub repositories in one place, as well as a rich analytics dashboard that can be hosted privately, via strong encryption, on your public GitHub Pages site. To use this action, all you need to do is copy our template repository, which has everything you need to start collecting your own data and hosting your own repo analytics dashboard straight from GitHub - no strings attached. Easy to set up in five minutes, no subscription, no third-party services, no ads or trackers, and no fees. Just making the most out of the data and resources that GitHub already provides to every maintainer, whether you're on a paid plan or the free tier.

> [!WARNING]
> Public pre-release: this repository is visible for review and hardening, but it is not yet promoted for general use. Do not expect stable behavior or seamless upgrades before `v1`.

## Action Modes

This is a composite action that does a lot of different things for the Reponomics Dashboard. These are the primary "modes" in which it is used:

- `collect`: queries the GitHub API on a daily schedule and collects growth metrics (stars/subscribers, forks, etc.) and, most importantly, traffic data (viewers, views, clones, top referrers, and most popular content), which GitHub provides but only for a bounded, 14-day rolling window. Collecting and persisting this ephemeral data is one of the most important tasks for the Reponomics Dashboard action, since if you aren't storing the data while GitHub makes it available, there's no way to retroactively query it. Even if you have no desire for a hosted dashboard, a turnkey way to aggregate and persist this data in a portable CSV format is in itself highly valuable. In order to keep your data separate from your git history, `collect` mode stores data in _workflow artifacts_ - data that is stored and managed by GitHub but is not part of your repository's git history.

- `publish`: renders dashboard outputs from retained data. `publish` is responsible for producing visual assets like the HTML dashboard and the README dashboard, and then serving the HTML dashboard through GitHub Pages, when enabled.

- `rotate-key`: the Reponomics Dashboard makes it easy for users to rotate their key in case they lose access to it. So long as the previous key is still stored in the repo as a repository secret, the workflow is able to download the encrypted artifact and decrypt it. So, all that's needed for key rotation is a new key. This should give you peace of mind that losing your encryption key is not going to lead to permanent loss of your data. On the other hand, this means you must be extra vigilant about who is able to execute your workflows. _Anyone with the ability to set a new secret and run the `rotate-key` workflow is able to change your secret._

- `incident-reset`: handles scenarios where your encryption key has been exposed publicly, exfiltrated, or otherwise compromised, and you deem it necessary to not only rotate to a new key, but destroy all previous artifacts from workflow runs that have not expired. Workflow artifacts are accessible to anyone with read access to your repository - in the case of public repositories, that means any GitHub user at all. Fortunately, it is possible to mitigate the damage - artifacts are not part of git history, so workflow runs and their artifacts can be deleted without any knock-on effects.

## Upgrade Model

Use normal GitHub Action refs to choose the upgrade cadence:

- `reponomics/reponomics-dashboard-action@v1` receives compatible fixes and feature additions published on the `v1` major line.
- `reponomics/reponomics-dashboard-action@v1.2.3` is pinned. Pinned workflows are not automatically upgraded; during `publish` runs the generated dashboard can show compact action version status with a link to the latest stable release.

Retained dashboard data artifacts are migrated by the runtime during `collect`, `publish`, `rotate-key`, and `incident-reset`. These schema migrations are internal compatible runtime behavior, not a public action mode, and they do not rewrite the caller-owned `config.yaml`.

New metrics can appear after a compatible upgrade once collection has run with the newer runtime. Historical rows keep blank values unless a safe migration default exists.

## Usage

Caller workflows are responsible for checkout, scheduling, permissions, secrets, and version pinning. `publish-pages: true` deploys dashboards with GitHub Pages Actions artifacts during `publish` and `rotate-key` runs when privacy mode is `strong` or `casual`, so those workflows need `pages: write` and `id-token: write`. The repository owner must first configure the repository's Pages source to **GitHub Actions** in the GitHub UI; this action verifies that configuration and deploys to it, but does not enable Pages or change the publishing source. `publish-pages: false` keeps dashboards downloadable as workflow artifacts (`html-dashboard-encrypted` or `html-dashboard-plain`) instead of deploying Pages. Plain mode always disables Pages deployment. Workflows only need `contents: write` when `generate-readme: true` is used to generate and commit README output or when `docs-sync` commits managed documentation. `incident-reset` requires `actions: write` because it deletes prior workflow runs and fallback artifacts after rotating retained encryption to `dashboard-next-secret`.

```yaml
steps:
  - uses: actions/checkout@v6

  - uses: reponomics/reponomics-dashboard-action@v1
    with:
      mode: collect
      collection-token: ${{ secrets.COLLECTION_TOKEN }}
      github-token: ${{ github.token }}
      dashboard-secret: ${{ secrets.DASHBOARD_SECRET_DO_NOT_REPLACE }}
      privacy-mode: strong
```

## Inputs

> [!NOTE]
> Default sources below assume the consuming workflow follows the Reponomics Dashboard template repository wiring for tokens and secrets. If you decide to use this action outside of that template, pass explicit `with:` input values.

For `collection-token`, use a [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new?name=COLLECTION_TOKEN&description=Read%20repository%20data%20for%20Reponomics%20Dashboard&expires_in=366&administration=read) with repository `Administration: read` for the owner/repositories being collected. Choose **All repositories** for broad automatic discovery, or **Only selected repositories** for a narrower dashboard. If you choose selected repositories, keep the dashboard configuration within that token's repository access. It does not need Pages or Administration write permissions.

This action accepts one `collection-token`. Fine-grained personal access tokens are scoped to one GitHub resource owner, so a fine-grained token is the right fit only when the dashboard collects from one user or organization owner. If one dashboard must span multiple owners today, the current single-token fallback is a classic PAT with `repo` scope where the relevant organizations allow it.

Advanced users may use a user-owned GitHub App installation token instead of a PAT for `collect` mode. Reponomics does not provide or operate a shared app for user dashboards; you create and control your own GitHub App installation. In that path, mint a short-lived installation token in the workflow, pass it as `collection-token`, and set `use-github-app: true`.

> [!NOTE]
> We chose the deliberately outlandish name `DASHBOARD_SECRET_DO_NOT_REPLACE` because the Actions > Secrets UI does not provide another affordance where we can warn users that if they want to rotate their secret, simply overwriting the existing secret is not the correct way to do so, and will in fact result in permanent data loss if the previous secret was not retained by the user.

| Input | Description | Default |
|---|---|---|
| `mode` | Runtime mode. Allowed values: `collect`, `publish`, `rotate-key`, `incident-reset`, `docs-sync`. | `collect` |
| `collection-token` | Token for GitHub repository data collection APIs. Usually a fine-grained PAT; advanced option: user-owned GitHub App installation token minted in-workflow. | Value of `${{ secrets.COLLECTION_TOKEN }}` in the consuming repository workflow. |
| `use-github-app` | Advanced collect-mode toggle. Set `true` when `collection-token` is a GitHub App installation token (user-owned app), so discovery/validation uses app-installation endpoints. | `false` |
| `github-token` | Token for artifact/repository workflow operations. | Value of `${{ github.token }}` in the consuming repository workflow/job. |
| `dashboard-secret` | Current dashboard/artifact encryption key (required for `strong` and `casual`). | Value of `${{ secrets.DASHBOARD_SECRET_DO_NOT_REPLACE }}` in the consuming repository workflow. |
| `dashboard-next-secret` | Next dashboard/artifact encryption key for `rotate-key` and `incident-reset` (required for `strong` and `casual` rotate-key/incident-reset runs). | Value of `${{ secrets.DASHBOARD_NEXT_SECRET }}` in the consuming repository workflow. |
| `incident-confirm-mode` | Destructive `incident-reset` confirmation; must be `INCIDENT_RESET_CONFIRMED` when `mode: incident-reset`. | `""` |
| `incident-confirm-purge` | Destructive `incident-reset` confirmation; must be `PURGE_OLD_HISTORY_CONFIRMED` when `mode: incident-reset`. | `""` |
| `incident-confirm-irreversible` | Destructive `incident-reset` confirmation; must be `IRREVERSIBLE_ACTION_CONFIRMED` when `mode: incident-reset`. | `""` |
| `privacy-mode` | Privacy model. Allowed values: `strong`, `casual`, `plain`. Public repositories may use `strong` or `casual`; `plain` is private-repository only. | `strong` |
| `config-path` | Repository selection config path in the caller repository. | `config.yaml` |
| `retention-days` | GitHub Actions artifact retention period (1-90 days). | `90` |
| `publish-pages` | Set `false` to keep rendered dashboards as downloadable workflow artifacts instead of deploying GitHub Pages. Plain mode always disables Pages deployment. | `true` |
| `artifact-run-id` | Optional workflow run ID whose `dashboard-data` artifact should be restored. Use this when a downstream publish run must render the artifact produced by a specific collect run. If set, a missing or unreadable artifact fails the run. | Latest available `dashboard-data` artifact. |
| `generate-readme` | Generate README dashboard output and commit it back to the caller repository. When `false`, README rendering is skipped. (NOTE: README dashboards may only be enabled in private repositories.) | `false` |
| `allow-docs-sync` | Optional override for managed documentation updates in `docs/reponomics/`; set `true` or `false`. | Uses `allow_docs_sync` in `config.yaml`; otherwise allows sync. |
| `readme-path` | README output path. | `README.md` |

## Outputs

The action emits metadata for workflow summaries and later automation:

- `tracked-repos`
- `collected-at`
- `artifact-mode`
- `publish-pages`: `true` when the rendered dashboard is published to GitHub Pages, `false` when it is only uploaded as a workflow artifact
- `pages-path`: rendered dashboard directory uploaded to Pages or a downloadable dashboard artifact
- `page-url`
- `readme-updated`
- `dashboard-updated`
- `schema-version`
- `runtime-version`
- `docs-sync-state`
- `docs-action-version`
- `docs-updated-at`

`collect` updates only the retained `dashboard-data` artifact. `publish` restores that artifact and always renders dashboard output from retained data. When `artifact-run-id` is set, publish restores the `dashboard-data` artifact from that workflow run instead of the latest artifact. For `strong` and `casual`, `publish-pages: true` deploys an encrypted Pages dashboard and `publish-pages: false` uploads an encrypted dashboard artifact (`html-dashboard-encrypted`). For private `plain`, publish uploads a non-Pages plain dashboard artifact (`html-dashboard-plain`) for download. When `generate-readme` is `true`, publish also renders and commits the README summary. `docs-sync` updates the Reponomics-managed local documentation namespace at `docs/reponomics/` when enabled. The retained CSV data is not committed to the repository. `rotate-key` re-encrypts encrypted retained state and encrypted dashboard output; with `publish-pages: false` it uploads `html-dashboard-encrypted` instead of deploying Pages. `incident-reset` re-encrypts retained state with `dashboard-next-secret`, deletes prior runs from the same workflow, and deletes any remaining `dashboard-data` artifacts tied to those old runs.

README metrics are derived from repository visibility: private dashboard repositories may render README metrics, while public dashboard repositories render a non-metric README status block. Plain mode stores plaintext CSV artifacts and is rejected in public repositories.

## GitHub Pages Setup

For a hosted encrypted dashboard, configure Pages once in the dashboard repository before relying on `publish` deployment:

1. Open the dashboard repository on GitHub.
2. Go to **Settings**.
3. In the sidebar, open **Pages**.
4. Under **Build and deployment**, set **Source** to **GitHub Actions**.
5. If GitHub suggests workflow templates, skip them. The Reponomics publish workflow already uploads and deploys the dashboard artifact.

Do not select **Deploy from a branch** for Reponomics dashboard publishing. Do not grant Pages or Administration write permissions to `COLLECTION_TOKEN` for this setup. `COLLECTION_TOKEN` is for repository data collection, including GitHub traffic data; Pages deployment uses the workflow `GITHUB_TOKEN` with the permissions declared by the consuming workflow.

## Offline Viewing

Generated dashboard files are not committed to the repository. This keeps retained history out of git, but it means offline viewing starts from a workflow artifact rather than from a tracked dashboard file in the repo.

After a successful encrypted `publish` run, open the workflow run's **Summary** page and download the `html-dashboard-encrypted` artifact before it expires. Extract it and open `index.html`. Use the same dashboard key that unlocks the hosted Pages dashboard.

For private repositories in `privacy-mode: plain`, `publish` uploads a plain dashboard artifact named `html-dashboard-plain`. Download that artifact from the workflow run and open `index.html` directly.

You can also download the dashboard with GitHub CLI if you have repository read access. Replace `OWNER/REPO` with the dashboard repository, use `gh run list --repo OWNER/REPO --status success --limit 10` to find the latest successful `publish` workflow run, and replace `RUN_ID` with that run ID.

For encrypted `strong` or `casual` output with `publish-pages: true`, download the encrypted dashboard artifact:

```bash
rm -rf .reponomics-dashboard
mkdir -p .reponomics-dashboard
gh run download RUN_ID --repo OWNER/REPO --name html-dashboard-encrypted --dir .reponomics-dashboard
tar -xf .reponomics-dashboard/artifact.tar -C .reponomics-dashboard
python3 -m http.server 8000 --directory .reponomics-dashboard
```

Then open `http://localhost:8000/` and unlock the dashboard with `DASHBOARD_SECRET_DO_NOT_REPLACE`.

For encrypted `strong` or `casual` output with `publish-pages: false`, download the encrypted dashboard artifact:

```bash
rm -rf .reponomics-dashboard
mkdir -p .reponomics-dashboard
gh run download RUN_ID --repo OWNER/REPO --name html-dashboard-encrypted --dir .reponomics-dashboard
python3 -m http.server 8000 --directory .reponomics-dashboard
```

When `publish-pages: true`, the downloaded artifact contains `artifact.tar`; extract it before serving. When `publish-pages: false`, files are available directly after `gh run download`.

For private `plain` output, download the plain dashboard artifact:

```bash
rm -rf .reponomics-dashboard
mkdir -p .reponomics-dashboard
gh run download RUN_ID --repo OWNER/REPO --name html-dashboard-plain --dir .reponomics-dashboard
python3 -m http.server 8000 --directory .reponomics-dashboard
```

For encrypted dashboards, after unlock, use the dashboard `Export CSV` control to download a canonical ZIP of retained CSV files. Export delivery is browser-local: ciphertext is fetched from a published encrypted asset and decrypted in memory before download. The runtime verifies both encrypted-asset and decrypted-bundle digests before download. Plaintext export data is not uploaded back to GitHub by this path. Export scope is canonical retained history, including repos that are currently excluded from dashboard rendering.

See [CSV Export Architecture Guide](./docs/CSV_EXPORT.md) for implementation details, integrity model boundaries, and payload size-estimation formulas.

Local-file browser restrictions can block `fetch()` for `file://` origins in some environments. When that happens, use the hosted Pages dashboard or serve the extracted artifact directory over local HTTP.

Artifact availability follows `retention-days`; the default is 90 days.

## Privacy Modes

The action permits three distinct "privacy modes". In `strong` and `casual` modes, all data and generated artifacts are encrypted, and require the user to generate an encryption secret, which they must store in their repo as a repository secret. In `plain` mode, repository metrics are not encrypted. The purpose of the Reponomics Dashboard is to provide users with safe and secure access to private analytic data about their repositories. So, in order to maintain conceptual clarity about the privacy model that is being employed, so that users do not have to worry about making a configuration choice that will unintentionally expose their data, we impose certain constraints for each of these "modes":

- `strong` - in this mode, users must generate an encryption secret that is high-entropy, and is not vulnerable to offline brute-force attacks. If `publish-pages: true`, your dashboard is published to the open internet and can be downloaded, so an attacker can apply brute-force techniques indefinitely without detection; this mode exists to protect against that attack class. If `publish-pages: false`, the encrypted dashboard is still downloadable to repository readers as a workflow artifact, so strong secrets remain the right default for high-assurance repositories. When this mode is selected, workflows using this action will _fail_ if a weak secret is detected. (For our purposes, we simply judge based on the length of the secret, which must be at least 40 characters - however we _strongly_ urge you to use one of our recommended methods to generate a truly high-entropy secret. Failure to do so (e.g. a 40-character sequence of `1`s) may pass our smell test, but will not provide any measure of privacy, and in the end it's up to the user if they wish to "cheat" the action in this way.) In order to generate a high-entropy secret, you can use one of the following methods:

  i) In a compatible terminal:
  ```bash
  openssl rand -hex 32
  ```

  Base64 secrets with the same entropy are also acceptable, but characters such as `+`, `/`, and `=` are easier to mishandle in shells, URLs, and copy/paste flows.

  ii) Using the Web Crypto API, open your developer tools console and copy/paste (or type, if you prefer), the following command:

  ```javascript
  Array.from(crypto.getRandomValues(new Uint8Array(32)), b => b.toString(16).padStart(2, "0")).join("")
  ```

  Both of these methods will produce a secret that is sufficiently high-entropy that no atacker will be able to decrypt your data with brute-force using consumer hardware within the span of their lifetime.

  Once you've done this, and you have stored the secret in your repository under the default name `DASHBOARD_SECRET_DO_NOT_REPLACE`, be sure to store it in your preferred password manager as this will also be your "login" password for your hosted dashboard. (Don't worry, if you lose access to the secret, you can rotate it so long as you have control of the repository's workflows, and the previous secret has not been changed, erased, or destroyed.)


 - `casual` - in this mode, all data and data-sensitive artifacts are also encrypted, but the action does not care if you use a strong or a weak password. The justification for this is that these modes provide privacy against different "threat models". If you decide to host your dashboard on GitHub Pages, then even a weak password will prevent "any passers-by" from simply viewing your dashboard without first going through the login/decryption flow. For the reasons stated above, weak passwords may easily be bypassed by any _targeted_ attack against your data. But for many users, a simple flow that deters casual users who happen upon their page from viewing the data is more than sufficient. That is the purpose of this mode.

 - `plain` - in this mode, there is no encryption or decryption of your data. It is stored in workflow artifacts in plain text. Therefore, because workflow artifacts are accessible to anyone who has read access to your repo, and our policy is to make it very difficult for a user to accidentally make a configuration decision that exposes their data, _`plain` mode is only available in private repos, and the action will not publish your dashboard to GitHub Pages in unencrypted form_. Instead, `publish` generates a plain dashboard and uploads it as a private workflow artifact (`html-dashboard-plain`) for download. This is not intended to make your life difficult, and after all, this action is open source, and if you wish to use it in some unintended way, that is within your rights. We impose these restrictions to give users peace of mind that accidental exposure of their data is not possible simply due to misconfiguration of the action or the template repo.

These modes are the best compromise that we could find between giving users a degree of flexibility with respect to their own privacy model, while ensuring that they do not have to worry about their data being published in unencrypted form simply because they "did not read the manual" closely enough.

That being said, we _must_ remind users that the safeguards provided are not strict guarantees. They provide strong resistance against exposure of a particular sort of threat vector. The encryption schemes described above cannot defend against malicious JavaScript, compromised CI/CD or supply chain risks, malicious or privacy-invasive browser extensions, malicious behavior of any collaborators, or accidentally sharing your secret on social media. In fact, anyone who is able to run the secret-rotation workflow may overwrite the existing secret with any value that they choose. So, you must also keep this fact in mind - although once set, a repository secret cannot simply be retrieved from the API, for example, anyone whose permissions allow them to execute the rotation-workflow, or indeed any workflow which would give them access to the `secrets` context, is able to exfiltrate and/or change your secret, irreversibly.

If you believe your secret has been exposed or compromised, you may read about our mitigiation protocols.

## Growth Metrics

Repository growth metrics use the GitHub repository detail API fields with their GitHub meanings:

- Stars are `stargazers_count`.
- Watchers are GitHub repository subscribers from `subscribers_count`.
- Forks are `forks_count`.
- GitHub's `watchers_count` field is not used as true watchers because that field mirrors stargazers on GitHub repository responses.

## Community Health Metrics

Per-repository community health metrics are collected from `GET /repos/{owner}/{repo}/community/profile` and persisted in `repo-metrics.csv` alongside growth counters.

Tracked values include:

- `community_health_percentage`
- documentation URL and profile timestamp
- file-presence signals for code of conduct, contributing guide, issue template, pull request template, README, and license

These fields are surfaced in the dashboard Repositories table under the Community column.

For public repositories, GitHub does not require special token permissions for this endpoint. If you want to track community health for private repositories, add repository `Contents: read` to the fine-grained personal access token used for collection.

## Local Development

```bash
make install
make pre-commit-install
make ci
```

Individual targets include `make lint`, `make type-check`, `make validate`, `make test`, and `make coverage`.

Run the configured commit hooks across the full tree with:

```bash
make pre-commit-run
```

Fixture checks stop before any live GitHub staging validation:

```bash
make fixture-collect
make fixture-publish
make fixture-rotate-key
make preview-collection-quality-dashboard
```

`preview-collection-quality-dashboard` uses fixture data from `tests/fixtures/collection_quality_preview` and renders a local publish output at `.tmp/collection_quality_preview/docs/index.html`.

## Maintainer Release Policy

Generated dashboards render compact local action version status only: current runtime version, latest stable release when the GitHub Releases API check succeeds, whether an update is available, and a link to the release or releases page. Release bodies, summaries, Markdown, and HTML are never rendered into user repositories.

Compatibility fixtures are part of the action CI policy. For each supported prior artifact/config shape, keep deterministic tests that run old config plus old retained artifact data through `collect`, `publish`, and encrypted `rotate-key` where encryption applies. These checks must verify migrated artifact schema, preserved historical data, rendered output compatibility, and that normal modes do not silently mutate user-owned `config.yaml`.
