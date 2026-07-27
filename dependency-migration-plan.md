# Dependency Migration Plan

## Scope

- Ecosystems: Python, GitHub Actions, and vendored npm assets
- Upgrade policy: accept evidence-supported patch/minor updates and targeted majors whose used interfaces remain compatible
- Inputs used:
  - `dependency-upgrade-directive.md`: yes
  - `dependency-intake-report.json`: yes
  - Open PR diffs, check runs, official releases, registry metadata, and repository product-boundary documentation

## Target upgrades

- `cffi`: 2.0.0 to 2.1.0 for Python 3.11+ runtime compatibility and upstream fixes
- `charset-normalizer`: 3.4.7 to 3.4.9 to take the post-3.4.8 regression fix
- `@fontsource-variable/inter`: 5.2.8 to 5.3.0 manifest provenance; selected font bytes unchanged
- `@fontsource-variable/jetbrains-mono`: 5.2.8 to 5.3.0 manifest provenance; selected font bytes unchanged
- `actions/setup-node`: 6.4.0 to 7.0.0; internal ESM migration, repository-only use
- `actions/setup-python`: 6.3.0 to 7.0.0; internal ESM migration and unused input removal, including product-facing `action.yml`
- `actions/attest`: 4.1.1 to 4.2.0 for release-provenance improvements
- OSV scanner and reporter: repin from post-release main snapshot to the verified v2.3.8 release SHA
- `numpy`: add `<2.5` development constraint to preserve the Python 3.11 type-check target across the CI matrix
- Ruff compatibility: parenthesize 21 collection-member string concatenations required by freshly resolved Ruff 0.16.0

## Execution stages

1. Stage A — development compatibility: reproduce the Ruff 0.16.0 failure in the refreshed `venv`, apply the mechanical syntax fix, and extract the NumPy cap.
2. Stage B — repository automation: apply setup-node, setup-python workflow occurrences, actions/attest, and OSV release pins; synchronize version comments and exact-SHA tests.
3. Stage C — product dependencies: apply the vendored manifest refresh and targeted Python runtime-lock upgrades.
4. Stage D — generated products: rebuild the template/demo and validate current/minimum-compatible template consumers.

## Validation gates

- Formatting/diff hygiene: `git diff origin/main..HEAD --check`
- Lint: `make lint` with Ruff 0.16.0
- Type check: `make type-check` with mypy 2.3.0 and `numpy<2.5`
- Unit: all 496 Python tests and 21 JavaScript tests
- Coverage: Python 90.77%; JavaScript coverage command passed
- Runtime lock: consistency regeneration, hash-required installation, and `pip-audit`
- Vendored assets: repository validator and focused updater tests
- Build: generated template and demo build/verification
- Integration/e2e: template smoke, consumer e2e, composite boundary e2e, accepted public action e2e, and current/minimum-template compatibility
- Aggregate gate: `make prebeta-check`

## Rollback plan

- Git rollback: revert the dependency commits in reverse order, or revert the combined PR squash commit after merge.
- Runtime lock: restore `requirements-runtime.txt` from baseline `994bc2b84e79e98d26786a28a2aeb8d3ec6b8651` and reinstall with `make install`.
- Action pins: restore the baseline SHAs and matching version comments together with the assertion changes.
- Vendored manifests: revert both 5.3.0 manifest entries together.
- Deployment rollback: no service deployment is performed. If a released action exhibits runner incompatibility, move the stable `v0` channel back to the previous release and publish a corrective patch.

## Open questions and residual risks

- Require combined-branch protected CI on GitHub-hosted Python 3.11, 3.12, and 3.13 runners before merge.
- Consider manually dispatching `osv-scanner.yml` and `promotional-dashboard-guide.yml` on the pushed branch.
- Do not manually dispatch release attestation solely as a local-equivalent test because it creates external provenance records.
- Track the OSV upstream container-tag limitation separately; it cannot be corrected from this repository without replacing or wrapping the upstream action.
