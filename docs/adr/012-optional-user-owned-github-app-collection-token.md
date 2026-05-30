## ADR 012: Optional User-Owned GitHub App Token for Collection

Date: 2026-05-30

### Status

Proposed

### Context

`collect` currently assumes a user-supplied PAT for `collection-token` and validates/discovers repositories via user-token endpoints (`/user`, `/user/repos`).

Advanced users may prefer GitHub App installation tokens for tighter credential lifecycle (short-lived tokens minted at runtime) and more explicit repository installation boundaries.

Reponomics should preserve its ownership model: users own their repositories, secrets, and data. This feature must not introduce a Reponomics-operated shared app.

### Decision

Add an advanced, opt-in collection path:

- New action input: `use-github-app` (default `false`).
- When enabled, `collect` interprets `collection-token` as a user-owned GitHub App installation token.
- Token validation switches from `/user` to `/installation/repositories`.
- Repository discovery switches from `/user/repos` to `/installation/repositories`.
- Eligibility filtering for this path accepts installation repositories with pull-only repository permission metadata.

Template workflows should mint the installation token in the caller repository (using caller-owned app credentials), then pass that token into the action for the collection run.

### Rationale

- Keeps the default PAT onboarding unchanged.
- Keeps action changes small and local to collection auth/discovery logic.
- Avoids running a central Reponomics app, preserving user control and trust boundaries.
- Supports GitHub’s installation-token endpoint model for repository traffic APIs.

### Consequences

- Advanced users get a best-practice credential path without changing default onboarding.
- Template/setup docs and workflow validation need a second credential path.
- Collection remains single-credential per run; multi-owner coverage still depends on app installation scope or broader PAT fallback choices.
