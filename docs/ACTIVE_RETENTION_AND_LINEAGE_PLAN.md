# Active Retention And Lineage Implementation Plan

Status: action-side implementation in progress. Lineage writing, retained-row verification, and collect post-upload artifact cleanup are implemented in `reponomics-dashboard-action`; generated dashboard workflows still need the corresponding collect job `actions: write` wiring before this is fully shipped to users.

The canonical policy is [ADR 014](./adr/014-canonical-artifact-lineage-and-active-retention.md). This document records the concrete transition plan so the project is not left halfway between the old passive-retention model and the new active-retention model.

## Target Model

`dashboard-data` remains the stable user-facing artifact name. GitHub Actions artifact `retention-days` is a long expiration safety window, not the primary history policy. The primary history policy is active supersession:

1. Restore the latest retained `dashboard-data` artifact.
2. Decrypt it when `data-mode` is `encrypted`.
3. Validate the restored parent payload against its lineage manifest when one exists.
4. Collect fresh GitHub data and merge it into the canonical CSV payload.
5. Build a new child lineage manifest over the decrypted/plaintext canonical payload.
6. Verify that the child preserves all parent rows still inside the configured retention horizon, allowing only explicit retention drops and compatible migrations.
7. Encrypt the child payload when required.
8. Upload the fresh `dashboard-data` artifact.
9. Delete only older superseded `dashboard-data` artifacts after upload succeeds.

If collection fails, merge fails, manifest verification fails, encryption fails, or upload fails, no active cleanup runs. The previous unexpired artifact remains the recovery point.

## Retention Defaults

The default `retention-days` stays long, currently 90 days and still bounded by GitHub's artifact retention limits. The long value absorbs ordinary outages, GitHub platform delays, disabled schedules, exhausted Actions minutes, and operator absence.

Active cleanup keeps storage and incident exposure bounded despite the long expiration window. The cleanup policy should keep a small rollback window by default. The first implementation should keep the latest two prior artifacts plus the artifact just uploaded, and delete at most one older superseded artifact per successful collection run. That is intentionally conservative: routine cleanup should not batch many non-GET API calls or consume a user's rate-limit budget aggressively.

## Lineage Manifest

The manifest is part of the canonical payload and is committed to the artifact before encryption. In encrypted modes, digests are computed before encryption over canonical plaintext files. In `plaintext`, digests are computed over the same canonical files directly.

The initial manifest should include:

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

The first implementation can accept legacy parent artifacts that do not yet have lineage metadata. For those parents, the action should compute a legacy parent snapshot after restore/decrypt/migration and require the child to preserve that snapshot before upload. Newly written artifacts must include the lineage manifest.

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

Routine active deletion is artifact-only. It should delete old `dashboard-data` artifacts, not workflow runs. Workflow-run deletion is reserved for `incident-reset`, where the goal is to burn down old decryptable history and GitHub deletes run artifacts as part of run deletion.

The post-upload cleanup step runs only for `mode: collect`. It lists repository artifacts named `dashboard-data`, excludes the current run, sorts the remaining artifacts by creation time newest first, preserves the newest rollback window, and deletes only the next older artifact. It should report counts in the step summary, not routine per-ID lists.

The cleanup step requires `actions: write` in the consuming collect workflow. Generated dashboard repositories should grant that permission at the collect job level, not at the workflow top level.

## Intermediate State

Until this implementation lands everywhere:

- dashboard-dev must not ship a separate outage-sentinel workflow;
- `retention-days` remains the safety net;
- old artifacts may accumulate up to the passive expiration window;
- `incident-reset` remains the manual emergency path for exposed dashboard keys;
- active deletion must wait until a successful successor upload has occurred.

This is intentionally conservative. It may temporarily keep more old artifacts than the target model, but it avoids deleting the last known good artifact.
