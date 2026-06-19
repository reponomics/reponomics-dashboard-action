# Reponomics Dashboard Documentation

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

The Reponomics Dashboard is a GitHub-native repository traffic and growth dashboard. It collects views, clones, top referrers, popular paths, and repository growth counters, then renders static dashboard output during the `publish` workflow.

This generated repository is intentionally thin. The workflows call the local Reponomics wrapper at `.github/actions/reponomics/action.yml`; that wrapper calls the configured `reponomics-dashboard-action` release. The action owns collection, artifact restore/upload, schema migration, encryption, README rendering, dashboard rendering, CSV export packaging, dashboard key rotation, incident reset behavior, and managed local documentation updates.

Template repositories do not require local Python for normal use. Workflows run in GitHub Actions and delegate runtime behavior to `reponomics/reponomics-dashboard-action`.

If a repository uses self-hosted runners, runner images should provide Python `3.11+` and GitHub CLI (`gh`) for setup token validation.

## Repository Model

Your repository owns:

- `config.yaml`
- repository secrets
- workflow schedule and permissions
- the `.reponomics/setup-complete` setup marker
- the configured action version
- retained `dashboard-data` workflow artifacts
- static post-setup README output
- optional committed metric README output when `publish_readme_dashboard` is enabled in a private repository
- optional Reponomics-managed local documentation under `docs/reponomics/`

Your repository does not store any collected data in git. The dashboard HTML is rendered during `publish`; when hosted dashboard publication is enabled, encrypted dashboards are deployed as GitHub Pages artifacts, and otherwise the rendered dashboard remains a downloadable workflow artifact. The default collect-and-publish run publishes from the fresh `dashboard-data` artifact uploaded by the same workflow run. Manual republish restores the latest retained data before rendering. This matters because `overwrite: true` keeps the logical artifact name stable, but each upload still belongs to a specific workflow run.

Collect and publish runs are serialized for `main`. A later scheduled run waits for an older collect-and-publish run instead of cancelling it, so retained artifact lineage is updated in workflow order.

Repository access is part of the dashboard security model. In personal private repositories, collaborators should be treated as trusted with the dashboard control plane, not merely as people who can read a report. See [Repository Access And Trust Boundary](trust-boundary.md).

Common privacy, storage, export, and trust-boundary questions are answered in the [FAQ](faq.md).

For release, dependency, vendored-asset, and generated-artifact verification materials, see [Provenance And Verification Materials](provenance.md).

`COLLECTION_TOKEN` is only for repository data collection, including GitHub traffic data. Create it as a [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new?name=COLLECTION_TOKEN&description=Read%20repository%20data%20for%20Reponomics%20Dashboard&expires_in=366&administration=read), choose the owner whose repositories should be collected, and keep the prefilled repository permission `Administration: read`. Choose **All repositories** for broad automatic discovery, or **Only selected repositories** if you want to limit collection to specific repositories. If you choose selected repositories, keep `config.yaml` within that token's repository access. The setup workflow uses the repository-scoped `GITHUB_TOKEN` to commit workflow enablement changes, and the collect workflow uses the repository-scoped `GITHUB_TOKEN` with job-level `actions: write` for same-repository artifact cleanup after a successful upload, so the collection token does not need repository, Pages, Actions, or Administration write permissions. Ideally, we will have one, limited-scope token responsible for any queries outside of the dashboard repo, and all other operations will be done by the repo's own `GITHUB_TOKEN`. This minimizes the scope of the collection token, which for many users will have access to lots of repositories.

This template currently supports one collection credential. Fine-grained personal access tokens are scoped to one GitHub resource owner. If one dashboard needs to track repositories under multiple users or organizations, the fine-grained token flow is not the right fit for the current single-token setup. Use a classic PAT with `repo` scope where the relevant organizations allow it. Classic PATs are broader and can access repositories your GitHub account can access.

Advanced option: use a user-owned GitHub App installation token for collection instead of a PAT. Reponomics does not provide or operate a shared collection app; the app, installation scope, and credentials are fully user-owned. In this mode, set `use_github_app: true` in `config.yaml`, store `COLLECTION_APP_PRIVATE_KEY` as a repository secret, store `COLLECTION_APP_ID` as a repository variable (or secret), and let the collect workflow mint a short-lived installation token at runtime.

## Configuration

`config.yaml` is the active configuration for this repository. It is user-owned: collection and publication runs read it, but do not silently rewrite it.

`docs/reponomics/config.example.yaml` shows the managed reference configuration shape. The setup fields at the top of `config.yaml` are required and explicit keys in `config.yaml` are treated as your choices.

`.reponomics/setup-complete` is an empty, non-secret marker file. Setup writes it after validating `config.yaml` and required secrets. Generated operational workflows treat its presence as the setup-complete signal; deleting it pauses normal workflow work until setup writes it again. If you intentionally complete `config.yaml` and manage setup manually, recreating the empty marker is acceptable.

The generated `update-docs` workflow updates Reponomics-managed local documentation under `docs/reponomics/` after successful collect-and-publish runs. It writes only that namespace and commits with `[skip ci]`. Disable or delete `.github/workflows/update-docs.yml` before editing that directory yourself.

## Data Modes

`data_mode` is the disclosure control passed to the action.

| Mode | Retained artifact | Hosted dashboard | Downloadable dashboard artifact | Secret requirement | Intended use |
| --- | --- | --- | --- | --- | --- |
| `encrypted` | encrypted `dashboard-data.enc` | optional encrypted Pages artifact | encrypted when hosted publication is disabled | non-empty `DASHBOARD_SECRET_DO_NOT_REPLACE` | default; required for public repositories and hosted Pages dashboards |
| `plaintext` | plaintext retained CSV files | disabled | plaintext, private repositories only | none | private repositories that use GitHub repo/artifact access as the boundary |

`plaintext` is rejected in public repositories. README dashboard generation is rejected in public repositories so repository metrics are not committed to public git history.

> [!NOTE]
> We chose the deliberately outlandish name `DASHBOARD_SECRET_DO_NOT_REPLACE` precisely because there is no other way in the Action > Secrets UI to convey the message to the user that if they want to rotate the key, they should not do so by simply replacing that value, which seems like a tempting mistake.

## Storage

The canonical data store is the `dashboard-data` GitHub Actions artifact.

- `collect` restores the prior artifact, collects current GitHub data, merges and trims retained CSV history, verifies lineage, uploads a new `dashboard-data` artifact, then deletes at most one older superseded `dashboard-data` artifact while keeping rollback artifacts.
- `publish` restores retained data, migrates it to the runtime's current retained-data schema, renders dashboard output, optionally renders private-repository metric README output, and deploys an encrypted Pages artifact for encrypted mode only when hosted dashboard publication is enabled. Otherwise, it uploads a downloadable dashboard artifact.
- `rotate-key` restores encrypted retained state, decrypts with `DASHBOARD_SECRET_DO_NOT_REPLACE`, re-encrypts with `DASHBOARD_NEXT_SECRET`, and publishes rotated encrypted outputs.
- `incident-reset` is a manual emergency workflow for suspected dashboard-key exposure. Make the dashboard repository private and disable any exposed Pages dashboard first. The action restores retained state, decrypts it with `DASHBOARD_SECRET_DO_NOT_REPLACE`, re-encrypts with `DASHBOARD_NEXT_SECRET`, uploads the new retained artifact, then deletes old workflow runs associated with prior `dashboard-data` artifacts.
- `update-docs` runs after successful collect-and-publish runs and writes the action-bundled managed documentation to `docs/reponomics/`.
- `keepalive` runs monthly, updates `.reponomics/keepalive.md`, and tries to create a persistent data safety reminder issue so scheduled collection is less likely to be silently disabled.

Git history is used for configuration, workflow shells, the static setup README, and optional private-repository metric README output. It is not the analytics database.

The template starts with `artifact_retention_days: 90`, which can be set from 14 to 90 days. This controls how long each GitHub Actions artifact remains downloadable if no successor artifact is uploaded. It is not the dashboard history window: retained CSV history can continue accumulating across unbounded collection runs as long as each run restores the current `dashboard-data` artifact and uploads the next one before the prior artifact expires.

## Scheduled Workflow Liveness

GitHub documents that scheduled workflows in public repositories may be disabled automatically after 60 days without repository activity, and inactive scheduled workflows are an operational risk for any dashboard repository. The generated repository enables a monthly keepalive workflow across repository visibility modes. It uses only the repository `GITHUB_TOKEN`, commits `.reponomics/keepalive.md`, and tries to create one persistent data safety reminder issue. This is a best-effort safeguard because GitHub does not precisely define the activity criteria, and GitHub can still change platform behavior. If scheduled workflows stop unexpectedly, download the latest `dashboard-data` artifact before it expires, then re-enable workflows from the Actions tab.

## Incident Response And Outage Preservation

Ordinary collection outages are handled by artifact retention and active supersession rather than a separate preservation workflow. Collection uploads a successor `dashboard-data` artifact before older superseded artifacts are cleaned up. If collection fails, no successor is uploaded and no cleanup is attempted, so the previous unexpired artifact remains the recovery point. If scheduled collection stays disabled past artifact expiry, the GitHub-hosted recovery point can expire even though the product does not impose a fixed maximum history length.

`incident-reset` handles suspected dashboard-key exposure. For serious exposure, make the dashboard repository private and disable any published Pages dashboard first. Then set `DASHBOARD_NEXT_SECRET`, run **Actions -> INCIDENT - Reset**, and enter the required confirmation strings. The reset restores retained state, decrypts it with `DASHBOARD_SECRET_DO_NOT_REPLACE`, re-encrypts it with `DASHBOARD_NEXT_SECRET`, uploads the fresh retained artifact, then deletes old workflow runs associated with prior `dashboard-data` artifacts. The generated workflow has a 30-minute timeout. After the run succeeds, promote `DASHBOARD_NEXT_SECRET` into `DASHBOARD_SECRET_DO_NOT_REPLACE`, then delete `DASHBOARD_NEXT_SECRET`.

## CSV Export

Encrypted hosted dashboards include an `Export CSV` control after unlock. The browser downloads an encrypted export asset, decrypts it locally with the dashboard key, verifies ciphertext and plaintext SHA-256 digests, and downloads a canonical ZIP of retained CSV files. Plaintext CSV is not uploaded back to GitHub during export.

Generated HTML dashboards use a chunked data model: the page loads a summary first and loads per-repository detail chunks only as repositories are selected for display. In encrypted mode, the summary and chunks are encrypted. In plaintext mode, the same summary/chunk boundary is used for the downloadable plaintext HTML artifact, but it does not add confidentiality.

For plaintext retained data, download the `dashboard-data` workflow artifact directly.

## Offline Viewing

The generated dashboard is not committed to this repository. To view an encrypted dashboard offline, open a successful **Collect and Publish** workflow run and download the dashboard artifact before it expires. Extract the artifact and open `index.html` with the same dashboard key that unlocks the hosted Pages dashboard.

Some browsers block local `file://` fetches used by CSV export. If export fails offline, serve the extracted artifact directory over local HTTP or use the hosted Pages dashboard.

## Key Rotation

1. Generate and save a new dashboard key.
2. Add it as `DASHBOARD_NEXT_SECRET`.
3. Run **Actions -> Rotate Key -> Run workflow**.
4. Confirm the dashboard opens with the new key.
5. Replace `DASHBOARD_SECRET_DO_NOT_REPLACE` with the new key (this a rare instance in which you are allowed to disobey the instructions in the secret's name).
6. Delete `DASHBOARD_NEXT_SECRET`.

Normal collection refuses to run while `DASHBOARD_NEXT_SECRET` is set, so rotation cannot be left half-finished unnoticed.

## GitHub Pages

For a hosted encrypted dashboard, manually configure this repository's **Settings -> Pages** page so **Build and deployment -> Source** is **GitHub Actions**. The Reponomics publish workflow renders the dashboard shell and uploads it as a GitHub Pages artifact only when hosted publication is enabled; retained dashboard data remains in the `dashboard-data` Actions artifact. The action verifies the existing Pages setting during deployment, but it does not enable Pages or change the publishing source. If GitHub suggests workflow templates while you are changing the setting, skip them.

> [!WARNING]
> Unless your GitHub plan provides Pages access controls, a GitHub Pages site is reachable on the internet even when the repository is private. Use `data_mode: encrypted` when the hosted dashboard must not disclose metrics to people without the dashboard key.
