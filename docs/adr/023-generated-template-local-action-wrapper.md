# ADR 023: Generated Template Local Action Wrapper

Date: 2026-06-17

## Status

Accepted

## Context

Generated dashboard workflows invoke `reponomics/reponomics-dashboard-action` from several jobs. Each invocation currently carries the same action ref in a separate workflow step. That is workable for the default `v0` compatible channel, but it is inconvenient and error-prone for generated repositories whose organization requires full-SHA-pinned Actions or whose maintainer chooses to pin the Reponomics action manually.

The generated template should keep the workflow jobs responsible for job-level permissions, scheduling, secrets, and mode-specific inputs. The concrete Reponomics action ref should have one generated home so a copied dashboard repository has one obvious place to inspect or update it.

## Decision

Ship a generated local composite action at `.github/actions/reponomics/action.yml`.

Generated workflows that currently call `reponomics/reponomics-dashboard-action@...` will instead call:

```yaml
uses: ./.github/actions/reponomics
```

The local action will call the real Reponomics action exactly once, using the generated template's accepted compatible action ref by default. For the ordinary compatible channel this is the major ref from `template-contract.yml`, currently `reponomics/reponomics-dashboard-action@v0`. Users who need full-SHA pinning will update the nested `uses:` line in this one local action file instead of updating every workflow.

This is an implementation simplification, not a change to the runtime permission model. Generated workflow jobs keep declaring their own permissions. The local action only declares inputs and forwards them to the real action.

## Wrapper Inputs

The wrapper must declare and forward every input currently passed by generated workflows:

- `artifact-run-id`
- `collection-token`
- `comparison-secret`
- `dashboard-next-secret`
- `dashboard-secret`
- `data-mode`
- `generate-readme`
- `github-token`
- `incident-confirm-irreversible`
- `incident-confirm-mode`
- `incident-confirm-purge`
- `mode`
- `publish-pages`
- `require-collect-provenance`
- `retention-days`
- `use-github-app`

The wrapper should not expose arbitrary passthrough behavior. Composite actions require explicit inputs, and explicit forwarding keeps the generated template contract reviewable.

If generated workflows later pass additional Reponomics action inputs, the wrapper and its tests must be updated in the same change.

## Wrapper Outputs

Generated template workflows do not currently consume outputs from Reponomics action steps. The wrapper therefore does not need to declare outputs for the initial implementation.

If a generated workflow later consumes a Reponomics action output, the wrapper must explicitly expose that output and forward it from the nested action step. Composite actions do not automatically re-export nested action outputs.

## Implementation Notes

- Keep `actions/checkout` before every generated workflow step that invokes the local action. Local actions are loaded from the checked-out repository workspace.
- Replace all generated workflow calls to `reponomics/reponomics-dashboard-action@...` with `uses: ./.github/actions/reponomics`.
- Add the wrapper under `template/.github/actions/reponomics/action.yml` so `scripts/build_template.py` copies it into the generated template.
- Give the nested action step a stable `id` so future wrapper outputs can be added without renaming the forwarding step.
- Keep the nested remote action ref generated from the template contract. The wrapper is the only generated file a SHA-pinning user should need to edit for the Reponomics action ref.
- Do not move job permissions, workflow triggers, concurrency settings, token minting, artifact restore steps, or mode-specific preflight shell logic into the wrapper.

## Blast Radius

Implementation should touch:

- `template/.github/actions/reponomics/action.yml`, new generated local action wrapper.
- `template/.github/workflows/collect-and-publish.yml`.
- `template/.github/workflows/doctor.yml`.
- `template/.github/workflows/rotate-key.yml`.
- `template/.github/workflows/incident-reset.yml`.
- Generated-template tests that currently expect direct `reponomics/reponomics-dashboard-action@...` workflow references.
- Template contract verification that currently scans generated files for direct action refs.
- Template compatibility e2e checks that currently identify generated workflow Reponomics invocations by direct remote `uses:` references.

Implementation should not touch:

- Source-repository release automation semantics.
- Job-level permission declarations.
- Action runtime inputs or behavior.
- Generated setup and keepalive workflows, unless tests prove an indirect reference needs updating.

## Verification

The implementation should prefer tests that protect useful invariants rather than tests that merely restate the implementation shape. Tests should make future refactors safer by checking contracts that can drift across files.

The implementation should prove:

- generated workflows invoke only `./.github/actions/reponomics` for Reponomics runtime calls;
- the generated template has a single maintained Reponomics action ref surface in the local wrapper;
- every `with:` key passed by generated workflows is declared by the wrapper;
- every forwarded wrapper input is declared by the real action metadata;
- the generated template builds and verifies;
- template compatibility e2e still runs against the current generated template and protected minimum compatible template refs;
- full-SHA-pinning users have one generated file to edit for the Reponomics action ref.

## Consequences

- The Reponomics action ref becomes a single generated maintenance point.
- Users on the default `v0` compatible channel continue to receive compatible action updates without manual workflow edits.
- Users who pin by SHA have one nested `uses:` line to update.
- Workflow files remain responsible for permissions and orchestration.
- Verification logic can inspect one wrapper file instead of treating scattered workflow references as the source of truth.
