# Testing

This guide is for day-to-day development testing in this source repository. The `Makefile` is the source of truth for exact command definitions. Release publication gates are documented in [VERSIONING_AND_RELEASE.md](./VERSIONING_AND_RELEASE.md), and workflow responsibilities are summarized in [../.github/workflows/README.md](../.github/workflows/README.md).

## Local Baseline

For ordinary code changes, start with:

```sh
make lint
make type-check
make validate
make test
```

Use `make ci` when you want the local equivalent of the normal aggregate CI path.

## Template Checks

Run template checks when a change affects generated workflows, template files, managed docs, action metadata used by generated workflows, or template publication assumptions:

```sh
make verify-template
make template-smoke
make template-consumer-e2e
```

`make verify-template` rebuilds `dist/template` before verifying it, so stale or ignored local output should not mask source changes.

## Bridge Checks

Bridge checks prove that the action and generated template still meet at the public boundary.

Run `make template-consumer-e2e` when runtime behavior should still work from a generated dashboard repository.

Run `make template-action-boundary-e2e` when changing `action.yml`, generated workflow `with:` blocks, action input names or defaults, wrapper inputs, or runtime environment loading.

Run `make template-compat-e2e` for release candidates and for changes that may affect copied template compatibility.

## Rendering And Demo Checks

Run scenario snapshots when dashboard rendering, layout, assets, or representative data behavior changes:

```sh
make dashboard-scenario-snapshots
```

Run demo checks when the public demo output, demo dataset, template setup surface, or visible dashboard behavior changes:

```sh
make verify-demo
make publish-demo-dry-run
```

## Test Isolation

Consumer-repository simulations should use temporary directories or temporary git repositories, not the source repository root. Tests that patch cwd, environment variables, runtime paths, module globals, or `sys.path` should restore them through fixtures such as `monkeypatch`.

Generated output should be produced by explicit Make targets such as `build-template`, `verify-template`, or `verify-demo`. Avoid tests that rely on execution order or shared generated state.

## Input Boundary Changes

When changing the action input schema, update and test the full boundary, not just `action.yml`. The current review aid for this lives in [VERSIONING_AND_RELEASE.md](./VERSIONING_AND_RELEASE.md#compatibility-policy).
