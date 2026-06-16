# Dependency Management

Status: maintainer reference.

This document describes how dependencies are declared, locked, checked, and updated in the Reponomics action source repository. It is a live maintainer document and is not shipped into generated dashboard repositories.

## Quick Model

- `pyproject.toml` is the source dependency declaration for the Python package, local development environment, and most source-repository CI jobs.
- `requirements-runtime.txt` is the hash-pinned runtime lock installed by the composite action before it runs the bundled Python runtime.
- `requirements-runtime.txt` is generated from `pyproject.toml` with `make lock-runtime`; do not hand-edit it except for emergency inspection.
- Source-repository workflows run on Ubuntu, and generated template workflows use `ubuntu-latest`. The composite action itself sets up Python 3.11.
- Dependabot reports the manifest path it is evaluating. Treat an alert on `requirements-runtime.txt` as a runtime-lock issue even if the same package is also declared by range in `pyproject.toml`.
- Vendored browser assets are not npm-installed at runtime. They are tracked through `vendor/*/manifest.json` and the vendored-asset validation scripts.

## Dependency Surfaces

| Surface | Source files | Runtime use | Update entry point | Automated checks |
| --- | --- | --- | --- | --- |
| Python package and dev environment | `pyproject.toml` | Local `venv`, lint, type check, tests, `pip-audit` environment audit | Edit `pyproject.toml`, then run `make install` or recreate `venv` when needed | `ci.yml`, `open-source-security.yml`, `make security-audit` |
| Composite action runtime lock | `requirements-runtime.txt` | Installed by `action.yml` with `python -m pip install --require-hashes` | Run `make lock-runtime` after dependency-range changes or runtime-lock alerts | `validate-runtime-lock.yml`, `open-source-security.yml`, `make validate-runtime-lock`, `make audit-runtime-lock`, Dependabot pip alerts |
| GitHub Actions used by this source repo | `.github/workflows/*.yml`, `action.yml` | CI, release, publishing, validation, repository security signals | Update action refs by full commit SHA with nearby version comments | Dependabot `github-actions`, workflow validation, repository policy, Scorecard/PolicyChecks visibility |
| Generated template workflow actions | `template/.github/workflows/*.yml` | Workflows in generated dashboard repositories | Update template workflow sources and run template gates | Template and generated-output tests; not the root source-repo action pinning policy alone |
| Vendored browser assets | `vendor/*/manifest.json`, vendored asset files | Inlined or copied into generated dashboard outputs | Run `make update-vendored-assets` | `validate-vendored-assets.yml`, `update-vendored-assets.yml`, OSV checks inside `scripts/validate_vendored_assets.py` |
| Repository-level vulnerability visibility | manifests, locks, source tree | Maintainer signal, not runtime installation | Investigate Dependabot, OSV, and `pip-audit` findings by manifest path | Dependabot, `osv-scanner.yml`, `open-source-security.yml`, code scanning |

## Python Dependencies

`pyproject.toml` declares the Python package metadata, direct runtime dependencies, and development extras. `make install` creates `venv`, upgrades `pip`, and installs the package in editable mode with development extras:

```bash
make install
```

The `make install` target is stamp-based and depends on both `pyproject.toml` and `requirements-runtime.txt`. When either file changes, `make install` refreshes the local `venv` with an eager upgrade from `pyproject.toml`, so local source/development checks are less likely to run against stale package versions. CI starts from a fresh runner and resolves from `pyproject.toml`.

The local `venv` is still not the action runtime environment. The composite action runtime is checked separately from `requirements-runtime.txt` through `make validate-runtime-lock` and `make audit-runtime-lock`.

Use `pyproject.toml` when changing the supported dependency range for the package. If a lower bound is raised for security or compatibility reasons, update `pyproject.toml` and regenerate the runtime lock.

## Runtime Lock

The composite action does not resolve Python dependency ranges during user workflow runs. `action.yml` installs `requirements-runtime.txt` in hash-required mode, then runs the bundled runtime script.

Regenerate the lock with:

```bash
make lock-runtime
```

Validate the committed lock with:

```bash
make validate-runtime-lock
```

`make validate-runtime-lock` performs two checks:

1. Regenerates a temporary lock from `pyproject.toml` without upgrades and compares it with `requirements-runtime.txt`.
2. Installs the committed lock into a temporary target with `--require-hashes`.

This check proves the lock is synchronized with the declared dependency ranges and hash-installable. It does not prove that the lock is the newest safe version. Vulnerability and freshness signals come from Dependabot, OSV-Scanner, and `pip-audit`.

## Security Checks

`make security-audit` runs `pip-audit` against the installed local environment with editable project packages skipped. It checks the resolved source/development environment.

`make audit-runtime-lock` runs `pip-audit` against `requirements-runtime.txt`. It checks the hash-pinned dependency set installed by the composite action in user workflows.

`make security` runs:

```bash
make security-audit
make audit-runtime-lock
make validate-runtime-lock
make validate-vendored-assets
```

`osv-scanner.yml` runs OSV-Scanner recursively and uploads SARIF to code scanning on push, schedule, and manual dispatch. It complements, but does not replace, Dependabot and `pip-audit`.

When investigating a vulnerability, use all three signals deliberately:

- Dependabot: authoritative for GitHub's dependency graph alert surface and specific manifest path.
- `pip-audit`: independent audit of the resolved Python environment and the runtime requirements lock.
- OSV-Scanner: repository-level OSV signal for supported manifests and locks.

## Dependabot

`.github/dependabot.yml` configures two ecosystems:

- `github-actions` for action refs in the repository workflow surface.
- `pip` for Python dependency manifests in the repository root.

Dependabot security updates can bypass version-update ignore rules. For example, the repository ignores routine semver-major `cryptography` version updates because runtime crypto upgrades need maintainer review, but a security update may still propose or require a major version.

Use the alert's manifest path to decide the remediation:

- `pyproject.toml`: update the declared Python range if the package metadata should no longer allow affected versions.
- `requirements-runtime.txt`: run `make lock-runtime` and check whether the lock moved to the version Dependabot expects.
- GitHub workflow files: update the referenced action to the intended upstream version and pin the full commit SHA.

## GitHub Actions And Runners

Source-repository workflows run on `ubuntu-24.04`, except for Scorecard on `ubuntu-latest`. Generated template workflows use `ubuntu-latest`. The action setup step installs Python 3.11.

Evaluate runtime dependency compatibility primarily against Linux and Python 3.11, while keeping the package test matrix compatible with the Python versions in `ci.yml`.

Third-party actions in source-repository workflows should be pinned by full commit SHA with a nearby version comment. Generated dashboard template workflows intentionally use the compatible Reponomics action channel, such as `reponomics/reponomics-dashboard-action@v0`, so users receive compatible fixes without manually chasing every action release.

## Vendored Assets

Vendored browser assets live under `vendor/` with package manifests. They are not installed through npm in user workflows.

Validate them with:

```bash
make validate-vendored-assets
```

Refresh them with:

```bash
make update-vendored-assets
```

The validator checks local hashes, recorded upstream package metadata, tarball integrity, license bytes, and OSV status for pinned package versions.

## Maintainer Upgrade Workflow

For Python dependency alerts or planned upgrades:

1. Read the alert, release notes, and changelog for the exact current-to-target range.
2. Decide whether `pyproject.toml` needs a new lower bound or only the runtime lock needs regeneration.
3. Run `make lock-runtime` when `requirements-runtime.txt` should change.
4. Run `make validate-runtime-lock`.
5. Run `make audit-runtime-lock` for a focused runtime-lock vulnerability check, or `make security` for the aggregate local security checks.
6. Run focused tests when the dependency touches runtime behavior, encryption, artifact handling, workflow execution, or generated outputs.

For GitHub Actions updates:

1. Identify the upstream release or tag.
2. Resolve and pin the full commit SHA.
3. Keep job-level permissions scoped to the jobs that need them.
4. Run workflow validation and any affected CI path.

For vendored assets:

1. Run `make update-vendored-assets`.
2. Review changed assets, manifests, upstream release notes, and license bytes.
3. Run `make validate-vendored-assets`.

## Known Boundaries

- `validate-runtime-lock` is a lock consistency check, not a vulnerability gate.
- `security-audit` checks the installed environment, which can be stale locally if `venv` was created before a dependency range or lock update.
- Dependabot, OSV, and upstream advisory metadata can disagree temporarily. Prefer the concrete manifest path, resolver output, and current upstream release notes when deciding the patch.
- Template workflow dependencies are part of the generated repository surface. Treat them as product-facing changes, not only source-repository CI maintenance.

ADR 021 records the adopted split between runtime-lock consistency checks, runtime-lock vulnerability audits, and direct dependency lower-bound review.
