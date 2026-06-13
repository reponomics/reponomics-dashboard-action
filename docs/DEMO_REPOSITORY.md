# Demo Repository

`reponomics-dashboard-demo` is a public generated showcase repository. It is not a development repository, not a user template, and not a third SemVer product. Its job is to give prospective users a concrete preview of the post-setup Reponomics experience: a public README dashboard, a GitHub Pages dashboard shell, artifact-backed retained data, and a data profile rich enough to show the dashboard's main workflows.

The demo is generated from this source repository. Maintainers should not hand-maintain the demo repository except for emergency recovery.

## Key Properties

- The demo repository is public.
- The README dashboard is committed to the demo repository.
- The Pages dashboard shell is committed under `docs/` and published with GitHub Pages Actions.
- The dashboard data is encrypted and stored as a `dashboard-data` Actions artifact in `reponomics-dashboard-demo`.
- The public demo key is shown in the Pages unlock UI so visitors can unlock the demo without reading separate instructions.
- The data is synthetic, curated, and date-shifted so the dashboard tells a useful product story without exposing live repository analytics.
- The generated demo output includes `.reponomics/demo-provenance.json`, which records source commit, template version, dataset revision, publication-tree digest, and retained-data seed evidence.

The useful product truth is that Reponomics dashboard data is artifact-backed, while README and Pages output are rendered surfaces. In the demo, the Pages shell and unlock affordance are public by design; the encrypted data remains separate from the committed repository tree.

## Design Boundary

The demo deliberately differs from ordinary generated user repositories in two ways:

- It commits a README dashboard in a public repository.
- It exposes a public unlock key in the Pages dashboard shell.

Those differences are demo-specific. They do not change the supported user template contract. The action runtime still rejects `generate-readme=true` in public repositories, and normal encrypted dashboards do not render a demo unlock panel. The demo builder calls the lower-level product renderers directly instead of calling the public action runtime's `publish` mode.

The maintenance rule is:

> Reuse the product renderer and canonical artifact formats, but keep demo-only publication behavior out of the public action workflow contract.

## Source Inputs

The demo is generated from:

- `dist/template`, produced by `make build-template`;
- `demo/dataset.yml`, the deterministic synthetic dataset source;
- `scripts/build_demo_repo.py`, which materializes canonical CSV data as an intermediate, renders showcase outputs, writes the encrypted seed artifact, prunes retained data from the publish tree, and writes demo provenance;
- `scripts/publish_demo_repo.py`, which validates and force-publishes the generated demo tree to `reponomics-dashboard-demo`;
- `dashboard_action/runtime/scripts/render_dashboard.py` and `render_readme.py`, the same renderers used by the product.

The dataset uses a relative 90-day window. By default, builds use the current UTC date as `as_of`; pass `--as-of YYYY-MM-DD` to `scripts/build_demo_repo.py` for reproducible local inspection.

## Generated Output

The generated demo publish tree contains:

- `README.md`, including a public synthetic-demo notice and rendered README dashboard;
- `docs/index.html`, the Pages dashboard shell with the public demo key panel;
- `docs/assets/`, including vendored dashboard assets needed by the shell;
- `.github/workflows/seed-and-publish-demo-dashboard.yml`, the demo-only target workflow;
- `.reponomics/demo-provenance.json`, the publication-tree and retained-data evidence.

The generated demo publish tree must not contain:

- `data/`;
- `dist/`;
- `.dashboard-data-artifact/`;
- real traffic data or customer/internal brand-risk terms.

`make verify-demo` and `make publish-demo-dry-run` enforce these shape constraints before publication.

## Publication Flow

Implementation sequence:

1. Build `dist/template` from the current source tree.
2. Copy `dist/template` into `dist/demo`.
3. Materialize synthetic canonical dashboard data under `dist/demo/data/` as an intermediate render input.
4. Produce `dist/demo-seed/dashboard-data.enc` using the same encrypted artifact format as the action runtime.
5. Generate `.github/workflows/seed-and-publish-demo-dashboard.yml` into the demo tree.
6. Render the public demo README and Pages dashboard shell from the source builder.
7. Prune retained data and build-only output from the demo repository tree.
8. Compute demo provenance over the pruned publication tree and record retained-data seed evidence separately.
9. Publish the generated demo repository tree to `reponomics-dashboard-demo` without `data/` or `dist/`.
10. Dispatch the generated demo-only target workflow, which imports the encrypted seed into `reponomics-dashboard-demo` Actions artifact storage and deploys the committed dashboard shell through GitHub Pages Actions.

The source publication workflow uploads two source artifacts:

- `generated-demo-repo`: the generated demo repository tree plus the source commit file;
- `generated-demo-dashboard-data`: the encrypted retained-data seed.

After the generated tree is force-pushed to `reponomics-dashboard-demo`, the target workflow downloads `generated-demo-dashboard-data` from `reponomics/reponomics-dashboard-action`, validates it, re-uploads it in the demo repository as `dashboard-data`, uploads the committed `docs/` shell as a Pages artifact, and deploys it.

The target artifact-import workflow uses `actions/download-artifact` with `github-token`, `repository`, and `run-id`. It passes the target workflow's `${{ github.token }}` as the explicit `github-token` input. This was validated against public source artifact run `27471925728` and target demo run `27472044670`: the target repo `GITHUB_TOKEN` could download the public source artifact, store it as `dashboard-data`, and deploy Pages.

If the source repo becomes private, artifact visibility changes, or GitHub tightens cross-repository artifact access, fall back to minting a narrowly scoped source-artifact GitHub App token in the target workflow. That cross-repository artifact path should remain demo-specific until it is designed as a user-facing import or recovery workflow.

## Public Demo Key

The Pages dashboard shell is public. The dashboard data remains encrypted. The demo key is displayed openly in the shell because visitors should be able to unlock the demo from the page itself.

The key is not public as a security tradeoff for synthetic data; it is public because this is a shareable demo. The data is synthetic for a separate reason: the demo needs a manicured, stable, non-sensitive portfolio that demonstrates the product surface well.

The demo key must never be reused for real dashboards.

The demo unlock panel is rendered only when `build_encrypted_html(..., demo_unlock=...)` receives demo metadata. Normal action-driven encrypted dashboards do not pass that metadata and do not render the panel.

## Local Commands

Build and verify the demo:

```sh
make build-demo
make verify-demo
```

Preview the generated files under `dist/demo/`. The Pages dashboard shell is at `dist/demo/docs/index.html`; for browser APIs that require HTTP, serve `dist/demo/` or `dist/demo/docs/` over a local web server.

The encrypted retained-data seed is written to `dist/demo-seed/dashboard-data.enc`. It is uploaded by the source publication workflow as `generated-demo-dashboard-data` and imported by the target demo workflow as `dashboard-data`.

Dry-run publication:

```sh
make publish-demo-dry-run
```

Publish:

```sh
make publish-demo
```

Publication refuses targets other than `reponomics/reponomics-dashboard-demo` unless the Make variables are intentionally overridden.

## GitHub Workflow

`.github/workflows/publish-demo.yml` is the source-repository publication workflow. It is manual-only for the current pass and split into two jobs:

- `build-demo-artifact` checks out the requested source ref, builds, verifies, dry-runs, packages `dist/demo` as a workflow artifact, and uploads `dist/demo-seed/dashboard-data.enc` as `generated-demo-dashboard-data`. This job has only `contents: read` and does not receive demo publication secrets.
- `publish-demo` downloads and validates the generated tree, then creates a demo publication app token scoped to `reponomics-dashboard-demo`, force-publishes the generated demo repository, and dispatches the generated target seed workflow with the source workflow run ID. After the token is minted, the job runs only a fixed shell publication sequence, not project Make targets or Python scripts.

The publication app should be a dedicated demo-only GitHub App installed only on `reponomics-dashboard-demo`. It needs `contents: write`, `workflows: write`, and `actions: write` on the demo repository so it can force-push the generated tree and dispatch the target seed workflow. Configure `vars.DEMO_PUBLISH_APP_CLIENT_ID` and `secrets.DEMO_PUBLISH_APP_PRIVATE_KEY` on the `demo-publication` environment.

The target demo repository must have GitHub Pages enabled with source set to GitHub Actions. The generated target workflow stores the encrypted seed artifact and deploys the Pages shell after the generated commit lands.

## Maintenance

The demo should be regenerated and republished when:

- a template release changes setup surface, docs, workflows, or first-run experience;
- an action release changes README rendering, Pages rendering, managed docs, setup behavior, or user-visible dashboard behavior;
- `demo/dataset.yml` changes;
- the relative synthetic 90-day window needs to roll forward.

The current daily-refresh cadence is not yet fully operationalized. Until it is, demo publication remains manual.

## Later Enhancement: Artifact History

The first artifact-backed implementation seeds only the current `dashboard-data` artifact. Do not engineer a multi-run backup-artifact simulation in this pass.

Because the demo will eventually refresh daily, previous target workflow runs will naturally accumulate. A later enhancement can generate a current 90-day packet and a previous 89-day or prior-day packet, then seed them through separate target workflow runs. That would make the demo Actions artifact history look more like a real dashboard repository with retained prior runs, and it may also inform a future repo-to-repo import workflow for template upgrades, compromise recovery, or dashboard repository migration.

## Guardrails

- Do not use real traffic data in `demo/dataset.yml`.
- Keep demo repository names under `reponomics-demo/demo-*` to avoid brand or search confusion.
- Keep retained canonical CSV data out of the published git tree.
- Keep demo unlock behavior out of `action.yml` and the public action input surface.
- Treat `.github/workflows/seed-and-publish-demo-dashboard.yml` as demo target infrastructure, not as a template workflow users should copy as setup guidance.
- If renderer APIs change, `make build-demo` and `make verify-demo` should fail before publication.
