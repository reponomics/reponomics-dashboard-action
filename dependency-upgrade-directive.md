# Dependency Upgrade Directive

## Request

> there are a number of open dependabot/deps-related PRs open on the remote origin - please go through them and for each one (a) determine if the update is safe and appropriate to perform; (b) does it affect the end user product at all or only the repository's CI/CD, (c) are there any other changes that must be considered for the template product if the upgrades are accepted. ideally, you can merge the PR branches and combine them into this local one, or copy the upgrades they recommend. selectively invoke skills from the @dependency-management plugin

## Mode

- [ ] intake-only
- [x] intake + execute

## Policy defaults

- Patch/minor upgrades: review and accept when supported by upstream and repository evidence
- Security fixes: accept when compatible
- Major upgrades: accept only after explicit breaking-change and migration review
- Runtime bumps (Node/Python): accept only when repository, action-runtime, and template compatibility are preserved

## Constraints

- Time window: current open dependency-related PRs as of 2026-07-27
- Freeze dates: none specified
- Must not change: unrelated product behavior or files outside dependency/migration follow-up scope
- Must change: every accepted upgrade's source-of-truth declarations, generated artifacts, and template copies where applicable
- Deployment constraints: published GitHub Action and template consumers must remain compatible

## Target focus

- Packages: all open Dependabot/dependency-related PRs on `origin`
- Subsystems affected: shipped action runtime, repository CI/CD, development tooling, and template product
- Hosting/runtime change: none unless an accepted PR requires it and the migration is demonstrably safe

## Acceptance criteria

- Every candidate has a documented accept/defer decision and risk basis
- End-user, repository-only, and template-product impact are classified separately
- All existing tests pass
- Lint/typecheck pass
- Build passes and checked-in distribution output is synchronized if applicable
- Relevant GitHub Actions workflows/checks are accounted for
- Rollback instructions and remaining follow-up work are documented
