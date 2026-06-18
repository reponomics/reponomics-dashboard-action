# Retained Data Migrations

This is the living policy for evolving the retained `dashboard-data` packet.
The retained packet is the durable compatibility contract between collection
runs, publication runs, action releases, and generated template users.

The goal is to avoid maintaining separate compatibility matrices for template
versions, action versions, and collect/publish pairings. Runtime compatibility
should be judged by one question:

> Can the current runtime migrate this retained packet schema into the current
> canonical schema without losing retained meaning?

## Compatibility Model

Retained data compatibility is schema-based, not runtime-version-based.

- `storage.SCHEMA_VERSION` identifies the current retained packet schema.
- A runtime may migrate older retained packet schemas forward.
- A runtime must reject retained packets whose schema is newer than it can
  understand.
- When a minimum supported schema floor is introduced or raised, that floor is
  the compatibility boundary.

A current runtime should carry the ordered migration chain from every supported
retained packet schema to the current schema. A user should not need to run each
intermediate action release just to upgrade retained data from, for example,
schema `3` to schema `6`.

If a direct jump is not supportable, the release must say so explicitly and
provide a bridge-release path, such as "upgrade once through version X, then
upgrade to this release." That should be treated as a compatibility reset, not
as ordinary compatible runtime behavior.

## Template Impact

Generated template users can freeze the action version they started with, either
by policy or by SHA pinning. If those users later upgrade directly from an older
runtime to a newer runtime, their retained artifact may have been produced by
the old action version that shipped with their template snapshot.

For that reason, retained packet compatibility is also template compatibility.
A release is breaking when it removes the upgrade path for retained packet
schemas produced by a previously supported template/action pairing within the
declared compatibility line.

This keeps one criterion for breaking changes:

> A release is compatible when supported retained packets, including packets
> produced by supported historical templates, can migrate to the current packet
> schema and continue through collect, publish, rotate-key, and reset flows.

The template version may still change for workflow, setup, permissions, docs, or
generated-file reasons, but retained-data compatibility should not become a
second template-versus-runtime matrix.

## Template Compatibility Tests

Template compatibility end-to-end tests must also prove retained packet
compatibility. When CI checks the current runtime against the current template
and the minimum compatible template, it should include retained artifact
fixtures produced by the action/schema that originally shipped with those
template snapshots.

Those tests do not create a second compatibility floor. They are evidence for
the same retained schema floor: a supported historical template/action pairing
must have a migration path from its original retained packet schema to the
current runtime schema.

The useful assertion is:

> The current runtime can restore a retained packet produced by the supported
> template floor, migrate it to the current schema, and complete publish,
> collect, and encrypted maintenance flows without losing retained rows.

## Migration Types

Structural migrations normalize packet shape without computing new semantics.
Examples:

- add a CSV family
- add a field with a blank or safe static default
- rename a field through aliases
- rename a CSV file
- normalize row `schema_version`

Computational migrations reconstruct a new field or table from retained data.
Examples:

- add `score_v2` while preserving legacy `score`
- compute `score_v2` for old rows from retained inputs
- split a table into a new canonical shape when row identity can still be
  preserved

Computational migrations are in scope when they are deterministic over retained
data. They should be versioned, idempotent, tested from old fixtures, and kept
centralized in the migration layer rather than scattered through render or load
code.

Historical backfills for data that was never collected are a different class of
work. They may be possible when an API can still provide the missing history,
but they are not guaranteed by retained packet migration.

## Semantic Changes

Do not silently change the meaning of an existing retained field.

If a field's meaning changes, prefer adding a new field and teaching readers to
prefer the new field when present. For example, introduce `score_v2` rather than
redefining `score` in place. The migration may backfill `score_v2` for retained
rows when the value can be deterministically computed from retained inputs.

Legacy fields can remain present for compatibility even if the runtime no longer
uses them as the preferred semantic source.

## Migration Requirements

Compatible migrations should be:

- deterministic from the retained packet and runtime configuration;
- idempotent, so re-running migration does not keep changing data;
- ordered by retained packet schema version;
- explicit about field aliases, file renames, defaults, and computed transforms;
- strict about missing required inputs when no honest default or derivation
  exists;
- covered by lineage checks when retained rows must be preserved;
- tested from old retained-packet fixtures directly against the current runtime.

Compatibility is not assumed to be transitive just because each adjacent release
worked at the time. The current runtime proves compatibility by migrating old
supported fixtures directly to the current schema.

## Breaking Changes

Retained data changes are breaking when they cannot be represented as a safe
forward migration from the supported schema floor. Examples include:

- dropping retained history inside the retention horizon;
- removing a migration step while its source schema is still supported;
- raising the minimum supported retained packet schema;
- changing row identity without an explicit identity-preserving transform;
- requiring new historical values that cannot be derived or safely defaulted;
- redefining an existing field's meaning instead of introducing a new semantic
  field;
- changing the encrypted artifact envelope without a versioned decrypt path;
- accepting a restored artifact with a conflicting `data-mode`.

Raising the supported schema floor is allowed, but it is a breaking release and
must be announced as such. Prefer retaining old migrations until there is a
clear operational reason to drop them.

## Review Checklist

For retained data changes:

1. Decide whether the change is structural, computational, or historical
   backfill.
2. Bump `storage.SCHEMA_VERSION` when the retained packet shape changes.
3. Add migration rules or versioned migration steps from every supported older
   schema to the current schema.
4. Preserve row identity or explicitly migrate it.
5. Add or update compatibility fixtures for `publish`, `collect`, and encrypted
   `rotate-key` when encryption applies.
6. Include template-floor retained artifacts in template compatibility CI so
   pinned-template users have a proven direct upgrade path.
7. Verify old supported fixtures migrate directly to the current runtime.
8. Treat any raised schema floor or missing upgrade path as a breaking release.

## Implementation Hygiene

`storage.py` should remain the home for canonical packet shape and low-level
CSV/manifest I/O. Migration policy should move to a separate runtime module once
migrations become versioned, computational, or large enough to make the storage
module hard to scan. As a practical context-management signal, migration code
growing the file beyond roughly 500-600 lines is enough reason to split it.

## Open Work

This checklist records known implementation gaps in the current migration
system. Remove or revise items as they are completed.

1. Extract migration policy from `storage.py` into a dedicated runtime migration
   module before adding substantive new migration behavior.
2. Add a versioned migration registry with an explicit current schema and
   minimum supported schema floor.
3. Support ordered computational migrations for deterministic retained-data
   backfills, such as adding `score_v2` while preserving legacy `score`.
4. Add tests that prove a retained packet can migrate directly from every
   supported schema fixture to the current runtime schema.
5. Extend template compatibility CI so the current runtime is tested against
   retained artifacts produced by the minimum compatible template's original
   accepted action/schema.
6. Add or update release gates so a release that raises the retained schema
   floor or removes an upgrade path is classified as breaking.
7. Improve runtime failure messages for unsupported old schemas so users get a
   clear bridge-release upgrade path when one exists.
8. Maintain a small fixture inventory that records which retained packet schema
   each compatibility fixture represents and which template/action pairing
   produced it.
