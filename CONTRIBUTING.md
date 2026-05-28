# Contributing

Reponomics Dashboard Action is in a public pre-release hardening period. The repository is visible so its security posture, workflows, dependency handling, and release process can be reviewed in the open, but it is not yet being promoted for general use and is not currently seeking outside contributors.

Security reports are welcome. For security issues, follow `SECURITY.md` instead of opening a public issue with exploit details.

## Current Contribution Policy

During this stage, maintainers may close or defer unsolicited feature requests, support requests, broad refactors, or pull requests that are not aligned with the current stabilization work. This is not a judgment on the quality of the idea; it is a scope control measure while the action, generated dashboard surface, and release process are being finalized.

Issues and pull requests that are most likely to be useful during pre-release:

- security vulnerability reports submitted through the private reporting path;
- small corrections to inaccurate documentation;
- reproducible CI, packaging, or release-process failures;
- narrowly scoped fixes for behavior that is already documented.

Please do not submit speculative integrations, large rewrites, new product features, formatting-only changes, or dependency churn unless a maintainer has asked for them.

## Development Setup

Use the project Makefile for local development. The repository expects a local `venv` virtual environment.

```bash
make install
make pre-commit-install
make ci
```

Individual checks are named after what they do:

```bash
make lint
make type-check
make validate
make test
make coverage
```

Focused fixture checks are also available:

```bash
make fixture-collect
make fixture-publish
make fixture-rotate-key
```

Do not commit generated local state such as `venv`, coverage reports, caches, rendered dashboard output, or local dashboard data artifacts.

## Markdown Formatting

Do not hard-wrap Markdown prose. Keep paragraphs as single logical lines so future edits produce smaller diffs. The `LICENSE` file is the exception and may keep conventional license-text wrapping.

## Security-Sensitive Areas

Be conservative with changes to:

- dashboard encryption and decryption;
- retained dashboard data artifact encryption and restore behavior;
- generated HTML or JavaScript;
- vendored third-party assets;
- workflow permissions and token handling;
- release notice parsing and rendering;
- release tags and generated release notes.

All imported GitHub Actions in workflows and in `action.yml` must be pinned to full-length commit SHAs. New workflows or action imports must also fit the repository Actions allowlist; if a new non-GitHub, non-`reponomics` action or reusable workflow is required, update the repository allowlist at the same time or document why the workflow is expected to be covered by the default policy. Vendored browser assets must remain verifiable from their recorded upstream package metadata.

## Pull Request Expectations

If a maintainer asks you to open a pull request, keep it small and include:

- the reason for the change;
- any security or compatibility impact;
- tests or a clear reason tests are not needed;
- the exact verification command you ran.

For action input/output changes, update `README.md`, `action.yml`, and tests together.

## Releases

Release Please manages releases. Use conventional commit messages for maintainer-authored changes:

```text
feat: add new behavior
fix: correct existing behavior
docs: update documentation
ci: update workflow behavior
chore: maintain tooling
```

Exact SemVer tags are immutable release identities. Floating compatibility tags such as `v1` and `v1.2` should move only as part of the release process.
