# Upgrade Notes

This dashboard last received managed docs from Reponomics Dashboard Action {{ACTION_VERSION}} with docs bundle {{DOCS_BUNDLE_VERSION}}.

If your workflow pins an exact action version such as `reponomics/reponomics-dashboard-action@v1.2.3`, you choose when to upgrade. If your workflow uses a floating major or minor ref such as `@v1`, a compatible Reponomics release can run in your repository without a workflow edit. Managed docs sync is the local receipt that the newer action ran and that current local guidance is available.

When a new action version introduces optional features, the action may add or update documentation here. It will not change your `config.yaml` for you. Review the relevant docs, then opt into new configuration when you want the behavior.

If docs sync reports `user_modified_conflict`, at least one managed file changed after Reponomics generated it. Keep your edits by disabling managed docs sync, or restore the generated file and rerun the workflow.

If docs sync reports `permission_missing`, grant `contents: write` to the docs sync job or disable managed docs sync. Top-level workflow permissions should remain minimal; grant write permission only to the job that needs to commit managed documentation.
