# Dependency Migration Report

## PR Summary

- What changed: combined the safe portions of open dependency-related PRs #218–#226, upgraded runtime-lock dependencies and repository actions, refreshed vendored font provenance, added required compatibility constraints/tests/comments, and repaired fresh Ruff 0.16 compatibility.
- Why: consolidate nine blocked or mixed-scope dependency PRs into one reviewable branch with accurate product-boundary handling and current validation.
- How validated: focused dependency/product gates and the complete `make prebeta-check` suite passed.
- Risks and notes: setup-python v7 is end-user-facing through `action.yml`; OSV and attestation execution remain remote-only surfaces; no direct template source update is required.
- Rollback: revert the dependency commits or the eventual combined squash commit, restore the baseline runtime lock and action SHAs, and reinstall with the repository Makefile.

## Baseline

- Start commit: `994bc2b84e79e98d26786a28a2aeb8d3ec6b8651`
- Integration head before report commit: `8e459be767ae00d87cce51f1835ee4ffd60d46c4`
- Branch: `fix-deps-07-27`
- Node: 24.18.0
- npm: 11.16.0
- Python: 3.11.14 in `venv`
- pip: 26.1.2
- Resolver: pip-tools 7.6.0
- Fresh lint/type tooling: Ruff 0.16.0, mypy 2.3.0

## Changes applied

### Python

- Added development constraint `numpy<2.5`, extracted from changes-requested PR #218 without taking its unrelated Windows documentation.
- Regenerated `requirements-runtime.txt` with targeted `cffi==2.1.0` and `charset-normalizer==3.4.9` upgrades.
- Confirmed the targeted regeneration changed only those two package versions; other runtime pins remained unchanged.
- Applied a behavior-preserving Ruff 0.16 `ISC004` compatibility rewrite in `scripts/build_dashboard_guide.py`.

### GitHub Actions

- `actions/setup-node`: v6.4.0 to v7.0.0 at full SHA `820762786026740c76f36085b0efc47a31fe5020`.
- `actions/setup-python`: v6.3.0 to v7.0.0 at full SHA `5fda3b95a4ea91299a34e894583c3862153e4b97`.
- `actions/attest`: v4.1.1 to v4.2.0 at full SHA `f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6`.
- OSV scanner and reporter: both pinned to verified v2.3.8 release SHA `9a498708959aeaef5ef730655706c5a1df1edbc2` rather than the PRs' misleading unreleased snapshot.
- Updated the setup-node/setup-python version comments and exact-SHA assertions that Dependabot omitted.
- Preserved minimal top-level workflow permissions and existing job-level permission boundaries.

### Vendored assets

- Advanced Inter and JetBrains Mono manifest provenance from 5.2.8 to 5.3.0.
- Confirmed the selected WOFF2 bytes and their recorded SHA-256 values are unchanged.

### Template product

- No source under `template/` changed.
- `template-contract.yml` remains unchanged because dependency integration is not an action-release acceptance event.
- Rebuilt and verified generated template/demo output; validated consumers against current template 0.20.1 and minimum compatible template 0.16.0.

## Validation results

| Gate | Result |
| --- | --- |
| `git diff origin/main..HEAD --check` | Passed |
| `make lint` | Passed with Ruff 0.16.0 |
| `make type-check` | Passed with mypy 2.3.0 |
| `make validate-action` / `make validate-workflows` | Passed |
| Runtime lock regeneration comparison and hash-required install | Passed |
| `make audit-runtime-lock` | Passed; no known vulnerabilities |
| Installed-environment `pip-audit` | Passed; no known vulnerabilities |
| `make validate-vendored-assets` | Passed |
| Focused action metadata and vendored updater tests | 26 passed |
| Python unit suite | 496 passed |
| Python coverage | 90.77%, threshold 70% |
| JavaScript tests | 21 passed |
| JavaScript coverage and smoke | Passed |
| Dashboard scenario snapshots | 19 passed |
| Generated template/demo build and verification | Passed |
| Template release smoke and packaging | Passed |
| Template consumer and composite-boundary e2e | Passed |
| Public accepted-action e2e | Passed |
| Current/minimum-template compatibility | Passed for 0.20.1 and 0.16.0 |
| Template/demo publication dry runs | Passed; no push performed |
| `make prebeta-check` | Passed |

## Major migration notes

### setup-node v7

- Upstream guide: https://github.com/actions/setup-node/releases/tag/v7.0.0
- Breaking declaration: internal CommonJS-to-ESM migration.
- Used interface changes: none; repository inputs remain supported.
- Runner compatibility: both the previous and target action versions use Node 24, so the runner floor is not newly raised.
- Product behavior: repository CI/promotional automation only.

### setup-python v7

- Upstream guide: https://github.com/actions/setup-python/releases/tag/v7.0.0
- Breaking declaration: internal ESM migration and removal of the unused `pip-install` input.
- Used interface changes: none; `python-version` and cache-related usage remain supported.
- Runner compatibility: both previous and target versions use Node 24.
- Product behavior: end-user-facing because the composite `action.yml` invokes setup-python; local consumer and compatibility gates pass.

## Incidents and failures encountered

### Fresh Ruff resolution

- Symptom: the July 27 scheduled baseline CI failed Python 3.11, 3.12, and 3.13 after resolving Ruff 0.16.0, while the stale local venv passed with Ruff 0.15.20.
- Root cause: Ruff 0.16.0 enables `ISC004` for unparenthesized implicit string concatenation inside collections.
- Fix: refreshed `venv` through the Makefile and mechanically parenthesized 21 affected string expressions without changing values.
- Follow-up: no Ruff upper bound is needed; the repository now passes the current rule.

### Incomplete Dependabot companion edits

- Symptom: #222 and #224 failed repeated CI assertions even though the setup actions provisioned runtimes successfully.
- Root cause: Dependabot updated workflow SHAs but not hard-coded SHA tests or separate version comments.
- Fix: updated both assertions and both comments.

### OSV version-comment mismatch

- Symptom: #223 and #226 proposed a post-release `main` commit while retaining `# v2.3.8`.
- Root cause: existing pins also followed an unversioned post-release snapshot, so Dependabot advanced that digest rather than the release tag.
- Fix: pinned both subactions to the verified official v2.3.8 release SHA, whose action definitions are byte-identical to the proposed snapshot.
- Follow-up: upstream still references its scanner container by tag, not digest.

## Rollback instructions

### Code rollback

- Before merge: reset the branch by reverting the local commits in reverse order; do not alter `main`.
- After squash merge: `git revert <combined-merge-commit>`.
- After preserving individual commits: revert from the newest dependency/report commit back through `0aebcaf`.

### Dependency rollback

- Restore `pyproject.toml`, `requirements-runtime.txt`, action/workflow SHAs, tests/comments, and vendored manifests from baseline `994bc2b84e79e98d26786a28a2aeb8d3ec6b8651`.
- Run `make install`, `make validate-runtime-lock`, and the focused metadata/vendored checks.

### Release rollback

- No deployment or remote publication occurred in this work.
- If incompatibility is discovered only after release, move the stable `v0` channel back to the previous release and publish a corrective patch before advancing it again.

## Remaining remote checks

- Push `fix-deps-07-27` and require all protected branch checks.
- Optionally dispatch `osv-scanner.yml` and `promotional-dashboard-guide.yml` against the branch.
- Do not run release attestation merely as a smoke test unless creating external provenance records is intended.
