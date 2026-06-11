# Obsolete Documentation Inventory

This is a triage inventory for docs that predate the action/template
consolidation. Do not treat this file as a polished architecture document.

## Archive Or Rewrite Before Treating As Source Of Truth

- `docs/DOCUMENTATION_INVENTORY.md`
  - Still describes `reponomics-dashboard-dev` as the owner for template files.
  - Still describes action-release sync into dashboard-dev and a checked-in
    `template/docs/reponomics/` snapshot.
  - Status: obsolete under the consolidated repository model.

- `docs/ACTIVE_RETENTION_AND_LINEAGE_PLAN.md`
  - Mentions dashboard-dev responsibilities around generated workflows.
  - Status: partially stale; lineage/runtime details may still be useful, but
    repository ownership references need review.

- `docs/adr/008-template-and-generated-output-assurance.md`
  - Written for a multi-repository development/template/generated-output model.
  - Status: historically useful, but its repository-boundary discussion should
    not be read as current without a superseding note.

- `docs/adr/010-dashboard-scenario-corpus-and-design-labs.md`
  - Refers to `reponomics-dashboard-dev` and generated template test ownership.
  - Status: partially stale; snapshot/test rationale may still be useful.

- `docs/adr/011-managed-documentation-sync.md`
  - Some design rationale remains current, but the dashboard-dev snapshot path is
    no longer current. Managed docs now build from
    `dashboard_action/runtime/managed_docs/` into generated template output.
  - Status: partially stale.

## Still Likely Useful With Narrow Review

- `docs/MARKETPLACE_PUBLISHING.md`
- `docs/SECURITY_CHECKS.md`
- `docs/PROVENANCE.md`
- `docs/INCIDENT_RESPONSE.md`
- `docs/CSV_EXPORT.md`

These may still contain stale wording, but they are not primarily about the
retired dashboard-dev release handoff.
