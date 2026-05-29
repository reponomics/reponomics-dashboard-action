# ADR 008: Template And Generated Output Assurance

Date: 2026-05-26

## Status

Proposed

## Context

Reponomics is not experienced by users as a single repository. The action repository contains the runtime, renderer, composite action wrapper, supply-chain checks, vendored browser assets, and most executable tests. The dashboard development repository is the product-development surface for the template experience. The template repository is the first user-facing repository most users interact with. A user-created dashboard repository is then generated from that template and runs the action to produce retained workflow artifacts, README output, GitHub Pages output, and private plain dashboard artifacts.

This creates an assurance gap. Hardening the action repository improves the runtime and renderer, but it does not by itself prove that the template repository has the correct workflows, permissions, secrets guidance, pinning posture, privacy defaults, Pages configuration, Dependabot configuration, branch settings, documentation, or update path. Hardening the dashboard development repository improves the source of the template, but it does not by itself prove that the published template repository is current, that a fresh user-created repository behaves as expected, or that the generated dashboard artifact satisfies the browser-security constraints users rely on.

The generated dashboard is also a product surface in its own right. It is a static browser application delivered through GitHub Pages artifacts for encrypted modes and workflow artifacts for private plain mode. It may handle private decrypted metrics and encrypted CSV export bundles in the browser. Even though it has few dependencies, it deserves security and quality validation against the generated artifact, not only against the Python renderer source.

The current action repository has substantial hardening in place: pinned imported GitHub Actions, vendored asset manifests and validation, hash-locked runtime Python dependencies, CSP generation, generated-dashboard tests, CodeQL, Scorecard, OSV, SBOM/provenance workflow, release attestations, and immutable releases. The unresolved question is how these controls should propagate across the development repository, template repository, user-created dashboard repositories, and generated dashboard outputs.

The word "propagate" is itself risky. Some safeguards can be copied into generated repositories, such as workflow permissions, Dependabot configuration, pinned action refs, documentation, and default privacy settings. Other safeguards cannot literally be inherited, because they belong to the source repository or release process that produced the template. For example, CodeQL, Scorecard, branch protections, release attestations, and source SBOMs in the dashboard development repository do not automatically become equivalent claims about a generated template repository. For those controls, the best available evidence is not inheritance but regeneration evidence: a recorded workflow generated the template from a known source commit, compared the output, tested a clean consumer instance, and attached or published enough metadata for reviewers to trace the relationship.

This means the project should avoid claiming that a generated template "inherits all hardening" from the development repository. A more accurate claim is that the generated template is reproducibly or verifiably produced from a hardened source process, then tested as the user-facing artifact. The distinction matters because it sets a realistic bar: prove the output, do not merely assert that source-repository controls flow through it.

## Decision Drivers

- Users primarily encounter the product through the template repository, not through the action repository.
- The action repository should remain the authoritative implementation for runtime behavior and generated dashboard rendering.
- The template repository should remain small, understandable, and close to what a user actually owns after setup.
- Generated dashboard output should be validated as a browser artifact because security properties such as CSP, local-only assets, export integrity checks, and no plaintext persistence are properties of the emitted HTML/JS/assets.
- Provenance claims should distinguish source provenance, template provenance, generated repository provenance, and generated dashboard artifact provenance.
- Release and update automation should not create a false sense of security by proving only an intermediate source repository while leaving the user-facing template stale.
- Assurance claims should be explicit about which controls are embedded in generated output, which controls are verified after generation, and which controls remain properties of the source repository or release process.
- The process should be lightweight enough to run frequently before v1, but structured enough to become a release gate later.

## Proposed Decision

Adopt a product-surface assurance model with four separately validated layers:

1. Action source assurance: the action repository proves runtime, renderer, vendored assets, dependency lock, imported action pins, tests, SBOMs, release source archive attestations, and release immutability.
2. Template source assurance: the dashboard development repository proves that the published template repository can be generated from reviewed source, with expected workflows, permissions, documentation, default config, Dependabot configuration, and update guidance.
3. Template consumer assurance: CI creates or materializes a fresh template-derived repository fixture and runs the same workflows a user would run, using mocked GitHub API responses where live external calls are inappropriate.
4. Generated artifact assurance: CI validates the actual dashboard output as browser-delivered product, including CSP, script/style sources, vendored asset inclusion, dangerous DOM sink policy, export integrity checks, localStorage/sessionStorage boundaries, plaintext handling, and offline artifact download paths.

For the action repository specifically, add a future `validate-dashboard-security` gate that renders representative encrypted and private plain dashboard outputs and checks generated-output invariants. This should be a repo-native validator or focused pytest suite first, not a generic website scanner. Generic scanners can be added later only if they provide signal for static generated artifacts without excessive false positives.

Action-only CI remains valuable even after the template-consumer release gate exists. Its role is the fast source-level gate for ordinary pull requests: it localizes failures to the action repository, proves renderer/runtime behavior before a change reaches the slower template path, keeps dependency and supply-chain checks close to the code they protect, and gives maintainers useful evidence for non-RC PRs that do not claim a releasable product state. For a release candidate, action-only CI is necessary but not sufficient; the RC also needs the template-source, template-consumer, and generated-artifact gates before the project can say the user-facing path is shippable.

For the template/development repository relationship, introduce a release-candidate promotion flow. Before a template release or major action release is treated as ready for users, automation should generate the template repository from the development repository, instantiate a clean template-derived fixture, run collect/publish/rotate-key or equivalent fixture workflows, validate generated output, and fail on drift. Before v1, it is acceptable to run this for every release candidate even if that is stricter than the eventual release policy.

After the full gate exists and has enough history to be trusted, the project can add risk-based release classes that allow lighter validation for changes that cannot plausibly affect generated repositories or dashboard behavior, such as a typo-only edit in user-facing documentation. That optimization should be a later policy, not the starting assumption. Any change touching privacy modes, encryption, artifact storage, workflow permissions, action inputs, template generation, renderer code, scenario data contracts, README disclosure rules, Pages publication, dependency/runtime behavior, or generated-dashboard assets should continue to require the full release-gate path.

This flow should explicitly classify controls into three buckets:

- Embedded controls: files or settings that are actually present in the generated template, such as workflows, permissions, action refs, Dependabot configuration, issue templates, documentation, default privacy mode, and recommended secrets names.
- Verified output controls: properties tested after generation, such as no generated drift, successful fixture lifecycle, correct dashboard artifact behavior, CSP, local asset loading, and artifact/privacy boundaries.
- Source/process controls: properties that remain attached to the development repository or action release process, such as source CI, release attestations, immutable releases, branch protection, CodeQL, Scorecard, SBOMs, and maintainer review.

The goal is not to make every source/process control physically present in the generated template. The goal is to make clear which controls are embedded, which are verified on the output, and which can only be traced through provenance metadata.

## Recommended Release Gate Shape

The long-term release gate should answer these questions before publishing or recommending a release:

- Does the action release pass its own CI, security, vendored asset, dependency lock, SBOM, and provenance checks?
- Does the dashboard development repository generate the exact template repository contents expected for this release?
- Does the generated template repository have the expected workflows, permissions, secrets names, action refs, Dependabot configuration, documentation, and privacy defaults?
- Can a fresh template-derived repository run the documented setup/collect/publish lifecycle without private shortcuts?
- Does encrypted publish output include only expected same-origin assets, strict CSP, encrypted payload metadata, export manifest metadata, and no committed private data?
- Does private plain publish output remain artifact-only and avoid Pages publication?
- Do README/dashboard outputs match expected disclosure rules for public/private repositories, including the rule that public repositories cannot generate the README dashboard?
- Are release notes, update notices, and version compatibility metadata consistent across action, dashboard development, and template surfaces?
- Can provenance documentation point a reviewer from a user-visible template commit to the action ref it consumes and to the generated dashboard artifact properties that were tested?

The release gate should be matrix-shaped, but constrained to valid product states rather than a full Cartesian product. The required minimum is coverage across every supported template version, every release-critical scenario family, and every supported privacy mode, with at least one end-to-end consumer run for each privacy mode: `strong`, `casual`, and `plain`. Some combinations are invalid by design and should be tested as rejections, not rendered snapshots. For example, public repositories cannot use `plain` privacy mode and cannot generate the README dashboard, so README dashboard snapshots are a private-repository surface rather than a public/private Cartesian axis.

The matrix can pair valid axes deliberately instead of multiplying all of them, for example by running all scenarios against the current template in the default encrypted private-repository README configuration, one smoke scenario against each supported template version, and targeted privacy-mode runs that prove `strong` secret enforcement and encrypted artifact behavior, `casual` weak-secret allowance with encrypted artifact behavior, and `plain` private-only non-Pages artifact behavior.

Full Cartesian expansion is reserved for high-risk changes: privacy-mode changes, encryption or artifact-format changes, template workflow rewrites, Pages publication changes, generated-dashboard payload changes, README disclosure-rule changes, or release candidates where previous matrix failures show that the axes are interacting unexpectedly.

For non-RC pull requests, the action-only CI suite can be the primary required evidence when the change is confined to action-owned runtime, renderer, test, or documentation behavior and does not require a template compatibility claim. That does not make the action-only jobs throwaway checks; it makes them the inner loop that catches most defects before the project spends time on slower cross-repository promotion.

## Generated Dashboard Security Invariants

The generated dashboard validator should eventually check at least:

- CSP meta tag exists early in `head`.
- CSP avoids `unsafe-inline`, `unsafe-eval`, wildcard script/style sources, and unexpected remote origins.
- Published dashboard references the same-origin vendored `assets/chart.umd.min.js` and no remote scripts.
- Inline scripts and styles are covered by generated CSP hashes.
- No inline event handler attributes are emitted.
- No `document.write`, `eval`, `new Function`, or string-based timers are present.
- `innerHTML` usage is either absent from generated output or covered by a narrow allowlist proving all dynamic content reaches it through escaping or trusted constants.
- Browser storage is limited to expected keys such as theme preference and unlock throttling metadata.
- Decrypted dashboard data and decrypted export bytes are not written to `localStorage`, `sessionStorage`, IndexedDB, URL fragments, or committed files.
- Export asset paths are content-addressed and constrained to expected local asset patterns.
- Export download verifies ciphertext digest and plaintext ZIP digest before handing bytes to the user.
- Plain mode refuses public repositories and does not publish plaintext GitHub Pages output.
- Offline artifact instructions remain accurate for encrypted Pages artifacts and private plain dashboard artifacts.

Privacy-mode coverage is mission-critical and should not be inferred from renderer snapshots alone. At least one template-consumer release-gate run must prove each mode through the user-shaped workflow path: `strong` rejects weak secrets and emits encrypted retained/dashboard artifacts when configured with a high-entropy secret; `casual` accepts a low-entropy non-empty secret while still emitting encrypted retained/dashboard artifacts; and `plain` is rejected for public repositories, avoids Pages publication, and uploads the plain HTML dashboard only as the private workflow artifact path.

## Provenance Model

The project should avoid a single broad provenance claim. Instead, provenance should be layered:

- Action release provenance: evidence for the source tree that GitHub Actions fetches when a consumer uses the action ref.
- Vendored asset provenance: evidence that browser assets match pinned npm package tarballs and recorded hashes.
- Runtime dependency provenance: evidence that Python runtime dependencies are hash-locked and installed in hash-required mode.
- Template provenance: evidence that the published template repository was generated from the dashboard development repository by a known workflow.
- Template consumer provenance: evidence that a clean template-derived repository was generated and tested against the action release.
- Dashboard artifact assurance: evidence that representative generated HTML/assets satisfy browser-security and privacy invariants.

For generated dashboard artifacts produced inside a user's own repository, the project can provide validation logic and documented expectations, but it should not claim global attestation over every user artifact. Those artifacts inherit the consuming repository's workflow identity, permissions, ref pinning, secrets, artifact retention, and Pages settings.

For generated template repositories, the project should similarly avoid claiming automatic inheritance of all development-repository controls. A template provenance record can say that a specific template commit was generated from a specific development commit by a specific workflow and validated by a specific test matrix. It should not imply that repository settings, branch protections, release signing, or code-scanning state were mechanically transferred unless those settings are explicitly configured and verified on the generated repository.

## Options Considered

### Option A: Treat Action Repository Hardening As Sufficient

Pros:

- Lowest process complexity.
- Keeps all assurance work in the repository that contains most code.

Cons:

- Does not prove the template repository is current or secure.
- Does not prove a fresh user-created repository works.
- Does not validate the generated browser artifact as a product surface.
- Produces weak answers for provenance questions about the user-facing template.

### Option B: Add Generated Dashboard Validation Only In The Action Repository

Pros:

- Directly improves assurance for the emitted web page.
- Low implementation cost because action tests already render fixture dashboards.
- Keeps renderer security invariants close to renderer code.

Cons:

- Still does not prove template repository propagation.
- Does not test the full user-facing setup path.
- Can miss workflow/permission/documentation drift in the template.

### Option C: Make The Template Repository The Primary Release Artifact

Pros:

- Centers the user-facing surface.
- Forces release checks to match how users start.

Cons:

- Risks duplicating runtime tests and hardening logic outside the action repository.
- Can obscure the action release as the real executable dependency.
- May make template updates heavier than necessary for action-only fixes.

### Option D: Layered Promotion From Action To Template To Generated Output

Pros:

- Matches the actual product topology.
- Allows each repository to own the checks it is best suited to run.
- Creates clear provenance boundaries and avoids overclaiming.
- Supports both action-only updates and template-impacting updates.

Cons:

- Requires coordination across repositories.
- Requires either a template fixture, generated repository fixture, or temporary repository workflow.
- Needs a policy for which releases require full template promotion versus action-only validation.

Recommended direction: Option D, with Option B implemented first as the lowest-risk near-term step in the action repository.

## Consequences

The project will need to describe assurance at the product level rather than only at the repository level. This should improve credibility for security-conscious reviewers, but it also requires careful wording so normal users are not presented with unnecessary complexity.

The action repository remains responsible for runtime and generated dashboard invariants. The dashboard development repository remains responsible for generating the template repository and proving the generated template is current. The template repository remains responsible for presenting a clean user-facing setup surface and may carry only minimal validation of its own if generated from the development repository.

Generated dashboard security tests should become release gates before v1. Template promotion tests can start as scheduled or manually triggered checks, then become required for releases that change workflow contracts, action inputs, privacy modes, generated dashboard structure, or setup documentation. Later, once the full gate is reliable, maintainers may define a lighter docs-only or metadata-only path, but that path should be explicit and conservative.

This decision introduces an additional assurance layer. That layer is justified because the template is the user's entry point, but it must be kept bounded. The project should not attempt to prove that every development-repository quality signal is recreated in every generated repository. Instead, it should prove the smaller and more useful claim that the generated template contains the intended embedded controls and that a clean template consumer produces secure expected output.

## Open Questions

- What is the exact repository name and ownership boundary for the dashboard development repository, and is it the only source of truth for the template repository?
- After the full release gate is established, which low-risk release classes, if any, can use a lighter validation path without weakening privacy or generated-output guarantees?
- Should template promotion update the template repository directly, open a pull request, or publish a signed/generated release artifact that maintainers manually promote?
- Should the generated template repository be tested as a local fixture, a temporary GitHub repository, or a persistent demo/test repository?
- Which provenance artifacts should be uploaded for template generation: generated diff, source commit, template commit, action ref, SBOM, artifact attestation, or all of these?
- Should user-facing template workflows recommend major-version action refs by default while documenting full-SHA pinning as the high-assurance option?
- Should the generated dashboard validator live in the action repository, the dashboard development repository, or both?
- How should failures in template promotion affect action releases when the action change is security-critical and users need the update quickly?

## Initial Implementation Plan

1. In the action repository, add `make validate-dashboard-security` with generated-output tests for CSP, local assets, dangerous browser APIs, storage boundaries, export integrity, and plain-mode publication rules.
2. In the dashboard development repository, add a template generation verification job that fails if generated template output differs from committed template output.
3. Add a template-consumer fixture or demo repository path that runs the documented collect/publish lifecycle with mocked GitHub API responses, including at least one end-to-end run for each supported privacy mode without requiring a full template-version/scenario/privacy Cartesian product.
4. Extend provenance documentation to include action, template, template-consumer, and generated-dashboard layers.
5. Decide before v1 which of these checks are release-blocking and which are scheduled advisory checks.
