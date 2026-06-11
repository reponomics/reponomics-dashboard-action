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
