# Credentials

Reponomics uses separate credentials for collection, repository workflow operations, and encrypted dashboard access. Keeping those roles separate is part of the dashboard security model.

## Collection Credential

`COLLECTION_TOKEN` is only for repository data collection. It does not need Pages, Actions, or write permissions.

For the default PAT mode, create a fine-grained personal access token for the owner whose repositories should be collected and grant repository `Administration: read` for the repositories listed in `collect.repositories`.

Fine-grained PATs are scoped to one GitHub resource owner. If one dashboard must collect repositories across multiple users or organizations, use a classic PAT with `repo` scope where the relevant organizations allow it, and treat that broader token accordingly.

## Advanced GitHub App Mode

Set `use_github_app: true` only when you operate your own GitHub App for collection. Reponomics does not provide or operate a shared collection app.

Advanced mode uses:

- `COLLECTION_APP_PRIVATE_KEY` as a repository secret.
- `COLLECTION_APP_ID` as a repository variable or secret.

The generated workflow mints a short-lived installation token and passes that token to the Reponomics action as the collection credential.

## Dashboard Key

Encrypted mode requires `DASHBOARD_SECRET_DO_NOT_REPLACE`. Store the same key in a password manager before saving it as a repository secret, because GitHub secrets cannot show the original value later.

Do not overwrite `DASHBOARD_SECRET_DO_NOT_REPLACE` for ordinary rotation. Add the replacement key as `DASHBOARD_NEXT_SECRET`, run **Rotate Key**, confirm the dashboard opens with the new key, then promote the new key and delete `DASHBOARD_NEXT_SECRET`.

## Workflow Token

The workflow `GITHUB_TOKEN` is separate from the collection credential. Generated workflows use it for checkout, artifact operations, README commits, Pages deployment, managed docs commits, and incident-reset cleanup according to each job's declared permissions.

## Continue

- [Dashboard key and recovery](../security-privacy/dashboard-key-and-recovery.md)
- [Workflow contract](../reference/workflow-contract.md)
