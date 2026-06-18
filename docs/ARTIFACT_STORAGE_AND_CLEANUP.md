# Artifact Storage and Active Cleanup

1. Restore the latest retained `dashboard-data` artifact.
2. Decrypt it when `data-mode` is `encrypted`.
3. Validate the restored parent payload against its lineage manifest when one exists.
4. Migrate the restored retained data packet to the runtime's current canonical CSV schema.
5. Collect fresh GitHub data and merge it into the canonical CSV payload.
6. Build a new child lineage manifest over the decrypted/plaintext canonical payload.
7. Verify that the child preserves all parent rows still inside the configured retention horizon, allowing only explicit retention drops and compatible migrations.
8. Encrypt the child payload when required.
9. Upload the fresh `dashboard-data` artifact.
10. Delete the oldest retained `dashboard-data` artifact after upload succeeds.

If collection fails, merge fails, manifest verification fails, encryption fails, or upload fails, no active cleanup runs. The previous unexpired artifact remains the recovery point.

## Retention Defaults

The default `retention-days` stays long, currently 90 days by default (user-configurable between 14-90 days) and still bounded by GitHub's artifact retention limits. The working model is: while collection is working as expected, artifacts are expected to be very short-lived, because each collection run deletes the oldest retained backup - the retention period, therefore, should be very long, by default, because it is only operationally relevant if there is a failure somehwere in the collection/storage pipeline.

## Lineage Manifest

The manifest is part of the canonical payload and is committed to the artifact before encryption. In encrypted modes, digests are computed before encryption over canonical plaintext files. In `plaintext`, digests are computed over the same canonical files directly.

The manifest includes:

- manifest schema version
- artifact kind: `dashboard-data`
- action version
- creation timestamp
- retention days and retention cutoff date
- parent manifest digest and parent payload digest when a parent exists
- per-file SHA-256 digests for registered canonical CSV files
- row counts and date ranges for registered canonical CSV files
- a semantic row-root digest over registered canonical row identities
- payload digest over the canonical per-file digest set

## Preservation Rules

Lineage verification is semantic, not byte-for-byte CSV comparison. CSV order, normalization, deduplication, and compatible schema additions may change bytes without losing data.

Each registered CSV needs a row identity:

- `traffic-log.csv`: `repo`, `ts`, `captured_at`
- `traffic-daily.csv`: `repo`, `ts`
- `traffic-snapshots.csv`: `repo`, `ts`, `captured_at`
- `traffic-referrers.csv`: `repo`, `captured_at`, `referrer`
- `traffic-paths.csv`: `repo`, `captured_at`, `path`
- `repo-metrics.csv`: `repo`, `captured_at`
- `collection-status.csv`: `repo`, `captured_at`, `status`

For each parent row inside the child retention horizon, the child must contain the same row identity in the same CSV family. Parent rows older than the child retention cutoff may be dropped. Any future migration that changes row identity must be represented as an explicit migration rule and tested.

## Retained Packet Migrations

The migration boundary is restore -> decrypt -> `storage.migrate_schema()` -> collect/render/rotate/reset. Downstream collection, merge, load, and render code should see only the current canonical CSV registry.

The project policy for retained packet compatibility, versioned migrations, and breaking changes lives in [Retained Data Migrations](./RETAINED_DATA_MIGRATIONS.md).

Compatible retained-data changes must follow these rules:

1. Add new CSV families to `storage.CSV_REGISTRY` with a row identity in `lineage.ROW_IDENTITY_FIELDS` when rows must be preserved across child artifacts.
2. Add new fields to the canonical field list. Historical rows receive blank values unless `storage.CSV_FIELD_DEFAULTS` defines a safe default.
3. Rename fields through `storage.CSV_FIELD_ALIASES`; do not leave fallback reads scattered through render or load code.
4. Rename CSV files through `storage.LEGACY_FILE_RENAMES`. Lineage validation reads recorded file digests from the restored manifest before migration, so renamed files can still be validated and then normalized into the current file name.
5. Bump `storage.SCHEMA_VERSION` when the retained packet shape changes. The runtime may migrate older schemas forward; it rejects artifacts whose manifest schema is newer than the runtime.
6. Add or update a compatibility fixture that exercises `publish`, `collect`, and encrypted `rotate-key` when encryption applies. The fixture must prove historical rows are retained and `config.yaml` is not silently rewritten.

Breaking changes are changes that cannot be represented as a compatible forward migration. Examples include dropping retained history, changing row identity without an explicit transform, requiring new non-null historical values with no safe default, or changing the encrypted artifact envelope without a versioned decrypt path.

## Active Deletion

Routine active deletion is artifact-only. It deletes old `dashboard-data` artifacts, not workflow runs. `incident-reset` mode can be used if the repo owner wants to completely destroy previous workflow runs, logs, and artifacts.

The cleanup step requires `actions: write` in the consuming collect workflow. Generated dashboard repositories should grant that permission at the collect job level, not at the workflow top level.
