# Upgrade Notes

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

The manifest at `docs/reponomics/.manifest.json` records the action version that last refreshed these managed docs.

If your workflow pins an exact action version such as `reponomics/reponomics-dashboard-action@v1.2.3`, you choose when to upgrade. If your workflow uses a floating major or minor ref such as `@v1`, a compatible Reponomics release can run in your repository without a workflow edit. Managed docs update records that the newer action ran and that current local guidance is available.

Use released action refs for generated dashboard repositories: floating major or minor release refs, exact release tags, or full commit SHAs for released action commits. Branch refs such as `@main` may run unreleased action behavior and are outside the generated template's compatibility guarantees.

When a new action version introduces optional features, the action may add or update documentation here. It will not change your `config.yaml` for you. Review the relevant docs, then opt into new configuration when you want the behavior.

If you want to keep local edits in `docs/reponomics/`, disable or delete `.github/workflows/update-docs.yml` before making those edits. When that workflow is enabled, Reponomics may regenerate this directory during action upgrades.

If docs update reports `permission_missing`, grant `contents: write` to the update-docs job or disable the update-docs workflow.
