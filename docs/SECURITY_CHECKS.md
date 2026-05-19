# Maintainer Security Checks

This repository ships a composite GitHub Action that handles sensitive repository
metrics and encrypted artifacts. The checks below are intentionally enforced in
CI, not only through local pre-commit hooks or repository settings, so pull
requests expose a visible security signal.

## GitHub Action SHA Pins

`scripts/validate_action_pins.py` scans `action.yml` and `.github` workflow YAML
for imported GitHub Actions. Third-party `uses:` references must be pinned to a
full 40-character lowercase commit SHA. Local actions and Docker image
references are not checked by this script.

CI runs this check through `.github/workflows/validate-action-pins.yml`, which is
also called by the aggregate `.github/workflows/ci.yml` workflow.

Run it locally with:

```bash
make validate-action-pins
```

GitHub repository settings may also enforce SHA-pinned actions. The script keeps
the same policy auditable from code review and from the `CI` workflow result.

## Vendored Assets

`scripts/validate_vendored_assets.py` verifies every `vendor/*/manifest.json`
entry. For each vendored asset it checks:

- the local asset and license hashes;
- npm registry metadata for the recorded package version;
- the recorded tarball integrity value;
- OSV vulnerability results for the pinned package version;
- the source asset and license bytes inside the published tarball.

Run it locally with:

```bash
make validate-vendored-assets
```

This check requires network access to the npm registry and OSV API.

CI runs this check through `.github/workflows/validate-vendored-assets.yml`,
which is also called by the aggregate `.github/workflows/ci.yml` workflow. The
workflow has a weekly scheduled run so newly disclosed OSV vulnerabilities can
fail the badge even when the vendored file has not changed.

## Release Notice Blocks

`scripts/validate_release_notice.py` validates the constrained
`<!-- reponomics-update {...} -->` block used in release notes. The dashboard
runtime parses this JSON metadata to show compatible upgrade notices to users of
pinned action versions. It does not render arbitrary remote release Markdown.

The supported schema and an example block are documented in
`README.md#maintainer-release-policy`.

Run the CLI against a release-note Markdown file with:

```bash
venv/bin/python scripts/validate_release_notice.py path/to/release-notes.md
```

Run the release-notice fixture tests with:

```bash
make validate-release-notice
```
