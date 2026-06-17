# Template And Action Release Recovery Runbook

## Scope

This runbook covers failures across:

- action release: `vX.Y.Z`
- floating action refs: `vX`, `vX.Y`
- template acceptance PR
- source-repo template release: `reponomics-dashboard-vA.B.C`
- generated template publication: `reponomics/reponomics-dashboard`
- generated template provenance and release artifacts

The guiding rule is: immutable release history is not rewritten. Recovery happens through rerunning failed workflows when the approved source is still correct, or through corrective patch releases when the approved source was wrong.

## Release-Readiness Requirements

Use this operational runbook before and after public launch. Do not defer recovery practices until after public release. Before treating the release process as ready, ensure:

- `template-contract.yml` records `accepted_action` with action tag and SHA.
- `minimum_compatible_template_version` and `protected_template_refs` are accurate.
- `make template-compat-e2e` gates action releases against current and minimum compatible templates.
- `make template-release-gates` gates template publication against the accepted action release.
- Template release notes state compatibility resets explicitly.
- Required release and publication workflow credentials are configured.
- Branch protection prevents direct pushes to `main`.

## Immutable Release Rules

- Exact action tags are immutable.
- Source-repo template release tags are immutable.
- Published GitHub Releases are not edited as a recovery mechanism.
- Floating action refs may move to corrective releases after validation.
- Generated template repo `main` may be force-pushed only by the publication workflow from an approved source release.
- Recovery uses reruns from the same approved source when the source is correct, or corrective patch releases when the source is wrong.

## Public Readiness And Versioning

This runbook should already be followed while the project is pre-public. The only phase-specific difference is versioning while the project remains on the `v0` line:

- Before public release, a breaking compatibility reset does not require a major version bump.
- Even before public release, an intentional compatibility reset must be explicit in `template-contract.yml`, release notes, and compatibility or migration notes when applicable.
- After public launch, breaking resets should be avoided unless intentionally announced and coordinated.

## Incident Triage

First identify the failure layer:

1. Action release failed before tag creation.
2. Action tag exists but floating refs are wrong.
3. Action release exists but template acceptance PR failed.
4. Template acceptance PR merged but template release failed.
5. Template release exists but generated publication failed.
6. Generated template was published with wrong contents/provenance.
7. Released action breaks an older protected template.
8. Released template gives new users broken setup.

Record:

- action tag/SHA
- template version/tag
- source commit
- workflow run URLs
- whether generated `reponomics-dashboard` changed
- whether users could have copied the affected template

## 1. Action Release Failed Before Tag Creation

Impact: no public action release exists.

Response:

- Fix the release PR or workflow issue.
- Rerun Release Please flow.
- Do not create a template acceptance PR.
- No user-facing release note required unless the failed attempt was visible.

## 2. Action Tag Exists But Floating Refs Are Wrong

Impact: exact action release exists, but `vX` or `vX.Y` may point to the wrong SHA.

Response:

- Verify the exact tag `vX.Y.Z` points to the intended release SHA.
- Move only floating refs to the exact release SHA.
- Rerun `make validate-template-action-ref`.
- If generated templates use the floating major ref, confirm `default_action_ref` now resolves correctly.
- Document the correction in maintainer notes; public notes usually unnecessary unless users were impacted.

Do not move the exact `vX.Y.Z` tag.

## 3. Action Release Exists But Template Acceptance PR Failed

Impact: action release is public, but template contract has not accepted it.

Response:

- Leave the action release in place if it passed `template-compat-e2e`.
- Fix the acceptance automation or contract issue.
- Open or refresh the template acceptance PR.
- Ensure the PR body has `## Template release notes`.
- Merge only after `validate-template-accepted-action` and relevant CI pass.
- The release train is incomplete until the template acceptance release publishes.

Public note: normally just the eventual template release note, e.g. `Updated action to vX.Y.Z`.

## 4. Template Acceptance PR Merged But Template Release Failed

Impact: `main` says the template version should be released, but no `reponomics-dashboard-vA.B.C` release exists.

Response:

- Do not bump the template version again just to retry.
- Fix the workflow or validation failure.
- Rerun the failed workflow if possible.
- If rerun is impossible, create the same `reponomics-dashboard-vA.B.C` source-repo release from the merged commit only after running `make template-release-gates` locally or in CI.
- Confirm `publish-template.yml` runs from that release.

Public note: use the merged PR’s release notes unchanged.

## 5. Template Release Exists But Generated Publication Failed

Impact: source-repo release exists, but `reponomics/reponomics-dashboard` was not updated.

Response:

- Inspect `publish-template.yml` failure.
- If the failure occurred before publication, fix and rerun `publish-template.yml`.
- If publication partially pushed, compare generated repo `Source-Commit` and `.reponomics/template-provenance.json`.
- Rerun publication only from the same source-repo release tag.
- Do not create a new template version unless the template payload itself must change.

Public note: not required unless users could copy the stale/broken generated repository during the incident window.

## 6. Generated Template Published With Wrong Contents Or Provenance

Impact: users may copy a bad template.

This should not happen after a successful normal publication run. `publish-template.yml`
runs `make template-release-gates` before minting the publication app token, and
`scripts/publish_generated_repo.py --push` fetches the published branch after the
push and verifies its `.reponomics/template-provenance.json` payload digest against
the generated source tree. If this incident occurs anyway, treat it as one of:

- a bug in the publication verifier or provenance generator;
- use of an operator bypass path outside the normal release workflow;
- mutation of `reponomics/reponomics-dashboard` after a successful publication.

Response:

- Stop further releases.
- Confirm whether the failed or suspect `publish-template.yml` run reached the post-push verification step.
- Determine whether the source-repo template release artifact and recorded source commit were correct.
- If the source release was correct but the generated repo was mutated or publication verification had a bug, fix the verifier if needed, then republish from the same release tag only if doing so restores the exact approved payload.
- If the approved source release itself was wrong, publish a corrective template patch release.
- Do not silently mutate the source-repo release notes to hide the incident.
- Add a release note explaining the corrected payload if users could have copied the bad version.

Corrective release example:

```md
## Template release notes

Corrects the generated template provenance for vA.B.C. Users who copied the previous generated template during the affected window should update from vA.B.D or verify `.reponomics/template-provenance.json`.
```

## 7. Released Action Breaks An Older Protected Template

Impact: compatibility promise violated.

Response:

- Confirm failure with `make template-compat-e2e`.
- If the exact action release is bad, publish an action patch release restoring compatibility.
- Move floating refs `vX` and `vX.Y` to the corrective action patch only after it passes compatibility gates.
- Keep the bad exact tag immutable; identify it as superseded in the corrective release notes if needed.
- Create a template acceptance PR for the corrective action release.
- Do not move `minimum_compatible_template_version` forward retroactively to avoid the failure.

Only change the minimum compatible template version if this is an intentional compatibility reset with explicit release notes. A bad release is not a compatibility reset.

Example: if action `v0.23.7` breaks template `0.10.0`, recovery is:

1. Keep exact `v0.23.7` immutable.
2. Publish `v0.23.8` restoring compatibility.
3. Move floating `v0` and `v0.23` to `v0.23.8`.
4. Accept `v0.23.8` in a template patch release.
5. Leave `minimum_compatible_template_version: 0.10.0`.

Do not use `minimum_compatible_template_version` to hide a bad patch. That would cut older-but-supported repositories off from future compatible action fixes.

## 8. Released Template Gives New Users Broken Setup

Impact: copied new repositories may be broken, existing repositories may be unaffected.

Response:

- Confirm whether action runtime is fine against older templates.
- If the fix is template-only, publish a template patch release.
- If the fix requires action behavior, publish action patch first, then template acceptance release.
- Update release notes with clear user guidance.
- Consider refreshing demo after the corrective template release.

Example note:

```md
## Template release notes

Fixes the generated setup workflow for new dashboard repositories. Users who copied vA.B.C should copy the corrected workflow files from vA.B.D or recreate from the template.
```

## Compatibility Reset Procedure

Use only when supporting older templates is intentionally no longer viable.

Required steps:

1. Open a PR changing `minimum_compatible_template_version`.
2. Update `protected_template_refs`.
3. Explain why older templates are no longer supported.
4. Add migration guidance.
5. Add release notes under `## Template release notes`.
6. Run `make template-compat-e2e`.
7. Run `make template-release-gates`.
8. Use a SemVer bump appropriate to user impact. While the project is pre-public and remains on `v0`, a breaking reset does not require a major version bump.

Example:

```md
## Template release notes

Compatibility reset: this release raises the minimum compatible template version to vA.B.C. Older generated repositories should update their workflows and managed Reponomics docs before moving to action vX.Y.Z.
```

## Decision Rules

- Exact release tags are immutable.
- Source-repo template release tags are immutable.
- Published GitHub Releases are not edited as a recovery mechanism.
- Floating action refs may move to corrective releases.
- Generated template repo `main` may be force-pushed only by the publication workflow from an approved source release.
- If a bad generated template may have been copied, publish a corrective template patch release.
- If a bad action may affect existing users through floating refs, publish a corrective action patch release and move the floating refs.
- Do not move `minimum_compatible_template_version` in response to a bad release. Move it only for an intentional compatibility reset.
- Do not use manual publication as normal rollback. Use it only to recover publication from an already-approved release source.

## Minimum Maintainer Checklist During Incident

```sh
git fetch --tags origin
make validate-template-action-ref
make validate-template-accepted-action
make template-compat-e2e
make template-release-gates
```

Then verify:

- exact action tag SHA
- floating action refs
- template contract version
- accepted action metadata
- source-repo template release tag
- generated repo `Source-Commit`
- `.reponomics/template-provenance.json`

## Appendix: Tabletop Exercise Protocol

Run a release recovery tabletop before public beta and periodically after major release-process changes. The goal is to verify that maintainers can identify the failed layer, choose the correct recovery path, and name the release history that must remain immutable.

Use one or more scenarios:

1. Action release exists, but the template acceptance PR failed.
2. Template acceptance PR merged, but `template-release.yml` failed.
3. Template release exists, but `publish-template.yml` failed before generated publication.
4. Generated template publication completed with wrong provenance.
5. Action patch release breaks the minimum compatible protected template.
6. Template release gives new copied repositories broken setup.

For each scenario, record:

- the first command or workflow to inspect;
- the tag, SHA, PR, and workflow run identifiers needed for triage;
- whether the source is correct and the workflow should be rerun;
- whether a corrective action or template patch release is required;
- which exact tags/releases must not be moved or edited;
- any missing runbook step, permission, artifact, or provenance evidence.

Prefer tabletop review first. Use staging drills when the exercise needs to prove app permissions, generated publication, or copied-template smoke behavior. Do not create artificial production breakage for practice.
