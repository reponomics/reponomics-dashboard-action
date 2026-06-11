# Initial Goal

Get to one source repo, reponomics-dashboard-action, that can:

- build the dashboard template from local source
- run the existing template smoke/consumer tests locally
- publish dist/template to reponomics-dashboard
- stop depending on reponomics-dashboard-dev for action-release sync

Do not try to perfect two-product release automation in the first pass. The first win is removing the cross-repo handoff.

USER COMMENT:
- Don't worry about documentation in this pass, we don't know what the staleness of any of the documentation is right now, the only important documents migration-wise are the managed docs (the docs that ship with the template).
- Prefer working prototype/skeleton with failing tests - we can seam the tests together after we have a have a proof-of-concept that this is the better structureoverall. We don't want regressions but if resources are stretched, prefer proving functionality first, tests after.
- Be patient when interacting with the GitHub API.
- Document your design choices, decisions, road blocks as you go. You can simply append to the bottom of this doc.
- Prefer more frequent commits (after each "milestone", e.g.) - iterative progress, not one major haul.

# Milestones

1. Copy the template machinery into the action repo
Bring over template/, template-manifest.yml, template-action-release.yml if still useful short-term, and the template build/publish/smoke/e2e scripts. Put them somewhere boring first; same paths are fine.

2. Make the action repo build the template
Add Make targets like build-template, verify-template, template-smoke, template-consumer-e2e. It is fine if they initially duplicate dashboard-dev assumptions.

3. Move template tests

Bring over tests/test_generated_repos.py and tests/test_template_setup_acceptance.py, then adapt imports/paths. Don’t over-refactor into ideal test layout yet.

4. Collapse managed-docs flow

The action repo already owns dashboard_action/runtime/managed_docs/. Long term, template/docs/reponomics/ should be rendered from that bundle during template build, not maintained as a second copied snapshot. For the rough transfer, copying the current snapshot is acceptable, but mark it as temporary.

5. Replace cross-repo release sync with local checks

Remove the need for scripts/sync_action_release.py to fetch a released action from GitHub just so the template can accept it. In the co-located repo, the template should validate against the local action.yml and local managed docs bundle before release.

6. Publish generated template from action repo

Move the dev-template-release.yml idea into the action repo. It should build dist/template and push to reponomics-dashboard with the same expected-repo guard and force-with-lease behavior.

7. Archive dashboard-dev

Once the action repo can generate and publish the template, stop using dashboard-dev. Add an archival README pointing to reponomics-dashboard-action.

## Dashboard-Dev Inventory

Keep / move:

template/: move into action repo. This is the important source for the generated dashboard repo.
template-manifest.yml: move. Still useful as the explicit shipped-file contract.
scripts/build_template.py: move, probably with only path fixes.
scripts/publish_generated_repo.py: move.
scripts/smoke_template_release.py: move.
scripts/template_consumer_e2e.py: move, then simplify because the action runtime is now local by default.
scripts/verify_workflow_classification.py: move if still useful, but it may become less important once there are no dev/template workflow directories in separate repos.
tests/test_generated_repos.py: move.
tests/test_template_setup_acceptance.py: move.
pieces of .github/workflows/dev-template-release.yml: merge into action repo release/publish workflow.

Modify / merge cautiously:

scripts/sync_action_release.py: do not move as-is as a permanent mechanism. Its job was cross-repo release acceptance. Salvage only useful validation ideas: action metadata contract, stale ref checks, managed-doc snapshot verification.
template-action-release.yml: keep temporarily if it helps preserve tests, but long term replace it with local product metadata: template version, default action ref, compatible action range/contract.
docs/architecture/* and docs/adr/*: cherry-pick only still-current docs into the action repo docs. Most can be archived rather than migrated wholesale.
.github/workflows/dev-ci.yml: merge ideas into action CI, not the file as-is.
dependency lock files / Makefile targets: merge only what the moved scripts need. Prefer one Python env and one Makefile in the action repo.

Remove / do not migrate:

dist/: generated output.
.mypy_cache, .pytest_cache, .ruff_cache, venv: local caches.
__INTERNAL__: unless there is a specific useful note, leave behind.
dashboard-dev top-level CODE_OF_CONDUCT, CONTRIBUTING, SECURITY, LICENSE, README as source repo identity files. The action repo already has these.
dashboard-dev hygiene workflows: Scorecard, OSV, semantic PR, dependabot, release-please. The action repo already has equivalents; merge only missing policy.
Important Simplification

After transfer, stop thinking “dashboard-dev accepts an action release.” Instead:
action release and template release are two products from one source tree
template compatibility is tested before either product is published
generated reponomics-dashboard is just the polished template artifact

For the first migration, I would tolerate duplicated docs snapshots, rough paths, and temporarily awkward version files. The criterion is: can the action repo alone regenerate the current template and run the old dashboard-dev gates? Once yes, the tighter two-product release design will be much easier to reason about.

---

Architecture sketch:

```sh
reponomics-dashboard-action/
  action.yml
  dashboard_action/
  template/
  scripts/build_template.py
  scripts/publish_generated_repo.py
  tests/
```

...publishes:

```sh
reponomics-dashboard-action@v0.22.1
reponomics-dashboard@v0.9.1
```

---

## Migration Log

### 2026-06-11 Initial Transfer

- Copied the dashboard template source into this repository at `template/`.
- Copied the template generator and release harness scripts into `scripts/`:
  - `build_template.py`
  - `publish_generated_repo.py`
  - `smoke_template_release.py`
  - `template_consumer_e2e.py`
  - `verify_workflow_classification.py`
  - `sync_action_release.py` temporarily, as a compatibility/helper module for transferred tests.
- Copied the template manifest files:
  - `template-manifest.yml`
  - `template-action-release.yml`
- Copied the generated-template tests:
  - `tests/test_generated_repos.py`
  - `tests/test_template_setup_acceptance.py`
- Added action-repo Make targets for the old dashboard-dev gates:
  - `build-template`
  - `verify-template`
  - `verify-workflow-classification`
  - `template-smoke`
  - `template-consumer-e2e`
  - `publish-template-dry-run`
  - `publish-template`
- Changed `scripts/template_consumer_e2e.py` so the default action runtime is the current repository, not a sibling checkout.
- Added `.github/workflows/publish-template.yml` so the action repo can publish the generated template to `reponomics-dashboard`.
- Removed the `reponomics-dashboard-dev` repository-dispatch handoff from `.github/workflows/release-please.yml`.

### Design Choices

- This pass prefers copy-over-cleanup. `reponomics-dashboard-dev` was not modified.
- The copied files are intentionally left in their old, boring paths for now. That keeps the proof-of-concept focused on co-location instead of layout design.
- `sync_action_release.py` remains as a temporary compatibility layer. It is no longer wired as a cross-repo release flow, but some moved tests still exercise its useful validation helpers.
- `template/docs/reponomics/` is still a copied snapshot. The next cleanup should render this snapshot from `dashboard_action/runtime/managed_docs/` during template build.
- File-level `ruff: noqa: ISC002` was added to transferred files that use dashboard-dev's implicit multiline string style. This is a rough-migration concession, not the desired final style.

### Verified Gates

- `make build-template`
- `make verify-template`
- `make verify-workflow-classification`
- `make template-smoke`
- `make template-consumer-e2e`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 venv/bin/python -m pytest tests/test_generated_repos.py tests/test_template_setup_acceptance.py -v`
- `make test`
- `make lint`
- `make type-check`
- `make validate-workflows`
- `make validate-action-pins`

### Remaining Rough Edges

- Replace `template-action-release.yml` with first-class local template/action compatibility metadata.
- Replace `sync_action_release.py` with a local template contract checker that validates against the current source tree instead of released GitHub state.
- Generate `template/docs/reponomics/` from the local managed-docs bundle during `build-template`.
- Decide how the two product release versions are represented in Release Please and GitHub Releases.
- Tighten CI so template gates run in the action repo at the right cost level.
- Decide whether local `publish-template-dry-run` should require a preconfigured `reponomics-dashboard` remote or accept a full remote URL.

### 2026-06-11 Local Template Contract

- Replaced the temporary `template-action-release.yml` acceptance file with
  `template-contract.yml`.
- Removed `scripts/sync_action_release.py`; its useful local checks now live in
  `scripts/template_contract.py`.
- Stopped maintaining `template/docs/reponomics/` as a checked-in source
  snapshot. `scripts/build_template.py` now writes the generated
  `docs/reponomics/` tree from `dashboard_action/runtime/managed_docs/`.
- Kept the product boundary explicit: the template contract owns
  `template_version`, default compatible action ref, and minimum action version;
  the action version remains owned by the action package/runtime metadata.

### Updated Rough Edges

- Decide how the two product release versions are represented in Release Please
  and GitHub Releases.
- Add compatibility fixtures for older template contracts once there are
  published template releases to support.
- Tighten CI so template gates run in the action repo at the right cost level.
- Decide whether local `publish-template-dry-run` should require a preconfigured
  `reponomics-dashboard` remote or accept a full remote URL.

### Current State After Contract Cleanup

The action repository now contains the development source for two related but
separately versioned products:

- Action product: `action.yml`, `dashboard_action/`, runtime managed-docs
  bundle, action CI, and action release metadata. Its version remains the action
  runtime/package version.
- Template product: `template/`, `template-manifest.yml`,
  `template-contract.yml`, template build/publish scripts, and template tests.
  Its version is `template-contract.yml`'s `template_version`.

`scripts/build_template.py` copies the template source tree into `dist/template`
and then overlays `docs/reponomics/` from
`dashboard_action/runtime/managed_docs/`. The checked-in template source no
longer contains a second managed-docs snapshot. Generated template repositories
still receive `docs/reponomics/` and its manifest.

The old cross-repo acceptance mechanism is gone from this source tree:

- `template-action-release.yml` was removed.
- `scripts/sync_action_release.py` was removed.
- `scripts/template_contract.py` now validates the local template/action
  contract, action metadata required by template workflows, generated
  managed-docs snapshots, and stale executable action references in the
  generated template surface.

The intended compatibility model is asymmetric:

- Once users copy the generated template, assume that template is durable and
  may not be regenerated in place.
- The action is the ongoing distribution channel for runtime fixes,
  enhancements, and managed-doc updates.
- Therefore, future action releases must remain compatible with previously
  published template contracts within their declared compatible action major.
- Future template releases may depend on newer action capabilities, but old
  templates must not depend on future template regeneration.

The current implementation preserves that separation, but it is still the first
co-located shape. The next release-design work should add fixtures for old
template contracts before there are public users, so action compatibility can be
tested against concrete historical template surfaces rather than only the
current generated template.

### 2026-06-11 Release Metadata Split

- `.github/.release-please-manifest.json` now has two entries:
  - `.` for the Marketplace action version.
  - `template` for the generated template product version.
- `.github/release-please-config.json` keeps the action package on bare `v*`
  tags so `reponomics/reponomics-dashboard-action@v0` remains the action update
  channel.
- The template package uses component-prefixed release tags,
  `reponomics-dashboard-v*`, to avoid competing with action tags in the shared
  source repository.
- Release Please updates `template-contract.yml`'s `template_version` for
  template releases. It does not update the action runtime version for template
  releases, and it does not update the template version for action releases.
- `.github/workflows/publish-template.yml` now ignores ordinary action releases
  and publishes `reponomics-dashboard` only for manual dispatch or
  `reponomics-dashboard-v*` template releases.

This is intentionally a first release split, not the final compatibility
program. The known weak point is path attribution: the template component is
keyed to `template/`, while some template-affecting source still lives in
top-level scripts and `template-contract.yml`. Before public release, either
tighten the Release Please path model or document the release-operator rule that
template-affecting non-`template/` changes need an explicit template release
commit.
