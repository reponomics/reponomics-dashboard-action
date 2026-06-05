# Reponomics Dashboard

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

This is a backup copy of the setup README for your Reponomics dashboard repository. The repository root `README.md` may be replaced by setup or by generated metrics README output in private repositories.

The dashboard collects GitHub traffic and growth data, stores retained state in GitHub Actions artifacts, and renders optional dashboard outputs through GitHub Actions. The repository stays intentionally thin: collection, encryption, rendering, key rotation, incident reset behavior, CSV export, and managed docs sync are owned by the versioned action:

```yaml
uses: reponomics/reponomics-dashboard-action@v{{ACTION_VERSION}}
```

## Get Started

1. Review `config.yaml` and decide which repositories this dashboard should track.
2. Create a collection credential and store it as the repository secret `COLLECTION_TOKEN`. Most single-owner dashboards should use a fine-grained personal access token with repository `Administration: read`.
3. Choose a privacy mode: `strong`, `casual`, or `plain`. Public repositories should normally use `strong`.
4. For `strong` or `casual`, generate and save `DASHBOARD_SECRET_DO_NOT_REPLACE`, then add it as a repository secret. See [Secure Dashboard Key Generation](secure-dashboard-key.md).
5. Run **Actions -> Set up Reponomics dashboard -> Run workflow**.
6. If setup enables hosted dashboard publication, open **Settings -> Pages** and set **Build and deployment -> Source** to **GitHub Actions**.

Setup enables the collection workflow, the manual incident reset workflow, and the scheduled workflow keepalive. It does not collect traffic immediately. Collection runs on the configured schedule and stores retained data in the `dashboard-data` Actions artifact.

## Configuration

`config.yaml` is owned by this repository. Reponomics reads it during workflow runs but does not silently rewrite it.

```yaml
max_repos: 50

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

If `include_only` is non-empty, Reponomics tracks exactly those repositories and ignores the automatic pool. For more detail, see [Dashboard repository documentation](repository-guide.md).

### Token Scope And Repository Owners

Repository entries use full `owner/repo` names because a dashboard can be configured against repositories owned by users or organizations. The token you choose still controls which owners can actually be collected.

Fine-grained personal access tokens are scoped to one GitHub resource owner. If your dashboard only tracks repositories under one user or one organization, a fine-grained token with repository `Administration: read` is the preferred path.

This template currently supports one collection credential. If one dashboard needs to track repositories under multiple users or organizations, the fine-grained token flow is not the right fit for the current single-token setup. Use a classic PAT with `repo` scope where the relevant organizations allow it. Classic PATs are broader and can access repositories your GitHub account can access, so use this fallback only when the dashboard really needs to span owners.

## Privacy And Output

The canonical store is the `dashboard-data` Actions artifact.

- `strong` and `casual` store encrypted retained data.
- `plain` stores retained CSV files directly in the artifact and is rejected in public repositories.
- Hosted dashboard publication is optional and requires GitHub Pages to use GitHub Actions as the deployment source.
- Metric README dashboard generation is only available in private repositories.

For the full mode comparison, see [Privacy Configuration Matrix](privacy-configuration-matrix.md). For repository access implications, see [Repository Access And Trust Boundary](trust-boundary.md). Common questions are answered in the [FAQ](faq.md).

## Managed Docs

Reponomics may update managed local documentation under `docs/reponomics/` before future collect runs. It writes only that namespace, commits with `[skip ci]`, and treats missing write permission as advisory. Set `allow_docs_sync: false` before editing `docs/reponomics/` yourself.

User-owned files outside `docs/reponomics/`, including the repository root `README.md`, are not managed by docs sync.
