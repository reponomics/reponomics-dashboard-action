# Provenance And Verification Materials

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

This page lists the provenance and verification material Reponomics publishes or writes into generated repositories.

## In This Dashboard Repository

| Evidence | Location | Contains |
| --- | --- | --- |
| Managed-docs manifest | `docs/reponomics/.manifest.json` | action repository, action version, managed namespace, generation timestamp, managed-doc file hashes |
| Template provenance | `.reponomics/template-provenance.json` | source repository and commit, template version, action repository/default ref/compatible major, template compatibility line, generated payload digest metadata |
| Workflow action refs | `.github/workflows/*.yml` | Reponomics action refs used by generated workflows |
| Collect provenance artifact | `reponomics-collect-provenance` workflow artifact, path `.reponomics/collect-provenance/collect-provenance.json` | source repository SHA, workflow run ID/attempt, action repository/ref/resolved SHA, runtime version, data mode, retention and publication settings |
| Retained dashboard data artifact | `dashboard-data` workflow artifact | retained encrypted or plaintext dashboard data, depending on `data_mode` |
| Rendered dashboard outputs | Pages artifact or downloadable dashboard artifact | generated dashboard HTML and assets from the repository workflow run |

## Generated Template Publication

| Evidence | Location | Contains |
| --- | --- | --- |
| Published template commit | `reponomics/reponomics-dashboard` `main` branch | generated template tree |
| Publication commit trailer | generated template commit message `Source-Commit` | source repository commit used for publication |
| Template provenance file | `.reponomics/template-provenance.json` in the generated template tree | source commit, template version, action ref metadata, canonical payload digest |
| Managed-docs manifest | `docs/reponomics/.manifest.json` in the generated template tree | action version and managed-doc hashes for the shipped docs snapshot |
| Template release artifacts | `publish-template.yml` workflow artifact named `reponomics-dashboard-template-release-<template-release-tag>` | deterministic template archive, canonical tree manifest, `SHA256SUMS` |
| Template artifact attestations | GitHub artifact attestations from `publish-template.yml` | attestations for the template archive, tree manifest, and checksum file |

Template release artifact names are derived from `template-contract.yml` and the `reponomics-dashboard-v<template_version>` release tag. The canonical tree manifest excludes `.reponomics/template-provenance.json`; the provenance file records that exclusion.

## Action Releases

| Evidence | Location | Contains |
| --- | --- | --- |
| Action release tag | `reponomics/reponomics-dashboard-action` Git tags and GitHub Releases | released action source ref |
| Floating action tags | action repository tags such as `v<major>` and `v<major>.<minor>` | compatible action channel refs moved by release automation |
| Release source archive | `sbom-provenance.yml` workflow artifact `reponomics-release-provenance` | Git archive of the release source tree |
| Release SBOM | `sbom-provenance.yml` workflow artifact `reponomics-release-provenance` | SPDX JSON SBOM for the release source tree |
| Release attestations | GitHub artifact attestations from `sbom-provenance.yml` | attestations for the release source archive and release SBOM |
| Runtime dependency lock | `requirements-runtime.txt` at the action ref | hash-pinned Python runtime dependencies |
| Vendored browser asset manifests | `vendor/*/manifest.json` at the action ref | upstream package metadata, local asset hashes, license hashes |

## Demo Publication

| Evidence | Location | Contains |
| --- | --- | --- |
| Demo provenance | `reponomics/reponomics-dashboard-demo` `.reponomics/demo-provenance.json` | source repository/commit, template version, dataset revision, synthetic-data marker, generated payload digest, retained-data seed metadata |
| Demo publication commit trailer | generated demo commit message `Source-Commit` | source repository commit used for publication |
| Demo publication workflow artifacts | `publish-demo.yml` workflow artifacts `generated-demo-repo` and `generated-demo-dashboard-data` | generated demo tree archive, source commit file, encrypted demo seed data |

## Local Verification Commands

Run these from a checkout of `reponomics/reponomics-dashboard-action` at the action ref being evaluated.

```bash
make validate-vendored-assets
make validate-runtime-lock
venv/bin/python scripts/template_provenance.py verify --root dist/template
venv/bin/python scripts/template_provenance.py manifest --root dist/template --output /tmp/template.tree.jsonl
```

For a copied dashboard repository, inspect the local files and workflow artifacts listed above. For source-repository release materials, inspect the named GitHub Actions workflow run and its artifacts/attestations.
