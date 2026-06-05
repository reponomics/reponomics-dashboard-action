# Template Setup README

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

This document preserves the template setup guidance that may be replaced by generated README dashboard output in private repositories.

The Reponomics Dashboard collects repository traffic and growth data, stores retained state in GitHub Actions artifacts, and renders optional dashboard outputs through GitHub Actions. The generated repository remains intentionally thin: collection, encryption, rendering, key rotation, incident reset behavior, CSV export, and managed docs sync are owned by `reponomics/reponomics-dashboard-action`.

Before setup, configure `config.yaml`, add the required collection credential, choose a privacy mode, and add `DASHBOARD_SECRET_DO_NOT_REPLACE` for `strong` or `casual` privacy modes. For current setup details, see [Dashboard repository guide](repository-guide.md), [Configuration reference](configuration.md), and [Secure Dashboard Key Generation](secure-dashboard-key.md).

Reponomics may update this managed documentation directory when `allow_docs_sync` is enabled. User-owned files outside `docs/reponomics/`, including the repository root `README.md`, are not managed by docs sync.
