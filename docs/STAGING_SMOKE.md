# Staging Smoke Protocol

This runbook defines the local, maintainer-operated smoke process for exercising generated dashboard repositories before public release. It complements CI and template publication gates; it does not replace them.

The goal is to prove that a real generated repository can be configured, collect data, publish outputs, rotate keys where applicable, and produce dashboards that a maintainer can inspect in a browser.

The smoke pass is orchestrated from the maintainer's local machine, usually by Codex running the Make targets in this source repository. GitHub Actions workflows are the system under test: the local smoke pass dispatches or supervises the generated staging workflows, waits for them, inspects their outputs, and records evidence. Do not treat this as a remote CI suite that runs unattended.

The first version is intentionally a guided interactive runbook, not a fully unattended smoke bot. Codex can run local checks, print commands, dispatch supervised workflows when approved, wait for workflow completion, and collect evidence. Secret entry, force-reset confirmation, and any other remote-writing checkpoint should remain explicit maintainer-approved steps.

## Staging Fleet

Use one generated-template staging repo and two private consumer staging repos at minimum:

| Repository | Role | Reset policy | Privacy mode | Expected outputs |
| --- | --- | --- | --- | --- |
| `reponomics-dashboard-staging` | Generated template staging surface | Force-pushed from source staging workflow | none | Template files only |
| `reponomics-dashboard-staging-private-encrypted-fresh` | Private encrypted consumer smoke | Force-push a fresh template-derived codebase for each smoke pass | `strong` | README dashboard, encrypted `dashboard-data`, encrypted Pages dashboard |
| `reponomics-dashboard-staging-private-plaintext-with-history` | Private plain consumer continuity smoke | Preserve repository and artifact history between smoke passes | `plain` | README dashboard, plain `dashboard-data`, private `html-dashboard-plain` artifact |

The encrypted/fresh repo proves the first-run codebase path. The repository itself is persistent: repository settings and Actions secrets remain configured between smoke passes, while the git tree/history is force-pushed back to a fresh generated-template state. The plain/history repo proves a durable private repository can keep accumulating real retained data over time.

A public encrypted consumer repo is also valuable before recommending public encrypted dashboards broadly, but it is a next-stage surface. A personal public encrypted dashboard can serve as a confidence signal; treat it as a real user repository, not as the minimum staging fleet.

## Product Boundaries

Plain mode does not publish a Pages dashboard. That is intentional. Plain-mode HTML is a private workflow artifact named `html-dashboard-plain`.

Public repositories must not use `privacy_mode: plain` and must not generate a README dashboard through the normal action runtime.

## Required Local Inputs

Before running a local Codex smoke pass, provide these values to the agent:

- GitHub owner, normally `reponomics`.
- Staging template repository, normally `reponomics/reponomics-dashboard-staging`.
- Encrypted fresh consumer repository, normally `reponomics/reponomics-dashboard-staging-private-encrypted-fresh`.
- Plain history consumer repository, normally `reponomics/reponomics-dashboard-staging-private-plaintext-with-history`.
- Collection PAT to configure as `COLLECTION_TOKEN` in each consumer repo.
- Strong dashboard key for encrypted mode.
- Temporary next dashboard key for rotation smoke.
- Comparison key, if comparison unlock behavior should be checked.
- Repository list or config changes that should be collected during this smoke pass.
- Whether the public demo should also be refreshed from `main`.

Do not paste long-lived secrets into tracked files. Provide them to the local automation session at run time and prefer `gh secret set` so they go directly to GitHub.

For the guided interactive pass, printed `gh secret set` commands omit `--body` so the GitHub CLI reads the secret from standard input instead of echoing it into the command line or transcript. If you later run a more automated pass, use local environment variables or a local untracked dotenv file and keep the values out of shell history, logs, and tracked files.

## One-Time GitHub Provisioning

Before the first live staging smoke pass:

- Create `reponomics-dashboard-staging` as a private repository. It may be empty before the first staging-template publication.
- Create `reponomics-dashboard-staging-private-encrypted-fresh` as a private repository. This repo is persistent, but its git tree/history is intentionally disposable; the smoke protocol force-pushes a fresh template-derived root history into it while retaining repository settings and secrets.
- Create `reponomics-dashboard-staging-private-plaintext-with-history` as a private repository. This repo is intentionally durable; do not reset it during ordinary smoke passes.
- Install the template staging publication app only where it needs access, currently `reponomics-dashboard-staging`, with `contents: write` and `workflows: write`.
- Configure `TEMPLATE_STAGING_PUBLISH_APP_CLIENT_ID` as a source-repository variable and `TEMPLATE_STAGING_PUBLISH_APP_PRIVATE_KEY` as a source-repository secret.
- Ensure the maintainer running local smoke has `gh` access sufficient to set consumer repo secrets, dispatch workflows, read workflow runs/artifacts, inspect Pages settings, and force-push only the encrypted-fresh repo.
- After the staging template is first published, run or inspect `make staging-smoke-preflight` again; it should then move from repository/bootstrap failures to consumer secret/workflow checks.

The local helper can plan or create the three private staging repositories:

```sh
make staging-smoke-provision-plan
make staging-smoke-provision
```

`staging-smoke-provision-plan` is read-only. `staging-smoke-provision` creates missing private repositories only. It does not install the publication app, set secrets, publish the generated template, force-push the encrypted-fresh repo, or run setup/collection workflows.

## Local Preflight

Run this before asking Codex to execute a live staging smoke pass:

```sh
make staging-smoke-preflight
```

The preflight is a readiness gate. On a brand-new staging fleet, it is expected to fail until the template has been published, consumer repos have been seeded, and required secrets have been configured.

The preflight checks:

- local `gh` authentication;
- source-repository staging publication app variable/secret names;
- staging and consumer repository accessibility;
- private visibility and `main` default branch;
- expected generated workflow files in the consumer repos;
- required consumer repository secret names for PAT collection mode.

The command does not print secret values. It only checks whether required secret names are configured. The first staging smoke protocol is PAT-only; evaluate GitHub App collection separately after the core staging loop is working.

Override repository names with `STAGING_SMOKE_TEMPLATE_REPO`, `STAGING_SMOKE_ENCRYPTED_REPO`, and `STAGING_SMOKE_PLAIN_REPO` if the staging fleet uses different names.

The staging helpers deliberately run slowly. `make staging-smoke-preflight`, `make staging-smoke-plan`, and `make staging-smoke-run` default to a one-second delay around GitHub CLI/API work. The smoke plan emits GitHub commands through `scripts/staging_smoke/slow_gh.py`, so commands copied from the plan are throttled too. Increase `STAGING_SMOKE_GH_DELAY_SECONDS` if a run is hitting secondary rate limits or if several agents are operating against the same repos:

```sh
make staging-smoke-run STAGING_SMOKE_GH_DELAY_SECONDS=3
```

Expected bootstrap blockers are:

- missing source-repository staging publication app variable/secret;
- staging template repository has no `main` branch until the first generated-template staging publication;
- encrypted fresh and plain history consumer repositories have no `main` branch until they are reset or seeded from the staging template;
- generated workflows are missing from the consumer repositories until they are reset or seeded;
- consumer repository secrets are missing until they are configured during the first live smoke pass.

## Local Smoke Driver

For a concise command sequence, start with:

```sh
make staging-smoke-live-order
```

Print the guarded execution plan without changing GitHub state:

```sh
make staging-smoke-plan
```

This also writes a starter smoke report to `.tmp/staging-smoke/report.md` by default. Override `STAGING_SMOKE_REPORT` to choose another local path.

The default phase is `recurring`, which assumes the staging repos and required secrets already exist. Use `STAGING_SMOKE_PHASE=bootstrap` for the first initialization pass or when intentionally reconfiguring persistent secrets:

```sh
make staging-smoke-plan STAGING_SMOKE_PHASE=bootstrap
make staging-smoke-plan STAGING_SMOKE_PHASE=recurring
```

Recurring mode does not prompt for persistent consumer secrets such as `COLLECTION_TOKEN` or `COMPARISON_SECRET`. It may still prompt for `DASHBOARD_NEXT_SECRET` and the promoted `DASHBOARD_SECRET_DO_NOT_REPLACE` during the key-rotation smoke because changing those secrets is the behavior being tested.

Secret provisioning and setup are separate steps. `gh secret set` writes repository Actions secrets; `setup.yml` consumes workflow inputs and existing secrets to write the generated dashboard config, README/setup marker, and related repository files.

## Local Clone Policy

Do not create persistent local clones for the staging template repo or the encrypted-fresh repo by default. The staging template repo is a generated publication surface, and the encrypted-fresh repo intentionally receives a fresh root history during smoke runs. Persistent local clones of either repo become stale quickly and increase the chance of editing or pushing from the wrong base.

Use temporary clones under `.tmp/staging-smoke/` when the smoke protocol needs to inspect or edit generated consumer state. A persistent local clone of the plain-history repo is acceptable if maintainers frequently edit its `config.yaml`, because that repo preserves history. Before editing that clone, fetch first and verify the branch, remote, and clean worktree.

Write a browser smoke checklist before beginning the interactive browser pass:

```sh
make staging-smoke-browser-checklist
```

The checklist defaults to `.tmp/staging-smoke/browser-checklist.md`. It records the encrypted Pages and local plain-artifact browser checks without asking the agent to store dashboard keys.

Run the local executable portion of the smoke pass:

```sh
make staging-smoke-run
```

`staging-smoke-run` runs preflight and the local template gates, then stops before dispatching the staging-template publication workflow. To also dispatch the staging publication workflow after local gates pass:

```sh
make staging-smoke-run DISPATCH_TEMPLATE_STAGING=1
```

Use the same phase selector for executable runs:

```sh
make staging-smoke-run STAGING_SMOKE_PHASE=bootstrap
make staging-smoke-run STAGING_SMOKE_PHASE=recurring
```

On the first empty-repository bootstrap pass, the readiness preflight will fail before the staging template has been published and before consumer repos have been seeded. If the failures are limited to the expected bootstrap checklist, use the explicit bootstrap override:

```sh
make staging-smoke-run STAGING_SMOKE_ALLOW_BOOTSTRAP=1
make staging-smoke-run STAGING_SMOKE_ALLOW_BOOTSTRAP=1 DISPATCH_TEMPLATE_STAGING=1
```

Do not use `STAGING_SMOKE_ALLOW_BOOTSTRAP=1` for ordinary recurring smoke passes. Once the staging fleet has `main` branches, generated workflows, and configured secret names, preflight failures should block the run.

The smoke driver does not silently force-reset consumer repositories or set secrets. It prints the remaining consumer-repository steps for Codex or the maintainer to execute deliberately, because those steps write to staging repositories and can overwrite the encrypted-fresh history.

Commands that dispatch generated staging workflows also include a local wait step. The wait step polls GitHub from the local machine, prints the workflow run URL and conclusion, and fails the local smoke command if the remote workflow fails.

Secret-setting commands are deliberately interactive in this first runbook. Do not run those commands in a non-interactive batch unless you have replaced them with an explicit local secret source.

The encrypted-fresh reset is guarded separately:

```sh
make staging-smoke-reset-fresh-plan
make staging-smoke-reset-fresh CONFIRM_TARGET=reponomics/reponomics-dashboard-staging-private-encrypted-fresh
```

`staging-smoke-reset-fresh-plan` prepares the fresh tree locally and does not push. `staging-smoke-reset-fresh` force-pushes only when `CONFIRM_TARGET` exactly matches `STAGING_SMOKE_ENCRYPTED_REPO`.

This reset affects the encrypted-fresh repository's git tree/history only. It does not recreate the repository, delete repository settings, or clear Actions secrets. Because the fresh tree no longer contains generated setup files such as `config.yaml` and `.reponomics/setup-complete`, the recurring smoke pass still runs `setup.yml` after the reset.

The plain-history seed is guarded separately:

```sh
make staging-smoke-seed-plain-history-plan
make staging-smoke-seed-plain-history CONFIRM_TARGET=reponomics/reponomics-dashboard-staging-private-plaintext-with-history
```

`staging-smoke-seed-plain-history-plan` prepares the seed tree only if the plain-history repo has no default branch. `staging-smoke-seed-plain-history` pushes without `--force` and exits without changing anything once the repo already has `main`.

After the live smoke steps have run, collect read-only evidence from both consumer repositories:

```sh
make staging-smoke-evidence
```

This checks private repo shape, required setup/config/managed-docs/README files, recent successful workflow runs, expected dashboard artifacts, encrypted Pages availability for the encrypted-fresh repo, and absence of Pages configuration for the plain-history repo. It does not prove browser behavior; browser unlock and chart checks still need an actual browser pass.

## Codex Automation Prompt

Use this as the local Codex task when you want an agent to run the smoke pass:

```text
Automation: Reponomics staging smoke

Repository: /Users/hesreallyhim/coding/projects/reponomics-action

Goal:
Run a manual staging smoke pass for the generated Reponomics dashboard template and two private consumer staging repos. Do not modify source code unless a smoke failure clearly requires a fix and I approve it. Use the current worktree and GitHub state as authoritative.

Staging template repo:
<owner/reponomics-dashboard-staging>

Encrypted fresh consumer repo:
<owner/reponomics-dashboard-staging-private-encrypted-fresh>

Plain history consumer repo:
<owner/reponomics-dashboard-staging-private-plaintext-with-history>

Inputs I will provide in the chat or terminal:
- collection PAT for `COLLECTION_TOKEN`
- DASHBOARD_SECRET_DO_NOT_REPLACE for encrypted mode
- DASHBOARD_NEXT_SECRET for rotation smoke
- COMPARISON_SECRET if needed
- config.yaml repository list or selection rules
- whether to refresh the public demo after the smoke pass

Protocol:
1. Inspect git status and confirm the source repo is on the intended branch/ref.
2. Run make staging-smoke-plan to review the intended smoke sequence and target repositories.
3. Run make staging-smoke-preflight. If this is the first bootstrap pass, use its failures as a checklist; otherwise resolve required failures before continuing.
4. Run local gates: make validate-workflows, make verify-workflow-classification, make build-template, make verify-template, make validate-template-action-ref, make template-smoke, make template-consumer-e2e, make publish-template-staging-dry-run. If this is the first empty-repository bootstrap pass and preflight failures match the expected bootstrap checklist, run the local gate driver with `STAGING_SMOKE_ALLOW_BOOTSTRAP=1`.
5. Confirm or run the staging template publication workflow for the intended source ref.
6. Reset the encrypted fresh consumer repo codebase from the staging template with `make staging-smoke-reset-fresh CONFIRM_TARGET=<exact encrypted fresh repo>`. This force-pushes the git tree/history only; repository settings and Actions secrets should persist. Do not preserve prior commits as evidence for this profile.
7. During bootstrap, configure encrypted fresh repo secrets and variables. During recurring smoke, rely on preflight to verify those persistent secrets exist. Run setup after each fresh codebase reset to write the generated repository config with privacy_mode=strong, generate_html_dashboard=true, generate_readme=true, use_github_app=false.
8. Review `config.yaml` in the encrypted fresh repo after setup. If this smoke pass should cover a specific repository set, commit that config change before running collect-and-publish with skip_collect=false.
9. Validate encrypted fresh outputs: setup marker, docs manifest, README dashboard, dashboard-data artifact, Pages deployment, docs/index.html and assets, collect/publish summaries, no unexpected workflow failures.
10. Run encrypted key rotation: set DASHBOARD_NEXT_SECRET, dispatch rotate-key with confirm_rotation=true, wait for completion, promote the next key into DASHBOARD_SECRET_DO_NOT_REPLACE, remove DASHBOARD_NEXT_SECRET, then run collect-and-publish again.
11. Run make staging-smoke-browser-checklist, then browser-test encrypted Pages dashboard with the active dashboard key. Confirm unlock succeeds, charts render, repo selector works, a non-traffic growth metric renders, a traffic metric does not appear clipped, and the collection calendar has expected statuses.
12. For the plain history repo, preserve existing history. If it is not initialized, seed it from the staging template once with `make staging-smoke-seed-plain-history CONFIRM_TARGET=<exact plain history repo>`. During bootstrap, configure the collection credential, then run setup to write config with privacy_mode=plain, generate_html_dashboard=false, generate_readme=true, and use_github_app=false.
13. During bootstrap, review `config.yaml` in the plain history repo after setup and commit any intended repository selection before the first retained-data run. During recurring smoke, preserve the existing config.
14. Run collect-and-publish on the plain history repo with skip_collect=false.
15. Validate plain history outputs: README dashboard, dashboard-data artifact containing retained plain data, html-dashboard-plain artifact, absent Pages configuration, docs manifest, and no unexpected workflow failures.
16. Download the plain html-dashboard-plain artifact locally and browser-test it from a temporary local HTTP server. Confirm charts render and the README/dashboard values are coherent with collected data.
17. Run doctor on both consumer repos using the latest successful collect/publish workflow run ID. Confirm doctor completes or report exact restore/validation failure.
18. Run make staging-smoke-evidence and resolve or record any required failures.
19. Produce a concise smoke report with source commit, template staging commit, consumer repo commits, workflow run URLs, artifacts observed, browser checks performed, failures, and follow-up recommendations.

Safety:
- Do not push to production template repo reponomics-dashboard.
- Do not delete the plain history repo or its artifacts.
- Only force-reset the encrypted fresh repo after explicitly confirming the target repo name.
- Never print secret values back into the transcript.
- Treat secret entry and force-reset/seed commands as guided interactive checkpoints, not unattended automation.
```

## Encrypted Fresh Smoke

The encrypted fresh smoke should start from a clean generated-template tree every time. Use `make staging-smoke-reset-fresh-plan` to verify the local fresh-root commit, then `make staging-smoke-reset-fresh CONFIRM_TARGET=reponomics/reponomics-dashboard-staging-private-encrypted-fresh` to force-push it. This is a codebase reset, not repository recreation; repository settings and Actions secrets persist.

During bootstrap, configure repository secrets:

- `COLLECTION_TOKEN`.
- `DASHBOARD_SECRET_DO_NOT_REPLACE`.
- `COMPARISON_SECRET`, if comparison unlock behavior is part of the pass.

For recurring smoke passes, do not re-enter these persistent secrets unless intentionally rotating or replacing them; preflight should verify that they already exist. Run `Set up Reponomics dashboard` after each fresh codebase reset with:

- `privacy_mode`: `strong`
- `generate_html_dashboard`: `true`
- `generate_readme`: `true`
- `use_github_app`: `false`

After setup, review `config.yaml` and commit any intended staging repository selection before collection. The encrypted-fresh codebase is reset every run, so recurring smoke must repeat this review if the desired repository set is not already the setup default.

Then run `Collect And Publish Reponomics Dashboard` with `skip_collect=false`.

Minimum checks:

- `.reponomics/setup-complete` exists in the repo.
- `config.yaml` reflects the requested mode and output settings.
- `docs/reponomics/.manifest.json` exists and names the expected action version.
- README dashboard was generated.
- `dashboard-data` artifact exists.
- encrypted Pages deployment exists and serves `docs/index.html`.
- browser unlock succeeds with the active dashboard key.
- repo selector, metric switching, focused repo view, comparison, and calendar all behave plausibly.

Rotation checks:

1. Set `DASHBOARD_NEXT_SECRET`.
2. Dispatch `Rotate Reponomics dashboard key` with `confirm_rotation=true`.
3. Confirm the rotation run succeeds.
4. Promote `DASHBOARD_NEXT_SECRET` into `DASHBOARD_SECRET_DO_NOT_REPLACE`.
5. Remove `DASHBOARD_NEXT_SECRET`.
6. Run collect/publish again.
7. Confirm the dashboard unlocks with the new key.

## Plain History Smoke

The plain history smoke should preserve the repository and artifact history. Seed it from `reponomics-dashboard-staging` only if it is empty:

```sh
make staging-smoke-seed-plain-history-plan
make staging-smoke-seed-plain-history CONFIRM_TARGET=reponomics/reponomics-dashboard-staging-private-plaintext-with-history
```

The seed helper refuses mismatched confirmation targets, pushes without `--force`, and treats an existing `main` branch as a no-op so the repo can accumulate real retained data across smoke passes.

Run setup with:

- `privacy_mode`: `plain`
- `generate_html_dashboard`: `false`
- `generate_readme`: `true`
- `use_github_app`: `false`

During bootstrap, review `config.yaml` and commit the intended staging repository selection before the first retained-data run. Recurring plaintext/history smoke should preserve the existing config unless the test intentionally changes the tracked repository set.

Then run `Collect And Publish Reponomics Dashboard` with `skip_collect=false`.

Minimum checks:

- README dashboard was generated.
- `dashboard-data` artifact exists and contains retained plain files.
- `html-dashboard-plain` artifact exists.
- Pages configuration must be absent.
- repeated runs preserve growing retained history within the configured retention window.
- doctor can restore the latest plain dashboard artifacts and run successfully.

For browser smoke, download `html-dashboard-plain`, serve it locally, and inspect it in a browser. This is deliberately not a hosted Pages check.

## Smoke Report

The local Codex run should finish with a report containing:

- source repo branch and commit;
- staging template commit and publication workflow run;
- encrypted fresh repo commit and workflow runs;
- plain history repo commit and workflow runs;
- setup, collect/publish, rotate-key, doctor results;
- artifacts observed for each repo;
- Pages URL for encrypted fresh;
- local artifact path used for plain browser smoke;
- `make staging-smoke-evidence` result;
- browser checklist path and status;
- browser checks performed;
- failures, suspected cause, and recommended next action.

Do not treat a smoke pass as successful if the browser checks were skipped. If browser automation is unavailable, mark that explicitly as incomplete rather than passing the smoke.
