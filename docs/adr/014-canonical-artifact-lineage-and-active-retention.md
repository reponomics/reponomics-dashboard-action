# ADR 014: Canonical Artifact Lineage And Active Retention

Date: 2026-06-05

## Status

Accepted

## Context

The canonical Reponomics data store is the `dashboard-data` GitHub Actions
artifact. Git history contains workflow shells, configuration, generated README
output when enabled, and documentation; it is not the analytics database.

Simple artifact retention based only on `retention-days` is not a sufficient
data-safety policy. Expiration is wall-clock based and does not know whether a
newer good artifact exists. A short expiration can destroy the last known good
state during an outage. A long expiration preserves recoverability, but it also
increases storage use and, for encrypted modes, increases the amount of old
ciphertext that remains decryptable by an exposed old key.

The desired policy is closer to a commit graph than to a pile of independent
backup files. Each new retained artifact should be a verified successor of the
previous retained artifact. Cleanup should happen only after the action has
proved that a newer canonical state exists and preserves the previous canonical
state under retention and migration rules.

## Decision

Treat each retained `dashboard-data` artifact as a lineage node.

The runtime should eventually include an artifact manifest inside the canonical
retained payload. That manifest should record:

- manifest schema version
- artifact kind, action version, and creation timestamp
- parent artifact identity, including parent manifest and payload digest when a
  parent exists
- per-file SHA-256 digests for canonical retained files
- row counts and date ranges for canonical data families
- a semantic root digest over canonical retained row identities
- retention policy applied by the run, including any cutoff date used to drop
  old retained data
- schema migration version or equivalent migration identity

Digest commitments should be computed over the decrypted canonical payload, not
over encrypted artifact bytes. Encrypted bytes may legitimately change on every
upload because encryption must use fresh salt/nonce material.

Before uploading a replacement canonical artifact, `collect` should verify:

1. The restored parent artifact matches its own manifest.
2. The newly built child payload references the parent manifest/payload digest.
3. Every parent row still inside the configured retention horizon is present in
   the child state, or has been transformed by an explicit compatible migration.
4. Rows dropped from the child state are outside the configured retention
   horizon or are otherwise explicitly accounted for by migration policy.
5. If the preservation invariant fails, the action fails before upload.

After a replacement artifact has been uploaded successfully, the runtime may
actively delete older superseded `dashboard-data` artifacts according to the
configured rollback policy. This cleanup must be conditional on successful
successor upload and successful preservation checks.

`retention-days` remains useful, but only as an expiration safety window. It is
not the primary canonical-history policy. The primary policy is active
supersession:

- expire slowly enough to survive outages and GitHub platform delays
- supersede quickly after a verified newer canonical artifact exists
- keep only a small rollback window by default
- do not promise archival storage through passive Actions artifact retention

## Plaintext Mode

In `privacy-mode: plain`, the same lineage, manifest, digest, and semantic
preservation policy applies. The difference is confidentiality, not integrity.

Plain mode stores canonical CSV files and the lineage manifest directly in the
private repository's `dashboard-data` artifact. There is no encryption layer, so
the artifact payload digest can be computed directly over the canonical file
contents and manifest. The action should still verify parent digests, child
lineage, row preservation, retention cutoffs, and migration accounting before
uploading a replacement artifact.

Plain mode must continue to be private-repository only. The lineage manifest is
not secret: it may reveal filenames, row counts, date ranges, repository names
or identifiers, and other operational metadata. That is acceptable only because
plain mode already treats repository and artifact read access as the privacy
boundary.

The same active cleanup rule applies to plain mode: do not delete older
artifacts merely because wall-clock time passed; delete superseded artifacts
only after a verified newer canonical artifact has been uploaded.

## Rationale

This policy makes the artifact store auditable and safer:

- A collect run cannot silently replace retained data with a lossy artifact.
- Schema migrations have to account for preservation explicitly.
- Operators can distinguish the latest canonical state from rollback artifacts.
- Storage pressure is controlled by active cleanup rather than long passive
  retention tails.
- Incident response has fewer old decryptable artifacts to purge in encrypted
  modes.

The commit-tree analogy is deliberate, but the implementation should not make
GitHub artifact names content-addressable initially. The user-facing artifact
name should remain `dashboard-data` so workflow UX and restore behavior stay
simple. Content addressing belongs inside the manifest as digest metadata.

## Consequences

- The action needs dataset-specific semantic row identity definitions. A
  byte-for-byte CSV superset check is too strict because normalization,
  deduplication, ordering, and schema migrations can legitimately rewrite files.
- The runtime needs tests that cover loss prevention, allowed retention drops,
  and compatible migration transforms.
- Active cleanup requires GitHub Actions artifact deletion permissions in the
  workflows that perform cleanup.
- A separate outage sentinel becomes less central. If successful collect runs
  actively delete only after verified replacement, and artifacts retain a
  reasonable expiration safety window, ordinary outages should not destroy the
  last known good artifact. A watchdog may still be useful later, but it should
  not be the primary retention model. [CORRECTION: PREVIOUS "OUTAGE-SENTINEL" MODE IS SUPERCEDED BY THIS METHODOLOGY. THERE IS NO NEED FOR A SENTINEL - EACH ARTIFACT IS LONG-LIVED BY DEFAULT, BUT DELETED AS FRESH DATA IS COLLECTED.]

## Alternatives Considered

### 1) Rely only on `retention-days`

Pros:
- simple action surface
- no additional artifact metadata

Cons:
- expiration can delete the last known good artifact during a prolonged outage
- long retention increases storage use and incident exposure
- no proof that a newer artifact preserved prior retained data

### 2) Keep every recent artifact until expiration

Pros:
- many rollback points
- easy to understand operationally

Cons:
- storage use scales with artifact size and retention time
- old encrypted artifacts remain useful to anyone with an exposed old key
- passive retention still does not prove successor correctness

### 3) Use content-addressable GitHub artifact names

Pros:
- artifact identity would be obvious from the name
- easier manual inspection of digest history

Cons:
- more complicated workflow UX
- harder restore behavior
- unnecessary while GitHub artifact APIs already support a stable logical
  artifact name

## Non-Goals

This ADR does not implement:

- a concrete manifest schema
- dataset-specific row identity definitions
- active artifact cleanup inputs
- a signed attestation format
- content-addressable artifact naming
- long-term archival or rehydrate workflows

Those details should be designed and implemented in follow-up changes.
