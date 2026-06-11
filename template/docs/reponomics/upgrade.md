# Upgrade Notes

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

This dashboard last received managed docs from Reponomics Dashboard Action 0.22.1.

If your workflow pins an exact action version such as `reponomics/reponomics-dashboard-action@v1.2.3`, you choose when to upgrade. If your workflow uses a floating major or minor ref such as `@v1`, a compatible Reponomics release can run in your repository without a workflow edit. Managed docs sync records that the newer action ran and that current local guidance is available.

When a new action version introduces optional features, the action may add or update documentation here. It will not change your `config.yaml` for you. Review the relevant docs, then opt into new configuration when you want the behavior.

If you want to keep local edits in `docs/reponomics/`, disable managed docs sync before making those edits. When docs sync is allowed, Reponomics may regenerate this directory during action upgrades.

If docs sync reports `permission_missing`, grant `contents: write` to the docs sync job or disable managed docs sync.
