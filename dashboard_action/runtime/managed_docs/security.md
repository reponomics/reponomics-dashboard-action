# Security Guidance

> [!NOTE]
> These docs describe the official Reponomics generated workflows for the `v0` external beta. Repository owners can modify their copies; modified workflows may behave differently from what these docs describe.

## Reporting Security Issues

Do not open a public issue for a suspected vulnerability.

For the Reponomics action/runtime, use GitHub private vulnerability reporting in the development repository:

<https://github.com/reponomics/reponomics-dashboard-action/security/advisories/new>

For a dashboard repository copied from the template, repository owners remain responsible for their own repository policies, access control, secrets, Pages settings, and workflow changes.

## What Not To Publish

Do not publish these in public issues, discussions, comments, or screenshots:

- `COLLECTION_TOKEN` or other GitHub tokens;
- `DASHBOARD_SECRET_DO_NOT_REPLACE` or rotation secrets;
- retained `dashboard-data` artifact contents;
- private workflow logs or generated dashboard data;
- exploit details for a suspected vulnerability before private triage.

## Supported Beta Line

The external beta uses the `v0` action line. Security fixes may land as new `v0.x.y` releases before the stable `v1` line exists.

Generated dashboard repositories call the versioned action through the local wrapper at `.github/actions/reponomics/action.yml`. If you pin that wrapper to an exact action tag or commit SHA, you own manual upgrades until you update it.

## Data-Loss Boundaries

Reponomics cannot recover:

- a lost dashboard key that was never saved outside GitHub secrets;
- retained history after all usable `dashboard-data` artifacts expire or are deleted;
- encrypted retained artifacts after the only valid key is overwritten without using **Rotate Key**;
- private repository data that was exposed by local workflow edits, broad repository access, or public issue comments.

General background is available in [Dashboard Essentials](dashboard-essentials.md), [Secure Dashboard Key Generation](secure-dashboard-key.md), [Repository Access And Trust Boundary](trust-boundary.md), and [Provenance And Verification Materials](provenance.md).
