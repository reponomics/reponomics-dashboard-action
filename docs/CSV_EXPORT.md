---
name: CSV_EXPORT.md
description: Canonical documentation for in-app CSV export system design and privacy/encryption model that it assumes.
created: 2026-05-23
last_modified: 2026-05-23
---

# CSV Export Architecture Guide

## Purpose

This document is the long-lived technical reference for CSV export delivery. ADR 004 records the decision; this file explains how the export architecture works in practice and how to plan capacity as datasets evolve.

## Scope

- Applies to encrypted dashboard publication mode (`encrypted`).
- Export payload is canonical retained data, not dashboard-view projections.
- `plaintext` mode does not publish a Pages dashboard export path.

## Architecture Summary

### 1) Canonical source of export data

The export bundle is built from canonical retained files:

- every CSV file registered in `storage.CSV_REGISTRY`
- `manifest.json`

This includes repos currently excluded from dashboard rendering, because export is for retained-data portability and parity.

### 2) Publish-time build pipeline

On encrypted publish:

1. Build a deterministic ZIP from the canonical files.
2. Compute `plaintext_sha256` of ZIP bytes.
3. Encrypt ZIP with AES-GCM under a PBKDF2-derived key from dashboard secret.
4. Compute `ciphertext_sha256`.
5. Write encrypted asset to a content-addressed path: `assets/export-data-<digest16>.enc`.
6. Embed only compact export metadata in `index.html` (`export-manifest`).

### 3) Runtime export pipeline (browser)

After successful dashboard unlock and explicit export click:

1. Validate manifest structure and strict asset path pattern.
2. Fetch encrypted asset.
3. Verify ciphertext size and `ciphertext_sha256`.
4. Decrypt with the same key boundary used for dashboard unlock.
5. Verify decrypted ZIP bytes against `plaintext_sha256`.
6. Trigger ZIP download and clear in-memory buffers best effort.

No plaintext export bytes are uploaded back to GitHub by this path.

## Security and Integrity Model

- `ciphertext_sha256`: catches transport/cache corruption before decrypt.
- AES-GCM decrypt success/failure: keyed ciphertext integrity/authenticity check.
- `plaintext_sha256`: confirms decrypted bytes match publish-time canonical ZIP.

Important boundary:

- These controls protect payload integrity at export time.
- They do not replace trust requirements for build/deploy/runtime supply chain.

## Caching and Asset Versioning

- Export asset filenames are content-addressed to avoid stale-cache mismatches.
- Manifest asset path validation is strict: `assets/export-data-[a-f0-9]{16}.enc`.

## Offline Behavior

- `file://` export is best-effort, not guaranteed across browsers.
- If browser fetch/CORS behavior blocks local-file export, runtime fails closed with explicit error messaging.
- Recommended fallback: hosted Pages URL or serving extracted artifact files over local HTTP.

## Performance Posture

Hard architectural budgets:

- Export ciphertext bytes in initial HTML: `0`.
- Export fetch/decrypt work before user clicks export: `0`.

Operational target:

- Keep click-to-download within an interactive desktop range for the reference profile (`R=50`, `D=90`, `C=1`) as features evolve.

## Size Estimation Framework

Use these variables:

- `R`: tracked repos
- `D`: retained days
- `C`: effective collect runs per day
- `W`: traffic-window rows returned per run for views/clones (currently 14)
- `q_r`: referrer rows per repo/run (current API top list, up to 10)
- `q_p`: path rows per repo/run (current API top list, up to 10)
- `b_*`: average bytes per CSV data row (including newline)
- `H`: fixed header/manifest overhead bytes

### Row-count model

Per retention window:

- `N_log ~= R * C * W * D`
- `N_snap ~= R * C * W * D`
- `N_daily ~= R * D`
- `N_metric ~= R * C * D`
- `N_ref ~= R * C * q_r * D`
- `N_path ~= R * C * q_p * D`

### Raw CSV bytes model

```text
S_raw ~= H
       + N_log*b_log
       + N_snap*b_snap
       + N_daily*b_daily
       + N_metric*b_metric
       + N_ref*b_ref
       + N_path*b_path
```

Expanded:

```text
S_raw ~= H + R*D * (
  C*W*(b_log + b_snap)
  + b_daily
  + C*(b_metric + q_r*b_ref + q_p*b_path)
)
```

### ZIP and encrypted asset approximation

Let `rho` be ZIP compression ratio (`S_zip / S_raw`).

- Typical CSV-heavy range: `rho ~= 0.25..0.45`
- `S_zip ~= rho * S_raw`
- `S_enc ~= S_zip + 16 + O(1KB)` (`16` is AES-GCM tag bytes; metadata is small and near-constant)

### Worked baseline (current schema profile)

Representative row-byte profiles used internally:

- Typical: `b_log=73`, `b_snap=69`, `b_daily=73`, `b_metric=221`, `b_ref=61`, `b_path=121`
- Conservative: `b_log=120`, `b_snap=110`, `b_daily=120`, `b_metric=300`, `b_ref=100`, `b_path=260`

For `R=50`, `D=90`, `C=1`, `W=14`, `q_r=q_p=10`:

- Typical raw: `~17.6 MB`
- Conservative raw: `~31.1 MB`
- Typical encrypted asset (ZIP range): `~4.4..7.9 MB`
- Conservative encrypted asset (ZIP range): `~7.8..14.0 MB`

Cadence impact:

- Moving from `C=1` to `C=2` is approximately `~1.98x` payload growth.

## Guidelines When Adding New Data Points

When a new retained table/metric is added:

1. Update canonical schema (`storage.CSV_REGISTRY` and migrations).
2. Decide export inclusion semantics (default: include canonical retained data).
3. Add or update runtime manifest and validation tests.
4. Recalibrate row-byte assumptions (`b_*`) from generated fixture data.
5. Recompute `S_raw`, `S_zip`, `S_enc` for reference profiles.
6. Check that initial HTML and pre-click work budgets remain unchanged.

## Testing Expectations

- Export manifest exists in encrypted dashboard HTML.
- Export asset is generated and content-addressed.
- Decrypted export ZIP reproduces canonical retained files.
- Integrity failures (ciphertext size/digest, plaintext digest, wrong key) fail closed with no partial plaintext output.
- Pre-unlock export remains unavailable.
