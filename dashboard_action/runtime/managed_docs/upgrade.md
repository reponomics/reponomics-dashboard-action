# Upgrade Notes

> [!NOTE]
> These docs describe the official Reponomics generated workflows for the `v0` external beta. Repository owners can modify their copies; modified workflows may behave differently from what these docs describe.

The manifest at `docs/reponomics/.manifest.json` records the action version that last refreshed these managed docs.

During the external beta, generated dashboard repositories use the `v0` action line. If your workflow pins an exact action version such as `reponomics/reponomics-dashboard-action@v0.31.0`, you choose when to upgrade. If your workflow uses a floating major or minor ref such as `@v0`, a compatible beta release can run in your repository without a workflow edit. Managed docs update records that the newer action ran and that current local guidance is available.

Future `v1` examples describe the stable public release model, not the current beta setup target.

Use released action refs for generated dashboard repositories: floating major or minor release refs, exact release tags, or full commit SHAs for released action commits. Branch refs such as `@main` may run unreleased action behavior and are outside the generated template's compatibility guarantees.

The default generated wrapper keeps the Reponomics action reference in one place: `.github/actions/reponomics/action.yml`. If your organization requires full-SHA-pinned actions, update that nested `uses:` line after resolving the intended release tag to a commit SHA. That is an owner choice: SHA-pinned repositories own manual upgrades, while floating `v0` repositories receive compatible fixes the next time the workflow runs.

When a new action version introduces optional features, the action may add or update documentation here. It will not change your `config.yaml` for you. Review the relevant docs, then opt into new configuration when you want the behavior.

If you want to keep local edits in `docs/reponomics/`, disable or delete `.github/workflows/update-docs.yml` before making those edits. When that workflow is enabled, Reponomics may regenerate this directory during action upgrades.

If docs update reports `permission_missing`, grant `contents: write` to the update-docs job or disable the update-docs workflow.
