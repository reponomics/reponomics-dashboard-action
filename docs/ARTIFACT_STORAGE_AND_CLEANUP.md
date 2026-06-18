# Artifact Storage and Active Cleanup

1. Restore the latest retained `dashboard-data` artifact.
2. Decrypt it when `data-mode` is `encrypted`.
3. Validate the restored parent payload against its lineage manifest when one exists.
4. Collect fresh GitHub data and merge it into the canonical CSV payload.
5. Build a new child lineage manifest over the decrypted/plaintext canonical payload.
6. Verify that the child preserves all parent rows still inside the configured retention horizon, allowing only explicit retention drops and compatible migrations.
7. Encrypt the child payload when required.
8. Upload the fresh `dashboard-data` artifact.
9. Delete the oldest retained `dashboard-data` artifact after upload succeeds.

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

## Active Deletion

Routine active deletion is artifact-only. It deletes old `dashboard-data` artifacts, not workflow runs. `incident-reset` mode can be used if the repo owner wants to completely destroy previous workflow runs, logs, and artifacts.

The cleanup step requires `actions: write` in the consuming collect workflow. Generated dashboard repositories should grant that permission at the collect job level, not at the workflow top level.
