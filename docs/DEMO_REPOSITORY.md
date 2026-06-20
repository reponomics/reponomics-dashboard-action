# Demo Repository

`reponomics-dashboard-demo` is a public generated showcase repository. It is not a development repository, not a user template, and not a third SemVer product. Its job is to give prospective users a concrete preview of the post-setup Reponomics experience: a GitHub Pages dashboard, artifact-backed retained data, and a data profile rich enough to show the dashboard's main workflows.

The demo is generated from this source repository. Maintainers should not hand-maintain the demo repository except for emergency recovery.

## Key Properties

- The demo repository is public.
- The README is committed to the demo repository as static explanatory text.
- The Pages dashboard is generated and published by GitHub Pages Actions.
- The dashboard data is encrypted and stored as a `dashboard-data` Actions artifact in `reponomics-dashboard-demo`.
- The public demo key is shown in the Pages unlock UI so visitors can unlock the demo without reading separate instructions.
- The data is synthetic, curated, and date-shifted so the dashboard tells a useful product story without exposing live repository analytics.
- The generated demo output includes `.reponomics/demo-provenance.json`, which records source commit, template version, dataset revision, publication-tree digest, and retained-data seed evidence.

The useful product truth is that Reponomics dashboard data is artifact-backed, while Pages output is a rendered surface. In the demo, the public key is embedded in the demo-only target workflow; the encrypted data and rendered Pages shell remain separate from the committed repository tree.

## Design Boundary

When maintaining or updating the demo repository, try to localize the deviations to the smallest possible surface area - always prefer to leverage real dashboard tooling instead of bespoke demo-specific logic. Any significant deviations should be explicitly foregrounded so as not to mislead the public. Avoid modifying anything that touches the critical path for the real dashboard product.

The maintenance rule is:

> Reuse the product renderer and canonical artifact formats, but keep demo-only publication behavior out of the public action workflow contract.

## Source Inputs

The demo is generated from:

- `dist/template`, produced by `make build-template`;
- `demo/dataset.yml`, the deterministic synthetic dataset source;
- `scripts/build_demo_repo.py`, which materializes canonical CSV data as an intermediate, writes the encrypted seed artifact, writes the configured demo repository tree, prunes retained data from the publish tree, and writes demo provenance;
- `scripts/publish_demo_repo.py`, which validates and force-publishes the generated demo tree to `reponomics-dashboard-demo`;
- the generated local action wrapper, which invokes the product runtime during the target seed-and-publish workflow.

The dataset uses a relative 90-day window. By default, builds use the current UTC date as `as_of`; pass `--as-of YYYY-MM-DD` to `scripts/build_demo_repo.py` for reproducible local inspection.

## Generated Output

The generated demo publish tree contains:

- `README.md`, including a public synthetic-demo notice;
- `config.yaml`, preconfigured for encrypted Pages publication;
- `.github/workflows/seed-and-publish-demo-dashboard.yml`, the demo-only target workflow;
- `.reponomics/demo-provenance.json`, the publication-tree and retained-data evidence.

The generated demo publish tree must not contain:

- `data/`;
- `dist/`;
- `docs/index.html`;
- `docs/assets/`;
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
6. Write a setup-ready demo `config.yaml` and public synthetic-demo README notice.
7. Prune retained data, rendered Pages output, and build-only output from the demo repository tree.
8. Compute demo provenance over the pruned publication tree and record retained-data seed evidence separately.
9. Publish the generated demo repository tree to `reponomics-dashboard-demo` without `data/` or `dist/`.
10. Dispatch the generated demo-only target workflow, which imports the encrypted seed into `reponomics-dashboard-demo` Actions artifact storage and runs the normal publish path to generate and deploy the Pages dashboard through GitHub Pages Actions.

The source publication workflow uploads two source artifacts:

- `generated-demo-repo`: the generated demo repository tree plus the source commit file;
- `generated-demo-dashboard-data`: the encrypted retained-data seed.

The target artifact-import workflow uses `actions/download-artifact` with `github-token`, `repository`, and `run-id`. It passes the target workflow's `${{ github.token }}` as the explicit `github-token` input. After storing the downloaded seed as `dashboard-data`, it calls the generated local Reponomics action wrapper in `publish` mode with `artifact-run-id: ${{ github.run_id }}` so the dashboard shell and runtime assets are generated during the workflow and uploaded as the Pages artifact.

## Public Demo Key

The Pages dashboard shell is public. The dashboard data remains encrypted. The demo key is included openly in the demo workflow because visitors should be able to unlock the demo from the page itself.

The generated demo workflow passes the public demo key as the dashboard secret. Normal user dashboards use repository secrets instead.

## Local Commands

Build and verify the demo:

```sh
make verify-demo
```

Preview the generated repository files under `dist/demo/`. The Pages dashboard shell is not committed there; it is generated by the target seed-and-publish workflow.

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

`.github/workflows/publish-demo.yml` is the demo repo publication workflow. It supports manual publication and scheduled daily refresh, and it is split into two jobs:

- `build-demo-artifact` resolves the allowed source ref, checks it out, builds, verifies, dry-runs, packages `dist/demo` as a workflow artifact, and uploads `dist/demo-seed/dashboard-data.enc` as `generated-demo-dashboard-data`. This job has only `contents: read` and does not receive demo publication secrets.
- `publish-demo` downloads and validates the generated tree, then creates a demo publication app token scoped to `reponomics-dashboard-demo`, force-publishes the generated demo repository, and dispatches the generated target seed workflow with the source workflow run ID. After the token is minted, the job runs only a fixed shell publication sequence, not project Make targets or Python scripts.

Manual publication and scheduled daily refresh use the same demo-only publication app. The scheduled source ref defaults to `main`; set `vars.DEMO_DAILY_SOURCE_REF` to `demo-stable` or an allowed release tag if the demo should follow a promoted ref instead of main.

The publication app is a dedicated demo-only GitHub App installed only on `reponomics-dashboard-demo`. It needs `contents: write`, `workflows: write`, and `actions: write` on the demo repository so it can force-push the generated tree and dispatch the target seed workflow. Configure `vars.DEMO_PUBLISH_APP_CLIENT_ID` and `secrets.DEMO_PUBLISH_APP_PRIVATE_KEY` at repository or organization scope in this source repository.

## Future Enhancement: Artifact History

A future enhancement can generate a current 90-day packet and a previous 89-day or prior-day packet, then seed them through separate target workflow runs. That would make the demo Actions artifact history look more like a real dashboard repository with retained prior runs.

## Guardrails

- Do not use real traffic data in `demo/dataset.yml`.
- Keep demo repository names under `reponomics-demo/demo-*` to avoid brand or search confusion.
- Keep retained canonical CSV data out of the published git tree.
- Keep demo unlock behavior out of `action.yml` and the public action input surface.
- If renderer APIs change, `make verify-demo` should fail before publication.
