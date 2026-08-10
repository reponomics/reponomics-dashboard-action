# Contributing

Reponomics Dashboard Action is in a public pre-release hardening period. The repository is visible so its security posture, workflows, dependency handling, and release process can be reviewed in the open, but it is not yet being promoted for general use.

Security reports are welcome. For security issues, follow `SECURITY.md` instead of opening a public issue with exploit details.

## Current Contribution Policy <>

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
make complexity
```

Complexity tooling is optional because it is not formally incorporated into CI/CD and is not supported in every environment.

Focused fixture checks are also available:

```bash
make fixture-collect
make fixture-publish
make fixture-rotate-key
```

Do not commit generated local state such as `venv`, coverage reports, caches, rendered dashboard output, or local dashboard data artifacts.

## Markdown Formatting

Do not hard-wrap Markdown prose. Keep paragraphs as single logical lines so future edits produce smaller diffs. The `LICENSE` file is the exception and may keep conventional license-text wrapping.
