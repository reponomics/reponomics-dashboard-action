# Reponomics Dashboard

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this repository should not be considered authoritative.

This is the setup README for your Reponomics dashboard repository. It helps you configure collection, privacy, and dashboard publication before the first setup run. Setup may replace this file with a shorter post-setup README, and private repositories can later opt into a generated metrics README dashboard.

The dashboard collects GitHub traffic and growth data, stores retained state in GitHub Actions artifacts, and renders optional dashboard outputs through GitHub Actions. The repository stays intentionally thin: collection, encryption, rendering, key rotation, incident reset behavior, CSV export, and managed docs sync are owned by the versioned action:

```yaml
uses: reponomics/reponomics-dashboard-action@v0
```

## Get Started

1. Review `config.yaml` and decide which repositories this dashboard should track.
2. Create a collection credential and store it as the repository secret `COLLECTION_TOKEN`. Most single-owner dashboards should use a fine-grained personal access token with repository `Administration: read`.
3. Choose a privacy mode: `strong`, `casual`, or `plain`. Public repositories should normally use `strong`.
4. For `strong` or `casual`, generate and save `DASHBOARD_SECRET_DO_NOT_REPLACE`, then add it as a repository secret. See [Secure Dashboard Key Generation](docs/reponomics/secure-dashboard-key.md).
5. Run **Actions -> Set up Reponomics dashboard -> Run workflow**.
6. If you enable hosted dashboard publication, open **Settings -> Pages** and set **Build and deployment -> Source** to **GitHub Actions**.

Setup writes your selected options to `config.yaml`, creates the empty `.reponomics/setup-complete` marker, and replaces this README. Operational workflows are present before setup but do no work until that marker exists. Setup does not collect traffic immediately. Collection runs on the configured schedule and stores retained data in the `dashboard-data` Actions artifact.

## Configuration

`config.yaml` is owned by this repository. Reponomics reads it during workflow runs but does not silently rewrite it.

```yaml
max_repos: 200

include_only:
  # - owner/repo-name

include:
  # - owner/important-repo

exclude:
  # - owner/noisy-repo

include_others: true
include_new: false
include_private: true

# Optional: disable Reponomics-managed local docs updates.
allow_docs_sync: true
```

If `include_only` is non-empty, Reponomics tracks exactly those repositories and ignores the automatic pool. For more detail, see [Dashboard repository documentation](docs/reponomics/repository-guide.md).

### Token Scope And Repository Owners

Repository entries use full `owner/repo` names because a dashboard can be configured against repositories owned by users or organizations. The token you choose still controls which owners can actually be collected.

Fine-grained personal access tokens are scoped to one GitHub resource owner. If your dashboard only tracks repositories under one user or one organization, a fine-grained token with repository `Administration: read` is the preferred path.

This template currently supports one collection credential. If one dashboard needs to track repositories under multiple users or organizations, the fine-grained token flow is not the right fit for the current single-token setup. Use a classic PAT with `repo` scope where the relevant organizations allow it. Classic PATs are broader and can access repositories your GitHub account can access, so use this fallback only when the dashboard really needs to span owners.

## Privacy And Output

The canonical store is the `dashboard-data` Actions artifact.

- `strong` and `casual` store encrypted retained data.
- `plain` stores retained CSV files directly in the artifact and is rejected in public repositories.
- Hosted encrypted dashboard publication is optional and requires GitHub Pages to use GitHub Actions as the deployment source.
- Plain-mode HTML dashboards are private-repository downloadable artifacts only and are not published to Pages.
- Metric README dashboard generation is only available in private repositories.

For the full mode comparison, see [Privacy Configuration Matrix](docs/reponomics/privacy-configuration-matrix.md). For repository access implications, see [Repository Access And Trust Boundary](docs/reponomics/trust-boundary.md). Common questions are answered in the [FAQ](docs/reponomics/faq.md).

## Managed Docs

Reponomics may update managed local documentation under `docs/reponomics/` before future collect runs. It writes only that namespace, commits with `[skip ci]`, and treats missing write permission as advisory. Set `allow_docs_sync: false` before editing `docs/reponomics/` yourself.

During setup, Reponomics saves the original setup README as `README.backup.md` before writing the shorter post-setup README. That backup is user-owned historical context; it is not managed by docs sync.
