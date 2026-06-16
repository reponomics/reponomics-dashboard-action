# ADR 020: Action-Side Minimum Compatible Template Gate

Date: 2026-06-16

## Status

Accepted

## Context

Reponomics publishes two related products with asymmetric upgrade behavior:

- the generated dashboard template, which users copy once and may keep unchanged;
- the GitHub Action, which copied repositories normally consume through the floating compatible ref such as `v0`.

The previous `template-contract.yml` shape recorded `template_version` and `min_action_version`. That made the relationship look like the template had to define a minimum action range. That is the wrong emphasis for this product.

Generated templates are published with the current compatible action channel. Users are not expected to copy a newly released template and intentionally pin its workflows to an older action version. Therefore "minimum action version" is not a meaningful compatibility promise; at template release time the relevant action answer is simply "the current released compatible action."

The meaningful long-lived compatibility claim points in the other direction. A user who copied an older template may keep that template while the floating action channel continues to move. A new action release must therefore prove that it still works with protected published template versions that users may already have copied.

The old contract was inverted. The explicit field is `minimum_compatible_template_version`: as action versions increase, action release gates must remember the oldest published template version that still has to pass.

## Decision

Keep one contract file, `template-contract.yml`, but make its compatibility direction explicit.

The contract records:

- the generated template version being published;
- the action repository and default compatible action ref used by generated workflows;
- the managed-docs namespace copied into generated repositories;
- the action-side `minimum_compatible_template_version` that action releases must continue to support;
- the protected published template refs used by the action release compatibility gate.

Do not keep `min_action_version` as a compatibility contract field. If template publication needs evidence that the current `v0` action channel was already released and tested, that evidence belongs in release provenance or release workflow output, not in a standing compatibility range.

The action release gate must materialize both:

- the current/latest generated template for the release candidate; and
- the minimum compatible template version recorded by `minimum_compatible_template_version`.

Both must pass against the candidate action. The current template proves the action still works with the newest generated workflow and setup surface. The minimum compatible template version proves the action still works with the oldest copied-template surface still covered by the action release. Additional protected template refs may be tested when the interval contains known compatibility-relevant releases.

The gate should not vendor whole generated template trees into the source repository as the default mechanism. If the minimum compatible template version is intentionally moved forward, the `minimum_compatible_template_version` change and release notes must make that compatibility reset explicit in the same review.

```text
candidate action release
  must pass current-template checks
  and must pass minimum-compatible-template checks
```

Generated template documentation should also include a low-friction notice for users whose organization requires SHA-pinned Actions. The default template should keep using the compatible floating action ref, but the notice should point such users to the latest released action tag/SHA available at template publication time and warn that SHA-pinned users own their own update cadence.

## Consequences

- Action releases get a real backwards-compatibility gate for copied template users.
- Template releases are not burdened with proving compatibility against older action versions that users are not expected to choose.
- The single contract avoids manifest proliferation while still distinguishing template identity from action-side compatibility.
- The phrase `minimum_compatible_template_version` points maintainers toward the real release obligation: keep new actions working with old protected templates.
- The release gate treats current-template compatibility and minimum-compatible-template compatibility as separate required checks.
- SHA-pinning remains an opt-in organizational-policy path, not the default generated workflow behavior.
- A future compatibility reset becomes auditable because it must change the contract's minimum compatible template version instead of silently passing only against the current template.
