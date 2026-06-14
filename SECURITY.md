# Security Policy

Reponomics Dashboard Action is in a public pre-release hardening period. The project handles GitHub traffic data, retained workflow artifacts, generated dashboard HTML, and optional dashboard encryption keys, so security reports are welcome even before general adoption is invited.

## Supported Versions

No stable production version is supported yet. Until the first stable release, security fixes will generally land on `main` and then be included in the next pre-release or release tag.

Before `v1`, users should not expect seamless updates between versions. Security fixes may be released together with incompatible pre-release changes, and migration guidance may require manual review.

After stable release, this policy will be updated with the supported major version line and expected fix process.

## Reporting a Vulnerability

Please do not open a public issue for a suspected vulnerability.

Use GitHub [private vulnerability reporting](https://github.com/reponomics/reponomics-dashboard-action/security/advisories/new) for this repository. You will receive a response with 48 hours and we will determine the appropriate method and timeline for a resolution if a problem is identified.

Useful reports include:

- affected commit, tag, or workflow run;
- a concise description of the vulnerability;
- reproduction steps using synthetic or redacted data;
- expected impact;
- whether any token, secret, or generated dashboard output may have been exposed.

## Scope

In scope:

- generated dashboard HTML and JavaScript;
- dashboard encryption and decryption behavior;
- retained dashboard data artifact encryption, restore, and upload behavior;
- workflow permissions, token handling, and release automation;
- vendored browser assets and their recorded upstream metadata;
- release notice parsing and rendering;
- action inputs and outputs that may expose sensitive data.

Out of scope:

- denial-of-service reports without a plausible security impact;
- reports that require access to a user's own GitHub token, repository settings, or dashboard secret without another vulnerability;
- social engineering, phishing, or physical attacks;
- vulnerability reports based only on a repository owner's low-entropy dashboard key choice, unless the report also shows a concrete implementation flaw in encrypted mode.

## Public Pre-Release Expectations

This repository is public for review and hardening, not broad production adoption. Security claims should be read narrowly:

- CI validates the action code, workflow shape, GitHub Action SHA pins, and vendored assets.
- Vendored assets are checked against recorded upstream package metadata and OSV vulnerability data.
- Generated dashboard artifacts in consuming repositories require their own workflow and deployment controls.
- Provenance and SBOM claims are documented in `docs/PROVENANCE.md` and should be read according to the specific commit, release, or consuming workflow being evaluated.

## Disclosure

Maintainers will assess reports and coordinate fixes according to severity and project stage. Because this is pre-release software, the usual resolution may be a fix on `main`, updated documentation, or a temporary warning against a configuration until a fuller mitigation is available.
