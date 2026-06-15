# Product Provenance And Release Verification

This document explains what Reponomics release provenance is intended to prove for users and reviewers. It focuses on the two shipped products: the GitHub Action and the generated dashboard template.

## Short Version

Reponomics publishes source code and generated products. A release provenance claim should identify the exact thing a user receives, then link it back to the source commit and workflow that produced it.

For the action product, users consume `reponomics/reponomics-dashboard-action` through Git tags such as `v0` or exact tags such as `vX.Y.Z`.

For the template product, users copy the generated `reponomics-dashboard` repository. That repository is not hand-maintained source. It is generated from `reponomics-dashboard-action` by a release workflow.

The core template release claim is:

```text
source commit S in reponomics-dashboard-action
  -> official template publication workflow W
  -> generated template payload digest D
  -> generated repository commit T in reponomics-dashboard
```

A user does not need to trust a hand-edited generated repository state. They can trace the generated template back to the source commit and release workflow that produced it.

## What We Claim

For an action release, Reponomics claims that the released action tag points to the source tree used by GitHub Actions when consuming repositories run the action. The action release is the source tree plus bundled runtime assets, dependency locks, action metadata, and managed documentation source shipped in this repository.

For a template release, Reponomics claims that the released generated template tree was built from a specific source commit in `reponomics-dashboard-action`, passed the declared release gates, and was published to `reponomics-dashboard` as generated output.

For compatibility, Reponomics claims only the template surfaces exercised by the compatibility gate or by an explicitly named ad hoc compatibility run. Other template/action pairs may work, but they are not part of the stated release-gate claim.

The template release claim is intentionally about identity and origin. It does not claim that the software has no bugs, that users cannot misconfigure their own repositories, or that every downstream dashboard artifact produced in a user's repository is globally attested by Reponomics.

## What Gets Attested

Supply-chain attestations should bind to the artifact being shipped, not merely to the source repository that produced it.

For the generated template, the attested subjects are deterministic release artifacts built from `dist/template`, including:

- a generated template archive such as `reponomics-dashboard-template-vX.Y.Z.tar.gz`;
- a canonical tree manifest such as `reponomics-dashboard-template-vX.Y.Z.tree.jsonl`;
- a checksum file such as `SHA256SUMS`.

The canonical tree manifest records the file paths, file modes, sizes, and SHA-256 hashes for the generated template payload. The generated template itself also contains `.reponomics/template-provenance.json`, which records the source commit, template version, action compatibility metadata, and payload digest.

The generated repository commit is checked against the same generated payload identity. In simple terms, "the generated repo commit contains digest D" means that recomputing the canonical digest over the files in that commit gives the same digest recorded in `.reponomics/template-provenance.json` and in the release artifact evidence.

## What A User Can Verify

A user or reviewer can inspect the generated template repository release and its provenance record. The important questions are:

1. Which generated repository commit am I looking at?
2. Which source repository commit generated it?
3. Which release workflow generated and published it?
4. What generated payload digest was recorded?
5. Does the generated tree match that digest?
6. Does the template declare the expected action compatibility contract?

The usual path is:

```text
reponomics-dashboard release or main branch
  -> generated commit T
  -> .reponomics/template-provenance.json
  -> source commit S and payload digest D
  -> source workflow run W
  -> workflow artifacts and attestations for the generated archive/tree manifest
```

After checking those links, the user knows that the generated template state they are reviewing is the one produced by the official Reponomics source workflow from the recorded source commit.

## What A User Does Not Learn

Provenance does not prove correctness, security, or suitability for a particular repository. It proves a narrower and more useful supply-chain property: identity and origin.

It also does not mean that generated dashboard artifacts produced later inside a user's copied repository are attested by Reponomics. Those artifacts are produced by the user's repository workflows, with that repository's secrets, permissions, artifact retention, and GitHub Pages settings.

## Why The Template Repository Is Generated

`reponomics-dashboard-action` is the source and build authority. It owns the runtime code, generator scripts, managed documentation source, validation tests, release workflows, and publication credentials.

`reponomics-dashboard` is the generated template product. It is what users copy. It is intentionally not a second development repository.

This split lets Reponomics prove that a user-facing template release was generated from a reviewed source commit, while keeping all development and release machinery in one source repository.
