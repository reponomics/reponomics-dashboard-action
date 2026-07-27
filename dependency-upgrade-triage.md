# Dependency Upgrade Triage Memo

## Inputs

- Directive: `dependency-upgrade-directive.md`
- Intake report: `dependency-intake-report.json`
- Remote inventory: open dependency-related PRs #218 through #226, excluding non-dependency content
- Baseline: `994bc2b84e79e98d26786a28a2aeb8d3ec6b8651`

## Summary

- Open dependency-related PRs reviewed: 9
- Dependency items reviewed: 10
- Major bumps: 2
- Automated PRs accepted: 8, with #223 and #226 adapted to the official release SHA
- Mixed-scope PR deferred as-is: #218; its dependency constraint was extracted
- Product-facing updates: #219, #220, #221's provenance metadata, and #224
- Repository-only updates: #218's NumPy constraint, #222, #223, #225, and #226

## Decisions

| PR | Decision | Safety and appropriateness | End-user impact | Template-product consideration |
| --- | --- | --- | --- | --- |
| [#218](https://github.com/reponomics/reponomics-dashboard-action/pull/218) | Defer PR; extract `numpy<2.5` | The cap prevents NumPy 2.5 stubs from conflicting with the Python 3.11 mypy target on newer CI interpreters. The PR remains changes-requested and inaccurately describes itself as documentation-only. | Development/type-check tooling only. | None. The constraint is not shipped in the action runtime or generated template. |
| [#219](https://github.com/reponomics/reponomics-dashboard-action/pull/219) | Accept | cffi 2.1.0 remains compatible with Python 3.11+, fixes platform/crash issues, and has no known advisory in the reviewed evidence. | Yes. It is installed from the action runtime lock through `cryptography`. | No template file change. Generated workflows consume the released action through the wrapper. |
| [#220](https://github.com/reponomics/reponomics-dashboard-action/pull/220) | Accept | charset-normalizer 3.4.9 repairs the 3.4.8 decode regression; 3.4.9 is not yanked and has no known advisory in the reviewed evidence. | Yes. It is installed from the action runtime lock through `requests`. | No template file change; validate template consumers against the candidate action. |
| [#221](https://github.com/reponomics/reponomics-dashboard-action/pull/221) | Accept | Manifest tarball provenance advances to 5.3.0, while the selected font bytes and hashes are unchanged. Local vendored-asset validation passes. | No visible or byte-level output change, although the manifests belong to the shipped product surface. | No template source change; generated dashboard output was rebuilt and verified. |
| [#222](https://github.com/reponomics/reponomics-dashboard-action/pull/222) | Accept with companion fixes | setup-node v7's breaking change is internal ESM migration. Used inputs remain supported, the Node 24 action runtime was already required, and JS gates pass. | Repository CI/promotional automation only. | None. No setup-node occurrence exists in template sources. |
| [#223](https://github.com/reponomics/reponomics-dashboard-action/pull/223) | Accept intent; use release SHA | The proposed unreleased snapshot has the same scanner action definition as v2.3.8. Pinning the verified v2.3.8 release SHA makes the version comment truthful. | Repository security CI only. | None. The scanner workflow is maintainer-only. |
| [#224](https://github.com/reponomics/reponomics-dashboard-action/pull/224) | Accept with companion fixes | setup-python v7's ESM migration and removal of the unused `pip-install` input do not affect repository usage. Python 3.11 remains unchanged. | Yes. Root `action.yml` invokes setup-python for every consumer run. | Do not copy the pin into `template/`; the local wrapper continues to call `@v0`. Run consumer, boundary, and minimum-template compatibility gates before release. |
| [#225](https://github.com/reponomics/reponomics-dashboard-action/pull/225) | Accept | Minor provenance improvements; full SHA matches v4.2.0. | Release attestations only, not action behavior or artifact content. | The template release pipeline uses the action, but generated template files do not. |
| [#226](https://github.com/reponomics/reponomics-dashboard-action/pull/226) | Accept intent; use release SHA | Same reasoning as #223 for the reporter subaction. | Repository security reporting only. | None. |

## Buckets

### 1) Safe and integrated

- #219 cffi 2.1.0
- #220 charset-normalizer 3.4.9
- #221 Inter and JetBrains Mono manifest provenance 5.3.0
- #222 setup-node 7.0.0 plus test/comment synchronization
- #224 setup-python 7.0.0 plus test/comment synchronization
- #225 actions/attest 4.2.0
- #223 and #226 as release-SHA OSV v2.3.8 repins
- The `numpy<2.5` constraint extracted from #218

### 2) Needs remote review

- setup-python v7 executes inside the shipped composite action; local boundary and compatibility gates pass, while final runner-level evidence must come from combined-branch CI.
- actions/attest executes only on release/template-release paths.
- OSV scanner/reporter execute only on push, schedule, or manual dispatch; the upstream action definitions invoke a container tag rather than a digest.

### 3) Deferred as submitted

- PR #218 should not be merged as-is while it remains changes-requested and mixes a dependency constraint into a documentation PR whose body says no build behavior changes.

## Recommended staged sequence

1. Restore compatibility with fresh development tooling by accepting the behavior-preserving Ruff 0.16 syntax repair.
2. Apply the vendored manifest and GitHub Action upgrades, including companion comments and exact-SHA tests.
3. Regenerate the runtime lock with targeted `cffi==2.1.0` and `charset-normalizer==3.4.9` upgrades.
4. Extract the `numpy<2.5` development compatibility constraint from #218.
5. Run focused runtime, metadata, vendored, generated-product, and compatibility checks.
6. Run the complete `make prebeta-check` gate.
7. Push the combined branch and require protected CI before merging; optionally dispatch the OSV and promotional-guide workflows on the branch.

## Notable risks

- setup-python v7 changes an end-user action dependency even though its interface remains compatible.
- charset-normalizer can affect response-decoding heuristics; focused and full application tests pass.
- OSV's upstream action repository pin does not content-address its referenced container image.
- The open PRs' earlier green checks predated Ruff 0.16.0; only the refreshed combined validation is representative.

## Missing evidence

- Combined-branch GitHub-hosted runner results are unavailable until the branch is pushed.
- Release attestation behavior is not executed locally.
- OSV scanner/reporter workflow execution is not part of PR-triggered CI.

## Maintainer decision

- Integrated scope: approved locally.
- Merge condition: protected remote CI passes on the combined branch.
- Template release: no direct `template/` or `template-contract.yml` edit is needed; ordinary action release and later template acceptance automation remain authoritative.
