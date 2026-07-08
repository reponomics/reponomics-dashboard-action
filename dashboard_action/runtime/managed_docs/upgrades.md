# Upgrades

The manifest at `docs/reponomics/.manifest.json` records the action version that last refreshed these managed docs.

## Action Refs

During the pre-wide-release beta, generated dashboard repositories use the `v0` action line. If your workflow pins an exact action version such as `reponomics/reponomics-dashboard-action@v0.31.0`, you choose when to upgrade. If your workflow uses a floating major or minor ref such as `@v0`, a compatible beta release can run in your repository without a workflow edit.

Use released action refs for generated dashboard repositories: floating major or minor release refs, exact release tags, or full commit SHAs for released action commits. Branch refs such as `@main` may run unreleased action behavior and are outside the generated template's compatibility guarantees.

## Local Wrapper

The default generated wrapper keeps the Reponomics action reference in one place: `.github/actions/reponomics/action.yml`.

If your organization requires full-SHA-pinned actions, update that nested `uses:` line after resolving the intended release tag to a commit SHA. SHA-pinned repositories own manual upgrades, while floating `v0` repositories receive compatible fixes the next time the workflow runs.

## Managed Docs During Upgrades

When a new action version introduces optional features, the action may add or update documentation here. It will not change your `config.yaml` for you. Review the relevant docs, then opt into new configuration when you want the behavior.

If you choose to own local edits in `docs/reponomics/`, disable or delete `.github/workflows/update-docs.yml` before making those edits. When that workflow is enabled, Reponomics may regenerate this directory during action upgrades.

If docs update reports `permission_missing`, grant `contents: write` to the update-docs job or disable the update-docs workflow.

## Continue

- [Managed documentation](managed-docs.md)
- [Provenance and verification](provenance.md)
