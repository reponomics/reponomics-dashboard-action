# Documentation Inventory

Status: maintainer reference.

This document records where Reponomics documentation lives, who owns it, and how it reaches the generated dashboard template or user-created repositories. It is not part of the managed documentation bundle.

## Quick Rules

- Runtime/user docs that should be synced into generated dashboard repositories belong in `reponomics-dashboard-action` under `dashboard_action/runtime/managed_docs/`.
- Template-owned top-level files such as `README.md`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md`, and `SUPPORT.md` belong in `reponomics-dashboard-dev` under `template/`.
- Dashboard-dev maintainer docs and ADRs belong in `reponomics-dashboard-dev/docs/` and must not be shipped into `reponomics-dashboard`.
- Action maintainer docs and action ADRs belong in `reponomics-dashboard-action/docs/` and are not copied into generated repositories.
- ADRs are decision records. They may be superseded or appended, but they should not be updated by release-sync automation to track the current action version.
- Do not edit `reponomics-dashboard` directly except for explicitly approved emergency recovery. Backport any emergency edit to the owning source repository.

## Repository Roles

### `reponomics-dashboard-action`

Owns runtime behavior and action-bundled user documentation.

Important documentation locations:

- `dashboard_action/runtime/managed_docs/`: user-facing managed docs bundled with each action release.
- `docs/`: action maintainer docs, action architecture notes, security/provenance notes, and action ADRs.
- `docs/DEPENDENCY_MANAGEMENT.md`: action maintainer dependency surfaces, ownership, and update workflow.
- `docs/FAQ.md` and `docs/PROVENANCE.md`: action-repo pointers to the corresponding managed docs, not the canonical user copies.
- `.github/ISSUE_TEMPLATE/`: action repository issue templates.
- `.github/workflows/README.md`: action repository workflow inventory.

Promotion path:

1. Update managed docs in `dashboard_action/runtime/managed_docs/`.
2. Add or update action-side tests for managed-doc contents when the file set or contract changes.
3. Release `reponomics-dashboard-action`.
4. The action release dispatches dashboard-dev action-release sync.
5. Dashboard-dev sync snapshots the released managed docs into `template/docs/reponomics/`.
6. Runtime `docs-sync` later updates user-created repositories under `docs/reponomics/`.

### `reponomics-dashboard-dev`

Owns the generated template source, generated-output tests, and template publication.

Important documentation locations:

- `docs/`: dashboard-dev maintainer docs, repository policy, generated repository model, template release protocol, architecture docs, and dashboard-dev ADRs.
- `template/README.md`: the generated template's initial root README.
- `template/CODE_OF_CONDUCT.md`, `template/CONTRIBUTING.md`, `template/SECURITY.md`, `template/SUPPORT.md`: template-owned top-level community-health files.
- `template/docs/reponomics/`: generated snapshot of the accepted action release's managed-docs bundle.
- `template-manifest.yml`: source-to-template copy contract.
- `.github/workflows/README.md`: dashboard-dev workflow inventory.

Promotion path:

1. Edit template-owned files under `template/` when changing the generated template surface.
2. Edit dashboard-dev maintainer docs under `docs/` when changing maintainer policy or architecture.
3. Do not hand-edit `template/docs/reponomics/` for content changes; update the source managed docs in the action repo, release the action, and run action-release sync.
4. Run generated-output checks in dashboard-dev.
5. Release dashboard-dev when the accepted state should publish to `reponomics-dashboard`.
6. Dashboard-dev publication generates and pushes the template repository from `template-manifest.yml`.

### `reponomics-dashboard`

Is the generated template repository users create dashboard repositories from.

Expected documentation surface:

- root `README.md`, generated from `reponomics-dashboard-dev/template/README.md`
- top-level community-health files generated from `reponomics-dashboard-dev/template/`
- `docs/reponomics/`, initially generated from `reponomics-dashboard-dev/template/docs/reponomics/`

Ownership rules:

- The repository should be generated from dashboard-dev, not maintained by direct edits.
- It should not contain dashboard-dev maintainer docs, tests, scripts, ADRs, or architecture notes.
- Its initial `docs/reponomics/` content should match the accepted action release snapshot.

### User-created dashboard repositories

Start from `reponomics-dashboard` and then become user-owned repositories.

Expected documentation behavior:

- The initial setup README comes from the generated template.
- If setup later enables a README dashboard, setup may preserve the initial README as a local backup before replacing the root README with generated dashboard output.
- `docs/reponomics/` is the only action-managed docs namespace.
- Runtime `docs-sync` may update `docs/reponomics/` when enabled and permitted.
- Top-level community-health docs are not managed by runtime docs sync.

## Managed Docs Tree Invariant

The managed-docs bundle tree at `dashboard_action/runtime/managed_docs/` is expected to be copied isomorphically into dashboard-dev at `template/docs/reponomics/` and into generated or user-created dashboard repositories at `docs/reponomics/`. File names and relative paths inside that namespace should not be remapped during action-release sync, template publication, or runtime docs sync.

Action-repo tests may validate managed-doc structure and local managed-doc links against `dashboard_action/runtime/managed_docs/` because of this invariant: a relative link that resolves inside the source bundle should resolve the same way after the bundle is rooted at `docs/reponomics/`. This assumption is deliberately narrower than the general `template-manifest.yml` source-to-template mapping, where source paths may be transformed before users see them.

If dashboard-dev reintroduces per-file path remapping inside `template/docs/reponomics/`, or if runtime docs sync starts projecting managed docs through any non-isomorphic transform, source-bundle link checks in this action repo are no longer sufficient. In that case, link integrity must be checked against the post-transform generated tree instead.

## Documentation Types

| Type | Owner | Source location | Shipped to template? | Updated after user creates repo? |
| --- | --- | --- | --- | --- |
| Action managed docs | `reponomics-dashboard-action` | `dashboard_action/runtime/managed_docs/` | Yes, via dashboard-dev snapshot at `template/docs/reponomics/` | Yes, via runtime `docs-sync` under `docs/reponomics/` |
| Template root README | `reponomics-dashboard-dev` | `template/README.md` | Yes, as root `README.md` | Setup may replace it if README dashboard output is enabled |
| Template community-health docs | `reponomics-dashboard-dev` | `template/CODE_OF_CONDUCT.md`, `template/CONTRIBUTING.md`, `template/SECURITY.md`, `template/SUPPORT.md` | Yes, as top-level files | No action-managed updates |
| Dashboard-dev maintainer docs | `reponomics-dashboard-dev` | `docs/` | No | No |
| Dashboard-dev ADRs | `reponomics-dashboard-dev` | `docs/adr/` | No | No |
| Action maintainer docs | `reponomics-dashboard-action` | `docs/` | No | No |
| Action ADRs | `reponomics-dashboard-action` | `docs/adr/` | No | No |
| Workflow inventories | Owning repo | `.github/workflows/README.md` | No, except generated workflows themselves | No |
| Issue templates | Owning repo | `.github/ISSUE_TEMPLATE/` | Not currently part of generated template docs | No |

## Common Changes

To change user-facing runtime guidance such as configuration, provenance, privacy behavior, secure key handling, support wording, or upgrade guidance:

1. Edit `reponomics-dashboard-action/dashboard_action/runtime/managed_docs/`.
2. Release the action.
3. Accept the action release in dashboard-dev so `template/docs/reponomics/` refreshes.
4. Release dashboard-dev if the generated template should publish the new snapshot.

To change the generated template's initial welcome/setup instructions:

1. Edit `reponomics-dashboard-dev/template/README.md`.
2. Update dashboard-dev generated-output tests if needed.
3. Release dashboard-dev when the change should reach `reponomics-dashboard`.

To change top-level community-health files:

1. Edit the corresponding file under `reponomics-dashboard-dev/template/`.
2. Keep language template-appropriate and avoid promises that should belong to a user-created repository owner.
3. Release dashboard-dev when the change should reach `reponomics-dashboard`.

To change maintainer policy, architecture, or historical decisions:

1. Edit the owning repo's `docs/`.
2. Do not expect the change to appear in generated repositories.
3. For ADRs, prefer a new ADR, a superseding note, or an appended status section over post-hoc rewrites.

## Boundaries To Preserve

- Do not expand runtime `docs-sync` outside `docs/reponomics/` without a new design decision.
- Do not make action-release sync rewrite ADRs to track the latest action version.
- Do not copy dashboard-dev `docs/` into `reponomics-dashboard`; `template-manifest.yml` should keep those paths forbidden.
- Do not use top-level template community-health docs as action-managed support or security policy.
- Do not use `reponomics-dashboard` as a source of truth for docs. It is the generated output.
