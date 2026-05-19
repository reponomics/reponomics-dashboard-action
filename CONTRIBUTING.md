# Contributing

Thanks for contributing to Reponomics Dashboard Action. This project is security-sensitive because it handles GitHub traffic data, retained workflow artifacts, dashboard publication, and dashboard encryption keys. Prefer small, reviewable changes with clear tests over broad rewrites.

## Development Setup

Use Python 3.13 for local development. The project supports Python 3.11 and newer, so avoid syntax that requires Python 3.12+ unless the supported runtime floor changes.

```bash
make install
make pre-commit-install
```

The project uses a local `venv` directory and Makefile targets for repeated operations. Do not commit generated local state such as `venv`, coverage reports, caches, rendered dashboard output, or local traffic artifacts.

## Validation

Run the full local verification suite before opening a pull request:

```bash
make verify
```

For a quicker pass while editing:

```bash
make pre-commit-run
make test
```

Focused fixture checks are available for the action modes:

```bash
make fixture-collect
make fixture-publish
make fixture-rotate-key
```

The complexity tooling is available but is not currently a required CI gate:

```bash
make complexity
```

## Code Style

Follow the existing code structure and keep action behavior explicit. Use built-in generic type syntax such as `list[str]` and `dict[str, Any]`; those are valid for Python 3.11+. Avoid Python 3.12-only type syntax such as `type Alias = ...` or generic function/class parameter syntax.

Markdown prose does not need hard wrapping. License text and generated/legal text may keep conventional wrapping.

## GitHub Actions Security

All imported GitHub Actions in workflows and in `action.yml` must be pinned to full-length commit SHAs. Keep the human-readable version tag as a trailing comment:

```yaml
uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
```

The repository validates this convention with:

```bash
make lint-action-pins
```

Use least-privilege workflow permissions. The default token permission should remain read-only at the organization/repository level. Workflow-level permissions should also default to read-only or narrower, and write scopes should be assigned at the specific job that needs them whenever GitHub Actions supports that shape. For example, the Release Please job needs `contents: write` and `pull-requests: write`, while ordinary CI jobs should only need `contents: read`.

## Security-Sensitive Changes

Be conservative with changes to:

- dashboard encryption and decryption,
- artifact encryption and restore behavior,
- generated HTML or JavaScript,
- vendored third-party assets,
- workflow permissions and token handling,
- release notice parsing and rendering.

Release notices intentionally parse only the constrained `<!-- reponomics-update ... -->` JSON block from GitHub Release bodies. Do not render arbitrary remote release Markdown into user dashboards.

Vendored assets must remain cryptographically verifiable. Chart.js is vendored from a pinned npm tarball and checked against recorded integrity/hash metadata and OSV vulnerability data:

```bash
make lint-vendored-assets
```

## Releases

Release Please manages releases. Use conventional commit messages for user-facing changes:

```text
feat: add new behavior
fix: correct existing behavior
docs: update documentation
ci: update workflow behavior
chore: maintain tooling
```

Use a `Release-As:` trailer only when intentionally steering the next release version:

```text
Release-As: 0.2.0
```

Do not manually edit generated Release Please pull request content unless the release automation requires it.

## Dependency Updates

Dependabot may open pull requests for Python dependencies and GitHub Actions. Review dependency PRs for security impact, major version changes, workflow permission changes, and SHA pin consistency. Nested actions used by this composite action are part of the action implementation surface; consumers pick up those changes when they update their Reponomics action ref or when a major tag advances.

## Pull Requests

Pull requests should include:

- a concise description of the user-facing behavior change,
- any security or compatibility implications,
- tests or a clear reason tests are not needed,
- the verification command run locally.

For changes touching action inputs/outputs, update `README.md`, `action.yml`, and tests together.
