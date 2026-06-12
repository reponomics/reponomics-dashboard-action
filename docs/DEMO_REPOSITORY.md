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
- `scripts/build_demo_repo.py`, which materializes canonical CSV data and renders outputs;
- `dashboard_action/runtime/scripts/render_dashboard.py` and `render_readme.py`, the real product renderers.

The dataset uses a relative 90-day window. By default, builds use the current UTC date as `as_of`; pass `--as-of YYYY-MM-DD` to `scripts/build_demo_repo.py` for reproducible local inspection.

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

Dry-run publication:

```sh
make publish-demo-dry-run
```

Publish:

```sh
make publish-demo
```

Publication refuses targets other than `reponomics/reponomics-dashboard-demo` unless the Make variables are intentionally overridden. The generated demo repository includes `.github/workflows/publish-demo-dashboard.yml`, which deploys the committed `docs/` dashboard through GitHub Pages Actions in the target repository.

## GitHub Workflow

`.github/workflows/publish-demo.yml` is the source-repository publication workflow. It is manual-only for the initial pass. It builds, verifies, dry-runs, creates a release app token scoped to `reponomics-dashboard-demo`, and force-publishes the generated demo repository.

The target demo repository must have GitHub Pages enabled with source set to GitHub Actions. The generated target workflow uploads `docs/` and deploys Pages after the generated commit lands.

## Risks And Guardrails

- The demo key is public by design. It must never be reused for real dashboards.
- The demo publishes synthetic metrics to public git history. Do not use real traffic data in `demo/dataset.yml`.
- The demo builder bypasses the public action runtime validation layer, so tests must prove this path does not relax generated user workflows or `action.yml`.
- The generated demo repository contains a special Pages deployment workflow. It is target-demo infrastructure, not a template workflow users should copy as setup guidance.
- If renderer APIs change, `make build-demo` and `make verify-demo` should fail before publication.
