# ADR 010: Dashboard Scenario Corpus And Design Labs

Date: 2026-05-29

## Status

Proposed

## Context

Reponomics has more than one generated dashboard surface. The hosted HTML dashboard is the richest surface for users who can publish or download a Pages artifact. The generated README dashboard is also a product surface, especially for users who can collect retained Reponomics data but cannot or do not want to host a GitHub Pages dashboard.

Both surfaces are built from the same retained data families: traffic, referrers, paths, repository metrics, collection quality, and derived dashboard summaries. A dense portfolio, traffic spike, long label, empty state, sparse history, or collection gap is therefore not a "markdown scenario" or an "HTML scenario". It is a product scenario.

README-compatible design harnesses are useful workbenches for exploring that surface. They can render deterministic scenarios such as dense portfolios, traffic spikes, long labels, empty data, and baseline fixture data. Those scenarios are not inherently private or experimental. They describe real dashboard states that every relevant generated surface should handle reliably.

The experimental designs built on top of those scenarios are different. A new composition, chart type, SVG layout, or dashboard narrative pattern may be valuable design research without yet being a product commitment. The project therefore needs a clear policy that treats scenarios as shared product test assets while still allowing local design labs to explore surface-specific ideas.

There is also a reproducibility question. A locally generated harness dashboard is not automatically evidence that the actual action or template will generate the same HTML or README dashboard. That claim is only justified when the same production renderer path, deterministic inputs, and stable output normalization are used.

## Decision Drivers

- The HTML dashboard and README dashboard should both be treated as generated product surfaces.
- Scenario data is useful shared public test infrastructure when it is synthetic, anonymized, or otherwise safe to commit.
- Design experiments should not be mistaken for product direction or release evidence before promotion.
- Generated `.tmp/` output is disposable and should not become the source of truth.
- Evidence claims must distinguish data-scenario coverage, surface-specific medium compatibility, production behavior, and byte-for-byte reproducibility.
- Future agents need a workflow that is clear enough to follow without knowing the history of this branch.

## Decision

Adopt a shared scenario corpus with two operating lanes:

1. A production snapshot lane for production dashboard surfaces.
2. A local design lab lane for exploratory surface-specific work.

Both lanes consume the same dashboard data contract, but they make different claims.

### Production Snapshot Lane

Scenario fixtures are product test assets. They should be promoted into a shared scenario corpus when they are safe, deterministic, and representative of supported data states.

Shared production scenarios should cover at least:

- baseline fixture data from the existing collection-quality preview
- dense multi-repository portfolio data
- single-repository traffic spikes
- long owner/repository labels
- empty or not-yet-collected dashboards
- collection gaps and partial failures
- sparse data where charts, tables, and summaries must degrade cleanly

These scenarios should feed durable production snapshots for generated dashboard surfaces, including the hosted HTML dashboard and the generated README dashboard. Shared production snapshot tests should verify:

- canonical CSV and derived dashboard data load correctly
- both production renderers can consume the scenario data
- empty, sparse, dense, and anomalous data states render without broken output
- production privacy/disclosure rules are preserved for public and private repository modes
- generated outputs use stable relative paths for the template/repository layout

README-specific tests should also verify:

- the generated Markdown has no JavaScript
- the generated Markdown does not inline SVG
- every referenced SVG asset exists
- light and dark SVG variants remain paired where required

HTML-specific tests should also verify the generated artifact invariants described in ADR 008, including local asset loading, CSP, privacy boundaries, export integrity, and plain-mode publication behavior.

Production snapshot tests may use structural assertions, targeted snapshots, or normalized golden files. They should avoid brittle visual snapshots unless the output is already produced by the production renderer and the snapshot has clear release value.

### Repository Ownership

Renderer scenario snapshots belong in `reponomics-dashboard-action` because the action repository owns the runtime scripts that collect, load, derive, and render the README and HTML dashboard outputs. A snapshot test in this repository can run the same production code path that an end-user workflow runs when it uses `reponomics/reponomics-dashboard-action@REF`.

`reponomics-dashboard-dev` and the generated `reponomics-dashboard` template should not duplicate the renderer golden files. Their tests should prove the consumer wiring: workflow inputs, default configuration, required secrets, permissions, generated template cleanliness, and compatibility with the action version the template points at. The template repository is still user-facing, but it is not the source of truth for renderer behavior.

The end-user translation is therefore:

- a user repository created from the template runs this action through its workflows;
- renderer changes reach users when their workflow reference points at a release, major-version ref, or commit that contains those changes;
- these snapshots prove what that action revision renders for representative data states;
- template/dev tests prove that the generated consumer repository invokes the action correctly.

### Local Design Lab Lane

Design labs may use the same shared scenarios, plus branch-local exploratory scenarios, to test new dashboard ideas quickly. A design lab may be specific to the README surface, the HTML surface, or another future generated surface.

The README-compatible design lab may render:

- exploratory chart families
- alternate SVG layouts
- alternate dashboard ordering and narrative structure
- alternate README-compatible dashboard compositions
- SMIL animation experiments
- proposed mobile-first variants

Design labs write generated output under `.tmp/` or another ignored scratch directory. Those outputs are not release artifacts, are not source of truth, and should not be committed except as deliberately documented examples or promoted test fixtures.

Local branch or private-remote work is an implementation convenience, not a production boundary. A design becomes product work only when it is promoted into the production snapshot lane or the production renderer path.

### Promotion Path

A dashboard idea moves from experiment to product through this path:

1. Prove the idea against representative scenario data in the design lab.
2. If the scenario exposes a product-relevant data state, promote that scenario into the shared scenario corpus.
3. Move rendering logic into the appropriate production renderer or a shared module used by that renderer.
4. Add or update scenario tests that invoke the production generation path, not only the design harness.
5. Validate the relevant surface contract, such as GitHub README compatibility for Markdown or generated-artifact security for HTML.
6. Mark the component or pattern as current only after production-path tests pass.

Production renderers are the authority for generated template output. A design harness can preview candidate directions, but copied or parallel rendering logic in a harness cannot prove one-for-one production behavior.

## Reproducibility And Confidence Levels

The project will describe dashboard-surface evidence using four confidence levels.

### Level 0: Lab Sketch

The output is generated by a design lab from dashboard-shaped data. It may use exploratory components, temporary compositions, or branch-local scenarios.

Claim: the idea is feasible enough to inspect.

Not claimed: surface contract completeness, production behavior, or byte-for-byte reproducibility.

### Level 1: Surface Contract Compatible

The output passes the relevant medium constraints. For README output, that means no JavaScript, no inline SVG in Markdown, external SVG references resolve, light/dark variants are coherent, and the layout handles the scenario data without broken links or missing assets. For HTML output, that means the generated artifact satisfies the local asset, CSP, privacy, and export integrity rules expected for that surface.

Claim: the idea is compatible with the target surface and scenario data contract.

Not claimed: the actual action/template will generate identical output.

### Level 2: Production Path Equivalent

The output is generated by the same runtime renderer, asset helpers, and data loaders that the action uses during the relevant production mode, or by shared modules imported by that renderer.

Claim: the behavior is representative of the generated product.

Not claimed: byte-for-byte reproducibility across environments unless the test also controls timestamps, paths, dependency versions, ordering, and formatting.

### Level 3: Byte-Reproducible Release Evidence

The output is generated from fixed scenario inputs, a known source commit, a known command, stable dependency versions, deterministic ordering, stable asset names, fixed timestamps where applicable, and a normalization policy for any allowed environment-specific values.

Claim: the generated dashboard output and referenced assets are reproducible one for one for the tested scenario and command.

This is the confidence level required before making a strict claim that the template or action will reproduce a generated dashboard exactly.

## Generated Output Policy

Commit these kinds of files when they are safe and useful:

- scenario source fixtures
- scenario manifests
- validators
- tests
- small expected snapshots or golden outputs generated by a production path
- documentation explaining scenario intent and coverage

Do not commit these by default:

- `.tmp/` output
- ad hoc design renders
- exploratory SVGs that are not shipped assets or intentional fixtures
- files labeled temporary unless they are promoted and renamed
- generated dashboards that contain real user data

Generated SVG assets may be committed only when they are either shipped product assets or intentional test fixtures with clear provenance. Otherwise they should be regenerated from committed sources during tests or local previews.

## Relationship To ADR 008

ADR 008 defines a broader assurance model across the action repository, template source, template consumer, and generated dashboard artifacts. This ADR specializes that model for the shared dashboard scenarios used to test and design generated surfaces, including both HTML and README output.

The important inheritance rule is the same: do not claim that source work automatically propagates to a generated template or user repository. Prove the generated output through the path users actually run.

## Consequences

The project can keep using the markdown dashboard harness for fast local README design iteration without treating every experiment as public product direction.

Scenario work becomes more valuable because it can graduate into public integration coverage for both HTML and README output. Agents can add scenarios to describe dashboard states without needing to settle the final design at the same time.

One-for-one reproduction claims become narrower but stronger. A design harness render is useful evidence, but exact reproduction requires the relevant production renderer path and deterministic test controls.

The cost is that successful experiments need a promotion step. Rendering logic should not live permanently in a parallel harness if the project wants to claim that the generated template will emit the same dashboard.

## Initial Implementation Plan

1. Extract public-safe scenarios from the harness into a committed shared scenario corpus, or document the current scenario builder as an interim corpus until file-based fixtures are introduced.
2. Add scenario tests that run the production HTML and README generation paths for every public scenario.
3. Add shared scenario validators for canonical CSV loading, derived data integrity, scenario manifest completeness, and deterministic ordering.
4. Add README-output validators for JavaScript absence, no inline SVG in Markdown, external SVG existence, light/dark pairing, and stable relative paths.
5. Keep local design harnesses pointed at the same scenario corpus and writing only ignored scratch output.
6. Promote candidate components by moving rendering code into the appropriate production renderer or into shared modules imported by production renderers.
7. Replace temporary validation scripts with real tests or documented developer scripts before public promotion.

## Open Questions

- Should public scenarios live as explicit CSV fixture directories, Python scenario builders, or both?
- Which HTML and README dashboard outputs deserve normalized golden files instead of structural assertions?
- Which composition experiments should remain strictly branch-local until product semantics are resolved?
- Which scenario set should become release-blocking before v1?
