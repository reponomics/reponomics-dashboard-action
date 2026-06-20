# ADR 026: Pages Dashboard Publication Verification Summary

Date: 2026-06-19

## Status

Accepted

## Context

Reponomics already has substantial provenance and integrity controls around the dashboard lifecycle:

- retained dashboard data artifacts are encrypted or retained according to the configured data mode;
- encrypted dashboard payloads use an authenticated chunked model;
- encrypted CSV export assets carry ciphertext and plaintext SHA-256 checks;
- vendored browser assets are pinned and validated;
- runtime Python dependencies are hash-locked;
- template and release artifacts have separate provenance and attestation tracks.

Those controls are real, but much of the evidence is hard for ordinary users to consume. A user can inspect workflow artifacts, artifact digests, provenance files, release attestations, and generated files, but that requires too much manual effort for the normal "did this run publish what it says it published?" question.

GitHub Actions now exposes artifact digests in the workflow UI and through the Actions artifacts API. The current template already uploads dashboard artifacts with product-relevant names such as `dashboard-data`, `html-dashboard-encrypted`, and `html-dashboard-plaintext`. The hosted Pages path also deploys the `html-dashboard-encrypted` artifact by name. This creates an opportunity to make publication provenance visible in the workflow summary, where users already look after a collect/publish run.

The missing link is the deployed web page. Verifying that GitHub accepted an artifact is useful, but it does not by itself prove that the live Pages URL is serving the same rendered dashboard tree. A meaningful user-facing check needs to tie together:

- the rendered dashboard file tree;
- the GitHub Actions artifact that stored that tree;
- the Pages deployment that consumed that artifact;
- the live Pages URL observed after deployment.

The Pages REST API does not appear to expose a deployed-content digest. Its `source` object describes branch/path configuration for Pages source settings, not a hash of deployed files. Pages deployment status can report deployment success, but not content identity. Therefore Reponomics must compute its own content identity for the rendered dashboard tree and verify the live deployment by fetching the deployed site after deployment.

## Decision

Add a workflow-summary publication verification section for generated dashboard outputs.

For hosted encrypted Pages publication, the publish path should:

01. Render the dashboard output directory.
02. Compute a canonical dashboard tree digest over the rendered Pages directory.
03. Write a machine-readable dashboard publication manifest into the rendered output directory.
04. Upload the rendered directory as the existing `html-dashboard-encrypted` Pages artifact.
05. Record the uploaded artifact ID and retrieve the GitHub-reported artifact digest for that artifact.
06. Deploy Pages from the same `html-dashboard-encrypted` artifact.
07. Fetch the live Pages URL after deployment.
08. Recompute the canonical dashboard tree digest from served bytes.
09. Compare the served tree digest to the pre-upload rendered tree digest.
10. Append a clear pass/fail verification section to `GITHUB_STEP_SUMMARY`.

For private plaintext and unpublished encrypted dashboard artifacts, the same rendered tree digest and artifact digest should be summarized when an HTML dashboard artifact is uploaded. Live Pages verification is skipped because those surfaces are not deployed.

The summary is an end-user assurance surface. It is not a replacement for release attestations, artifact retention, doctor diagnostics, or deeper provenance files. It is the readable bridge between those mechanisms and the normal workflow UI.

## Summary Shape

The workflow summary should use stable, direct language similar to:

```markdown
## Dashboard publication verification

| Field | Value |
| --- | --- |
| Dashboard mode | `encrypted` |
| Pages publication | `enabled` |
| Source commit | `abc123...` |
| Workflow run | `123456789` |
| Run attempt | `1` |
| Dashboard artifact | `html-dashboard-encrypted` |
| Artifact ID | `987654321` |
| GitHub artifact digest | `sha256:...` |
| Rendered tree digest | `sha256:...` |
| Pages URL | `https://owner.github.io/repo/` |
| Live Pages tree digest | `sha256:...` |
| Live Pages verification | `passed` |
```

For skipped or unavailable checks, the summary should say why:

- Pages verification `skipped`: Pages publication disabled.
- Pages verification `skipped`: plaintext mode cannot publish Pages.
- Pages verification `failed`: live URL did not serve the expected tree digest.
- Artifact digest `unavailable`: GitHub artifact lookup failed.

Preferred summary phrasing:

> Live Pages served the same canonical dashboard tree that this workflow rendered before uploading the Pages artifact.

## Canonical Tree Digest

The project should use its own deterministic tree digest in addition to GitHub's artifact digest.

GitHub's artifact digest identifies the uploaded artifact object. For Pages artifacts, `actions/upload-pages-artifact` first creates a tar archive and then uploads that tar through `actions/upload-artifact`. That archive digest is valuable because GitHub stores and displays it, but it is not the best stable identity for the dashboard product payload.

The Reponomics canonical tree digest should identify the unpacked rendered dashboard tree:

- normalize paths to POSIX separators;
- sort file entries by path;
- reject or explicitly skip `.git` and `.github`;
- reject symlinks unless a future ADR defines symlink semantics;
- include each file path, byte length, and SHA-256 of raw file bytes;
- compute a final SHA-256 over a deterministic manifest representation.

A JSON Lines manifest is sufficient:

```jsonl
{"path":"index.html","size":12345,"sha256":"..."}
{"path":"assets/base.css","size":23456,"sha256":"..."}
{"path":"assets/dashboard/entry-secure.js","size":34567,"sha256":"..."}
```

The final tree digest is the SHA-256 of the UTF-8 encoded manifest bytes. The manifest itself should not be included in its own digest unless the project later defines a self-exclusion rule. The simplest rule is:

- compute the tree digest over deployable dashboard payload files;
- exclude `assets/dashboard-publication-manifest.json` from the tree digest;
- write the manifest after the tree digest is known.

The publication manifest should include:

- schema version;
- algorithm;
- canonical tree digest;
- file entries;
- repository;
- source SHA;
- workflow run ID;
- run attempt;
- dashboard mode;
- Pages publication flag;
- generated timestamp;
- action runtime version.

It may also include the GitHub artifact ID, artifact name, artifact digest, Pages deployment URL, and live verification result after those values are known. If those values are not available at render time, a later workflow step may update the manifest or write a separate verification report artifact.

## Artifact Digest

The GitHub artifact digest remains useful and should be printed next to the canonical tree digest.

The uploaded artifact identity should be treated as a tuple:

- repository;
- workflow run ID;
- run attempt;
- artifact name;
- artifact ID;
- artifact digest;
- source commit.

This avoids overinterpreting the digest as a globally stable product version. If identical bytes are uploaded in another run, the digest may be the same, but the artifact record and workflow context are distinct.

Implementation should prefer action outputs when available:

- `actions/upload-pages-artifact` exposes `artifact_id`;
- `actions/upload-artifact` exposes artifact metadata for ordinary dashboard artifacts;
- if the digest is not available as a step output, query the Actions artifact REST endpoint for the artifact ID or list workflow-run artifacts filtered by name.

The summary should include the GitHub artifact digest exactly as GitHub reports it, normally in `sha256:<hex>` form.

## Live Pages Verification

Live Pages verification should run only after `actions/deploy-pages` reports a successful deployment and returns the `page_url`.

The verifier should:

1. Fetch the deployed `page_url`.
2. Parse the HTML for expected same-origin dashboard assets.
3. Fetch the files needed to reconstruct the canonical deployed tree.
4. Include `index.html`, first-party dashboard modules, CSS, fonts, vendored Chart.js, dashboard JSON payload assets, export manifest, and encrypted export asset when present.
5. Compute the canonical tree digest from the fetched bytes using the same algorithm as the pre-upload renderer.
6. Compare the served digest with the pre-upload rendered digest.
7. Fail the workflow, or at minimum mark the summary check failed, if the digests differ.

For the first implementation, it is acceptable for the verifier to use the rendered manifest's file list rather than independently discovering every asset. The manifest defines the expected product tree for that run. The verifier fetches each listed path from the live Pages URL and compares bytes through the canonical digest calculation.

The verifier must not fetch remote third-party assets because the dashboard contract prohibits them. Encountering a remote script, stylesheet, font, or data payload should be treated as a verification failure.

The verifier should use conservative cache bypassing where practical:

- append a query string such as `?reponomics_verify=<run_id>-<attempt>` for fetches if GitHub Pages serves the same bytes for query variants;
- set `Cache-Control: no-cache` request headers;
- retry briefly to allow Pages propagation after deployment.

If Pages propagation causes transient mismatches, the summary should report the final state and the verifier should include enough diagnostics to distinguish timeout from content mismatch.

## Security Properties

This check adds workflow-visible assurance that:

- the workflow rendered a dashboard tree with a specific canonical digest;
- GitHub accepted a named dashboard artifact with a specific artifact digest;
- the Pages deploy step targeted that named artifact;
- the live Pages URL served a tree with the same canonical digest when the verifier fetched it.

The check is valuable because it turns existing provenance into a visible, low-friction workflow result and closes the practical gap between "artifact was uploaded" and "the deployed Pages site served that artifact's rendered tree."

## Relationship To CSP And ESM

ADR 025 moved the hosted dashboard to native ESM with a strict CSP and no inline executable code. That change reduces injection risk, but it deliberately removes the old incidental CSP-hash sensitivity of inline blocks in the hosted artifact.

The publication verification summary fills a different role:

- CSP controls what the browser is allowed to execute or load;
- encrypted payload authentication controls dashboard data integrity after the key is provided;
- export SHA-256 checks control downloadable export integrity;
- artifact and tree digests identify what the workflow produced and uploaded;
- live Pages verification checks what the deployed URL served after deployment.

These controls are complementary and should not be collapsed into one broad "provenance" claim.

## Product Behavior

The dashboard user experience should remain unchanged. Users still open the dashboard, unlock it with their dashboard key, view charts, and optionally export CSV data.

The new user-visible surface is the Actions run summary. It should make the publication state easy to scan without requiring artifact downloads, attestation tooling, or API calls.

The dashboard page may display the rendered tree digest and workflow run ID for discoverability, but that display is secondary. The workflow summary is the authoritative user-facing verification surface for this ADR.

## Implementation Plan

01. Add a small no-dependency Python module for canonical dashboard tree manifests and tree digests.
02. During `publish` and `rotate-key` render paths, compute the rendered dashboard tree manifest for `steps.runtime.outputs.pages-path`.
03. Write `assets/dashboard-publication-manifest.json` into the rendered dashboard directory after computing the tree digest.
04. Expose the rendered tree digest and manifest path as composite action outputs.
05. Give the `Upload GitHub Pages artifact` step an `id` and capture its `artifact_id`.
06. Query the Actions artifact API for the artifact digest associated with that artifact ID.
07. After `Deploy GitHub Pages`, run a verifier script against `steps.deploy-pages.outputs.page_url`.
08. Append the publication verification table to `GITHUB_STEP_SUMMARY`.
09. For non-Pages dashboard artifacts, append an artifact-only summary table and mark live Pages verification as skipped.
10. Add tests for digest determinism, manifest exclusion behavior, summary content, artifact lookup behavior, and live-verifier mismatch reporting.

The first implementation should keep this inside the existing generated workflow and composite action rather than introducing a separate follow-up workflow. A separate follow-up workflow can be considered later if we need longer-running periodic verification of the currently live site.

## Test Plan

Add unit coverage for:

- deterministic tree digest ordering;
- byte-size and SHA-256 manifest entries;
- rejection or exclusion of unsupported paths;
- exclusion of `assets/dashboard-publication-manifest.json`;
- stable digest changes when a file byte changes;
- stable digest changes when a file path changes.

Add workflow/template coverage for:

- `Upload GitHub Pages artifact` has an `id`;
- `html-dashboard-encrypted` remains the artifact deployed to Pages;
- summary verification steps run only for publish/rotate-key Pages output;
- plaintext/private artifact paths summarize artifact identity but skip live Pages verification;
- generated workflows retain least-needed permissions.

Add integration-style tests for:

- rendered manifest presence in generated dashboard output;
- summary markdown includes tree digest, artifact name, run ID, run attempt, source SHA, and Pages verification result;
- live verifier passes when served bytes match the manifest;
- live verifier fails when `index.html` or a dashboard module differs;
- live verifier fails on unexpected remote assets.

## Consequences

Users get a visible, low-effort integrity and provenance check in the workflow summary. This makes existing provenance work more legible without asking users to download artifacts, inspect JSON, or understand GitHub attestations.

The workflow gains a small amount of complexity and an additional post-deploy network check. That complexity is justified because hosted Pages output is the primary encrypted product surface.

The check is strong evidence that the deployed site matched the rendered artifact at verification time, and it presents that evidence in the same UI where GitHub already exposes artifact digests.

## Open Questions

- Should a live Pages verification mismatch fail the publish workflow immediately, or should the first release report failure in the summary while avoiding deployment rollback behavior?
- Should the dashboard page display the tree digest and run ID, or should those stay only in the workflow summary and manifest?
- Should a later scheduled workflow periodically re-verify the current Pages site against the most recent successful publication summary?
- Should the publication manifest be retained only inside the deployed tree, or also uploaded as a separate small artifact for easier download?
- Should this summary eventually link to GitHub artifact attestations when they exist, while keeping the digest table readable for non-specialist users?
