# Staging Smoke

> [!IMPORTANT]
> This is a maintainer-operated smoke check, not a release gate. It exercises one
> copied public dashboard repository before beta onboarding and must stay small.

The staging smoke path proves the copied-repository workflow that an external
maintainer is most likely to trust:

- a real copied repository can run the generated workflows;
- a low-scope `COLLECTION_TOKEN` can collect real but non-sensitive public
  GitHub data;
- encrypted retained data can be restored across workflow runs;
- GitHub Pages can serve the encrypted dashboard shell;
- the dashboard unlocks in a browser and renders the expected views.

Synthetic data remains appropriate for demos, fixtures, and UI snapshots.
Staging uses public repositories and real GitHub API responses so it exercises
authentication, rate limits, artifacts, generated workflows, Pages, and browser
behavior together.

## Scenario

| Setting | Value |
| --- | --- |
| Repository visibility | Public |
| Data mode | `encrypted` |
| Pages dashboard | Enabled |
| README dashboard | Disabled |
| Data source | Real, non-sensitive public GitHub API data |
| Collection credential | Dedicated low-scope `COLLECTION_TOKEN` |

## Local Dry Run

Prepare the copied staging tree and local evidence without touching GitHub:

```bash
make staging-smoke
```

This writes:

- `dist/staging-smoke/`, a generated copied-dashboard tree configured for the
  scenario;
- `dist/staging-smoke/.reponomics/staging-smoke.json`, machine-readable staging
  scenario metadata;
- `dist/staging-smoke-evidence.md`, the operator evidence checklist and follow-up
  commands.

The default target is `reponomics/reponomics-dashboard-staging` on `main`. The
script defaults to dry-run mode and will not push unless `--push` is passed.

## Publish To Staging

Before publishing, configure the staging repository out of band:

- repository visibility is public;
- Settings -> Pages -> Build and deployment -> Source is set to GitHub Actions;
- repository secret `COLLECTION_TOKEN` exists and can read the selected public
  repositories;
- repository secret `DASHBOARD_SECRET_DO_NOT_REPLACE` exists and is retained
  across runs.

Publish the configured copied tree:

```bash
STAGING_SMOKE_PUSH=--push make staging-smoke
```

The publish path replaces the target branch with the generated staging tree using
`--force-with-lease`, so stale legacy code in the staging repository is expected
to disappear. The remote safety check defaults to
`reponomics/reponomics-dashboard-staging`; override `STAGING_SMOKE_REMOTE` and
`STAGING_SMOKE_EXPECTED_REPO` only for an intentional staging target change.

Use explicit public repositories when the collection token is scoped narrowly:

```bash
STAGING_SMOKE_REPOSITORIES="reponomics/reponomics-dashboard-action" \
STAGING_SMOKE_PUBLISH_REPOSITORIES="reponomics/reponomics-dashboard-action" \
STAGING_SMOKE_PUSH=--push \
make staging-smoke
```

## Run The Smoke

After publication, run the generated workflows in the staging repository:

```bash
gh workflow run setup.yml --repo reponomics/reponomics-dashboard-staging --ref main
gh workflow run collect-and-publish.yml --repo reponomics/reponomics-dashboard-staging --ref main -f skip_collect=false
gh workflow run collect-and-publish.yml --repo reponomics/reponomics-dashboard-staging --ref main -f skip_collect=false
```

The second collection run is intentional: it checks that encrypted retained data
from the first run can be restored and extended.

Record the smoke as passing only after:

- Setup succeeds and writes `.reponomics/setup-complete`;
- both Collect and Publish runs succeed;
- the Pages deployment succeeds;
- the Pages dashboard unlocks in a browser with
  `DASHBOARD_SECRET_DO_NOT_REPLACE`;
- the expected dashboard navigation and repository views render.

Keep the workflow run URLs, Pages URL, published staging commit, and browser
notes in the generated evidence file or the release issue that requested the
smoke.
