# Demo Repository

`reponomics-dashboard-demo` is a public generated showcase repository. It is not a development repository and it is not the same product as the generated user template. Its purpose is to show prospective users what a Reponomics dashboard looks and feels like after setup, collection, and publication.

## Design Boundary

The demo intentionally uses synthetic public data. That lets it publish two surfaces that ordinary generated public user repositories do not enable by default:

- a README dashboard committed to the public repository;
- an encrypted GitHub Pages dashboard with a public demo key.

This does not change the supported user template contract. The action runtime still rejects `generate-readme=true` in public repositories, and generated user workflows still default to conservative settings. The demo builder renders README and Pages output directly through the lower-level renderer modules instead of calling the public action runtime's `publish` mode.

The maintenance rule is:

> Reuse the product renderer and canonical artifact formats, but do not teach the public action workflow contract that synthetic public demo output is an ordinary user mode.

## Source Inputs

The demo is generated from:

- `dist/template`, produced by `make build-template`;
- `demo/dataset.yml`, the deterministic synthetic dataset source;
- `scripts/build_demo_repo.py`, which materializes canonical CSV data as an intermediate, renders showcase outputs, and writes the encrypted seed artifact;
- `dashboard_action/runtime/scripts/render_dashboard.py` and `render_readme.py`, the real product renderers.

The dataset uses a relative 90-day window. By default, builds use the current UTC date as `as_of`; pass `--as-of YYYY-MM-DD` to `scripts/build_demo_repo.py` for reproducible local inspection.

## Artifact-Backed Publication

The demo publication shape keeps synthetic retained data out of public git history while still showing the same storage model that real dashboard repositories use.

Public state:

- `README.md` is committed and public.
- `docs/index.html` is an encrypted GitHub Pages dashboard with the public demo key panel.
- Retained synthetic dashboard data is stored as a `dashboard-data` Actions artifact in `reponomics-dashboard-demo`, not committed under `data/`.
- `dist/` is not committed to the demo repository.

The source repository still generates the README and Pages dashboard because the real action intentionally refuses `generate-readme=true` in public repositories and does not expose a public demo-unlock input. These are showcase artifacts, not changes to the supported user template contract.

Implementation sequence:

1. Build synthetic canonical data in the source repository as an intermediate render input.
2. Render and commit the public demo README from the source builder.
3. Produce an encrypted `dashboard-data` seed artifact using the same encrypted artifact format as the action runtime.
4. Publish the demo repository tree without `data/` or `dist/`.
5. Include a generated demo-only target workflow, `.github/workflows/seed-and-publish-demo-dashboard.yml`, that imports the encrypted seed artifact into `reponomics-dashboard-demo` Actions artifact storage.
6. Deploy the committed `docs/` dashboard through GitHub Pages Actions in that same demo-only workflow.
7. Compute demo provenance over the final published tree and record retained-data seed evidence separately.

This avoids the misleading impression that users should commit retained traffic CSVs. It also keeps the useful product truth visible: Reponomics dashboard data is artifact-backed, while the public README and Pages dashboard are rendered outputs.

The target artifact-import workflow uses `actions/download-artifact` with `github-token`, `repository`, and `run-id` to download a source artifact from `reponomics/reponomics-dashboard-action`, then re-uploads the payload as `dashboard-data` in `reponomics-dashboard-demo`. That cross-repository artifact path should remain demo-specific until it is designed as a user-facing import or recovery workflow.

The target repository needs a secret named `REPONOMICS_SOURCE_ARTIFACT_TOKEN` with read access to Actions artifacts in `reponomics/reponomics-dashboard-action`. The demo publication GitHub App also needs `contents: write`, `workflows: write`, and `actions: write` on `reponomics-dashboard-demo` so it can force-push the generated tree and dispatch the target seed workflow.

### Later Enhancement: Previous Artifact Illusion

The first artifact-backed pass should seed only the current `dashboard-data` artifact. Do not engineer a multi-run backup-artifact illusion in the first correction.

Because the demo will eventually refresh daily to roll the 90-day window forward, previous artifacts will naturally accumulate. A later enhancement can generate a current 90-day packet and a previous 89-day or prior-day packet, then seed them through separate target workflow runs. That would make the demo Actions artifact history look more like a real dashboard repository with retained prior runs, and it may also inform a future repo-to-repo import workflow for template upgrades, compromise recovery, or dashboard repository migration.

## Public Demo Key

The Pages dashboard remains encrypted, but the demo key is intentionally public because the data is synthetic. The encrypted unlock shell has an optional demo panel that displays the key and unlocks through the same client-side decrypt path as a normal dashboard.

This panel is only rendered when `build_encrypted_html(..., demo_unlock=...)` receives demo metadata. Normal action-driven encrypted dashboards do not pass that metadata and do not render the demo panel.

## Local Commands

Build and verify the demo:

```sh
make build-demo
make verify-demo
```

Preview the generated files under `dist/demo/`. The Pages dashboard is at `dist/demo/docs/index.html`; for browser APIs that require HTTP, serve `dist/demo/docs/` over a local web server.

The encrypted retained-data seed is written to `dist/demo-seed/dashboard-data.enc`. It is uploaded by the source publication workflow as `generated-demo-dashboard-data` and imported by the target demo workflow as `dashboard-data`.

Dry-run publication:

```sh
make publish-demo-dry-run
```

Publish:

```sh
make publish-demo
```

Publication refuses targets other than `reponomics/reponomics-dashboard-demo` unless the Make variables are intentionally overridden. The generated demo repository includes `.github/workflows/seed-and-publish-demo-dashboard.yml`, which imports the encrypted seed artifact, stores it as `dashboard-data`, and deploys the committed `docs/` dashboard through GitHub Pages Actions in the target repository.

## GitHub Workflow

`.github/workflows/publish-demo.yml` is the source-repository publication workflow. It is manual-only for the initial pass and split into two jobs:

- `build-demo-artifact` checks out the requested source ref, builds, verifies, dry-runs, packages `dist/demo` as a workflow artifact, and uploads `dist/demo-seed/dashboard-data.enc` as `generated-demo-dashboard-data`. This job has only `contents: read` and does not receive demo publication secrets.
- `publish-demo` downloads and validates the generated tree, then creates a demo publication app token scoped to `reponomics-dashboard-demo`, force-publishes the generated demo repository, and dispatches the generated target seed workflow with the source workflow run ID. After the token is minted, the job runs only a fixed shell publication sequence, not project Make targets or Python scripts.

The publication app should be a dedicated demo-only GitHub App installed only on `reponomics-dashboard-demo`. Configure `vars.DEMO_PUBLISH_APP_CLIENT_ID` and `secrets.DEMO_PUBLISH_APP_PRIVATE_KEY` on the `demo-publication` environment, and protect that environment with required reviewers.

The target demo repository must have GitHub Pages enabled with source set to GitHub Actions. The generated target workflow stores the encrypted seed artifact and deploys Pages after the generated commit lands.

## Risks And Guardrails

- The demo key is public by design. It must never be reused for real dashboards.
- The demo publishes synthetic README and Pages output to public git history. Do not use real traffic data in `demo/dataset.yml`.
- The canonical synthetic CSV data must remain out of the published git tree. `make verify-demo` and `make publish-demo-dry-run` reject generated demo output that contains `data/`, `dist/`, or `.dashboard-data-artifact/`.
- The demo builder bypasses the public action runtime validation layer, so tests must prove this path does not relax generated user workflows or `action.yml`.
- The generated demo repository contains a special seed-and-Pages workflow. It is target-demo infrastructure, not a template workflow users should copy as setup guidance.
- Demo publication requires `permission-workflows: write` because the generated demo repo includes `.github/workflows/seed-and-publish-demo-dashboard.yml`, and `permission-actions: write` because the source workflow dispatches that target workflow. Remove those permissions if the target workflow becomes fixed infrastructure in the demo repo.
- If renderer APIs change, `make build-demo` and `make verify-demo` should fail before publication.
