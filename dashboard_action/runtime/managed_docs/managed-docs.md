# Managed Documentation

Reponomics ships local documentation into generated dashboard repositories so the guidance can match the action version that actually runs there.

## Managed Namespace

The managed namespace is `docs/reponomics/`.

Reponomics may update files inside that namespace when `.github/workflows/update-docs.yml` runs. It must not rewrite root repository docs, `config.yaml`, workflow files, retained dashboard data, tokens, secrets, or files outside the managed namespace as part of a docs update.

## Manifest

`docs/reponomics/.manifest.json` records:

- manifest schema version;
- managed namespace;
- action repository;
- action version;
- update timestamp;
- managed file hashes.

The manifest is the local freshness record. A floating action ref such as `@v0` may run a newer action without a workflow edit; managed docs update records that the newer action ran and that current local guidance is available.

## Update Workflow

The generated `Update Docs` workflow runs after successful Collect and Publish runs and can also be dispatched manually. Keep it enabled when you want local docs to track the action version that runs in this repository.

If you choose to own local edits under `docs/reponomics/`, disable or delete `.github/workflows/update-docs.yml` before editing this directory manually. When that workflow is enabled, Reponomics may regenerate the namespace during action upgrades.

If docs update reports `permission_missing`, grant `contents: write` to the update-docs job unless you intentionally disabled managed documentation updates.

## Continue

- [Upgrades](upgrades.md)
- [Provenance and verification](provenance.md)
