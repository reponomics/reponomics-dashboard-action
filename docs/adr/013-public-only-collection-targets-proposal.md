## ADR 013: Proposal - Public-Only Repository Collection Targets

Date: 2026-05-30

### Status

Proposed

### Context

Collection currently supports both public and private repository targets.

This adds complexity to:

- credential and permission guidance,
- token scope explanations,
- feature expectations (for example, public-community-oriented signals).

Product direction discussion raised whether private-target collection is meaningful enough to justify that complexity, especially as the default user mental model is public-facing repository growth and traffic.

### Proposal

Treat collection targets as public-only in a future change.

Key behavior goals if adopted:

- private repositories are not collected,
- private repos discovered or configured by users are skipped with clear warnings,
- collection should not fail the entire run solely because a previously tracked repo became private.

### Rationale

- Reduces onboarding and permission-surface complexity.
- Better aligns collection semantics with public-facing growth/community analytics.
- Avoids user surprises from hard failures when repository visibility changes over time.

### Scope

This ADR is a proposal only. No runtime behavior change is part of this ADR itself.

Current implementation remains unchanged until an explicit adoption decision is made.
