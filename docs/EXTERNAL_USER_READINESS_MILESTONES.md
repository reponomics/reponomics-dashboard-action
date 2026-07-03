# External User Readiness Milestones

Status: pre-beta readiness plan

Scope: `reponomics-dashboard-action`, generated `reponomics-dashboard` template surface, generated demo surface, release operations, local validation gates, and owner-facing documentation.

## Executive Verdict

The codebase is technically substantial and the core local gates are healthy, but it is not ready to invite external users yet.

The main blocker is not ordinary test coverage. The runtime, template generator, release tooling, security checks, and demo generator all passed the local checks run during this audit. The remaining launch blockers are product-contract clarity, external-user onboarding, support/security policy, realistic copied-repository staging, and a small set of retained-data safety hardening items that matter because the product stores user metrics in workflow artifacts.

Recommended launch posture: invite only a narrow beta cohort after all P0 milestones are done, with explicit `v0` compatibility language, documented data-loss boundaries, and at least one fresh copied-repository smoke pass with retained evidence.

## State Snapshot

- Current branch during audit: `codex/pre-beta-roadmap`.
- Current source commit during audit: `61c5fbf1ec1c`.
- Default remote branch: `origin/main`.
- Worktree before and after validation: clean.
- Action version: `0.31.0` in `pyproject.toml` and `dashboard_action/run_modules/core.py`.
- Template version: `0.18.0` in `template-contract.yml`.
- Generated template action channel: `v0`, with accepted action `v0.31.0` at `7003fa1a04084448214f5097400788ab60d73622`.
- Repo-audit branch profile: `delivery`, because the goal is implementation readiness for outside users. The original branch scan surfaced several active candidates, but follow-up reconciliation found that the named implementation/design candidates were already squash-merged, superseded, or not launch contenders. `revise-docs` remains normal in-progress documentation work, not a separate launch-candidate branch decision.

## Validation Results

These checks passed locally during the audit:

| Check                         | Result | Notes                                                                                                                                                                                                         |
| ----------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `make ci`                     | Passed | 462 Python tests passed, 16 staging-smoke tests skipped, total Python coverage 90.69%.                                                                                                                        |
| `make security`               | Passed | No known Python vulnerabilities from local env or runtime lock; runtime and guide locks hash-installable; vendored assets validated.                                                                          |
| `make template-release-gates` | Passed | Workflow classification, template build, public action ref validation, accepted action release validation, template smoke, accepted-action e2e, publication dry-run, and template release package all passed. |
| `make js-coverage`            | Passed | 18 JS tests passed; JS line coverage reported 37.44%, so browser confidence still depends on smoke/snapshot/staging evidence.                                                                                 |
| `make js-smoke`               | Passed | Dashboard JS smoke script completed.                                                                                                                                                                          |
| `make verify-demo`            | Passed | Generated demo repository verified; synthetic encrypted seed built.                                                                                                                                           |
| `make publish-demo-dry-run`   | Passed | Demo publication target and expected repo guard passed in dry-run mode.                                                                                                                                       |

Important gap: the staging smoke test group is intentionally skipped because copied-repository staging is paused. This is recorded in `docs/STAGING_SMOKE.md`, `docs/VERSIONING_AND_RELEASE.md`, and `tests/test_generated_repos.py`.

## P0 Milestones

### 1. Make The Beta Channel Unmistakable

Problem: the external beta line is `v0`, but a root README versioning example can be read as current setup guidance if it appears in first-contact onboarding without enough context. `v1` should be presented as the future full public release line, not the beta install target.

Evidence:

- `README.md` describes `reponomics/reponomics-dashboard-action@v1` and `@v1.2.3` as versioning examples.
- `template/.github/actions/reponomics/action.yml` uses `reponomics/reponomics-dashboard-action@v0`.
- `template-contract.yml` records `compatible_action_major: 0`, `default_action_ref: v0`, and accepted action `0.31.0`.
- `docs/VERSIONING_AND_RELEASE.md` says the project is still on the `v0` compatibility line.

Required outcomes:

- State plainly that external beta uses the `v0` action line.
- Keep first-contact beta onboarding examples on `@v0` or an explicit `@v0.x.y` release.
- Move `v1` examples into versioning/release documentation, or label them as future stable-release examples rather than current setup instructions.
- Make the authoritative onboarding surfaces agree: root README quickstart/install examples, generated template README, managed getting-started docs, generated wrapper docs/comments, setup output or first-run instructions, beta invite/release notes, demo/promotional guide, and Marketplace-facing copy if used.
- Say plainly what compatibility is promised for external beta users before `v1`.

Done when:

- A new user sees `v0` as the beta setup channel across authoritative onboarding surfaces.
- Any `v1` examples are clearly labeled as future stable-release examples, not current beta installation guidance.
- Release notes explicitly state whether external beta users are on a compatibility commitment or a pre-commitment hardening line.

### 2. Rewrite The External Onboarding Path

Problem: the README markets a near-frictionless setup, but generated docs say the template is not intended for public use and the first-run path stops before a first dashboard is produced.

Evidence:

- `README.md` says the project is "easy to set up in five minutes" while also warning that it is not promoted for general use.
- `template/README.template.md` says setup does not collect immediately and waits for schedule.
- `template/.github/workflows/collect-and-publish.yml` supports manual dispatch, but the setup README does not clearly tell users to run the first collect-and-publish workflow after setup.
- `dashboard_action/runtime/managed_docs/config.example.yaml` references `DASHBOARD_ESSENTIALS.md` and misspelled `DASHBOARD_ESSENTIAILS.md`, while `dashboard-essentials.md` is effectively empty.

Required outcomes:

- Replace the current onboarding path with a tested sequence:
  1. Copy template.
  2. Edit and commit `config.yaml`.
  3. Set required secrets or app credentials.
  4. Run `Setup`.
  5. Configure Pages when enabled.
  6. Run `Collect and Publish` manually for the first dashboard.
  7. Verify README/Pages/artifacts.
  8. Run `Doctor` when verification fails.
- Add a short "who should join the beta" section: GitHub Actions-fluent maintainers, one GitHub owner or organization to start, encrypted mode preferred, roughly 1-30 repositories, at most 8 published repositories, and willingness to share diagnostic artifacts.
- Replace broken references and empty docs before generated template publication.

[OWNER: Agree with the recommended required outcomes. Disagre that the current state is incoherent - I'm working through the docs as I go, and telling users not to basically disregard them.]

Done when:

- A new external user can get from a copied template to a first dashboard without inferring any missing workflow step.
- The docs set expectations before secrets are created or artifacts are written.

### 3. Publish Real Support And Security Policies

Problem: external users need to know what is supported, where to report security problems, and what risks Reponomics does not assume. Current generated support/security documents are placeholders.

Evidence:

- `dashboard_action/runtime/managed_docs/support.md` says it does not define a support policy, availability promise, response timeline, maintenance commitment, or public-use readiness statement.
- `dashboard_action/runtime/managed_docs/security.md` says it is not a reporting channel.
- `template/SECURITY.template.md` is a placeholder.

[OWNER: This is the correct posture for post-beta. We do not offer a service, we mostly cannot help users with specific problems (we can address bugs and so forth), and even if the application made it possible we don't have the resources currently. This is correct though that I plan to offer different language to the beta group.]

Required outcomes:

- Define beta support scope, response expectations, communication channel, and triage data.
- Define the security disclosure channel and supported-version policy for action and template.
- State data-loss boundaries: artifact retention, dashboard secret loss, direct secret overwrite, incomplete key rotation, incident reset limits, and what Reponomics cannot recover.
- Link Doctor report artifacts and workflow run summaries as the primary support evidence.

Done when:

- No generated or managed security/support document says it is only a placeholder.
- A user can report a security issue without publishing secrets, dashboard keys, retained artifact contents, or exploit details in a public issue.

### 4. Restore A Lightweight Copied-Repository Staging Gate

Problem: local and release gates prove a lot, but they do not fully simulate a real copied dashboard repository with secrets, Pages settings, workflow artifacts, first-run setup, retention, rotation, and browser behavior. The repo already recognizes this gap, but the staging protocol is paused and its tests are skipped.

Evidence:

- `docs/STAGING_SMOKE.md` says the staging smoke effort is paused and not a live release gate.
- `docs/VERSIONING_AND_RELEASE.md` repeats that copied-repository smoke work is paused.
- `tests/test_generated_repos.py` skips staging-smoke assertions with `STAGING_SMOKE_PAUSED_REASON`.

Required outcomes:

- Resume a smaller staging protocol with the minimum useful fleet:
  - private encrypted fresh repo;
  - private plaintext history repo;
  - at least one public encrypted dashboard path before public encrypted dashboards are recommended broadly.
- Exercise setup, first collect, publish, Pages, README generation, artifact restore, key rotation, doctor, update-docs, and incident-reset preparation or a bounded non-destructive substitute.
- Include browser checks for unlock, chart load, export, lazy data chunks, and no obvious broken layout.
- Store a dated evidence report under an untracked or artifact path, then summarize the result in the release checklist.

Done when:

- A pre-invite candidate has a successful copied-repository smoke report.
- Browser checks are marked passed, not skipped.
- Any remote-writing steps have exact target guards and operator confirmation.

### 5. Harden Retained-State Race And Artifact Boundaries

Problem: multiple workflows can write the same retained `dashboard-data` surface, and artifact restore/extraction accepts broad artifact contents. These are pre-user hardening items because they affect user data continuity.

Evidence:

- `template/.github/workflows/collect-and-publish.yml` has a concurrency group.
- `template/.github/workflows/rotate-key.yml` and `template/.github/workflows/incident-reset.yml` do not have matching state concurrency.
- `action.yml` uploads `dashboard-data` for collect, rotate-key, and incident-reset modes.
- `dashboard_action/runtime/scripts/restore_artifact.sh` unzips the restored artifact directly into `DATA_DIR`.
- `dashboard_action/runtime/scripts/crypto_artifact.py` encrypts all non-`.enc` files found under `data_dir`, not only registered retained-data files.
- Collector modules still call `sys.exit(1)` from several submodules.

Required outcomes:

- Add a shared retained-state concurrency group across collect, publish, republish, rotate-key, incident-reset, doctor when it reads a just-produced artifact, and update-docs where relevant.
- Before uploading retained state, recheck latest parent or lineage to avoid last-writer-wins overwrites from overlapping workflow runs.
- Replace shell `unzip` restore with a Python extractor that rejects absolute paths, `..`, symlinks, hardlinks, device files, and unexpected archive members.
- Restrict encryption and retained lineage to registered artifact files.
- Convert collector `sys.exit` paths into typed exceptions handled by the top-level dispatcher.

Done when:

- A collect/rotate/reset overlap cannot silently overwrite a newer retained artifact.
- Restored and encrypted retained artifacts contain only expected files.
- Failure paths leave predictable summaries and do not bypass central output/error handling.

## P1 Milestones

### 6. Sync The Public Action Contract Across Metadata And Docs

Problem: `action.yml`, root README, generated wrapper, workflows, and managed docs do not expose the same public contract.

Evidence:

- `action.yml` exposes `comparison-secret`, `incident-confirm-next-secret`, and `doctor-report-path`.
- The README input/output tables omit at least some of those fields.
- Doctor emits a detailed report and upload path, but managed docs do not yet provide a practical failure-mode playbook.

Required outcomes:

- Generate or test the README input/output tables against `action.yml`.
- Document every public mode, input, output, permission, secret, artifact, and expected failure class.
- Add a managed troubleshooting guide for:
  - PAT scope and expiration;
  - GitHub App setup;
  - Pages source not set to GitHub Actions;
  - artifact expiry or missing `dashboard-data`;
  - wrong dashboard key;
  - incomplete rotation;
  - public/private data-mode rejection;
  - doctor report upload and interpretation.

Done when:

- `action.yml` and docs cannot drift silently.
- A beta support request can be routed to a documented doctor/troubleshooting step first.

### 7. Align Local, PR, Release, And Policy Gates

Problem: local `make ci` is healthy, but it is not the full GitHub CI/release surface. The project does have deeper gates, but they are spread across workflows and manual pre-release validation.

Evidence:

- `Makefile` `ci` runs lint, type-check, validate, test, and coverage.
- `.github/workflows/ci.yml` also runs dashboard scenario snapshots as a dedicated job, JS coverage, JS smoke, template gates, and the Python suite across 3.11, 3.12, and 3.13. Runtime-lock and vendored-asset validation are covered locally through `make validate`, but are also split into reusable CI jobs for clearer remote signal.
- `template-compat-e2e` is part of pre-release validation and release automation, but not the normal CI template job.
- `release-please.yml` preserves implicit release GitHub App token permissions.

Required outcomes:

- Add a local `make release-check` or `make prebeta-check` that matches external-user risk: CI aggregate, security, template-release gates, JS coverage/smoke, demo verify/dry-run, and compatibility e2e.
- Add `template-compat-e2e` or a cheaper equivalent to required PR/main validation for changes that touch action inputs, generated workflows, retained schemas, or template contracts.
- Add a repository policy preflight for CodeQL, Dependabot, branch protection, SHA-pin policy, immutable releases, required environments, and release app installation scopes.
- Make release app token permissions explicit where feasible, or add a workflow preflight that fails early when installation scopes are insufficient.

Done when:

- Maintainers can run one local command and know which remote-only checks remain.
- Release automation failures from missing app scopes or repository settings are caught before a public release or template publication is attempted.

### 8. Define The Generated-Repository SHA-Pinning Story

Problem: generated user workflows intentionally use floating/tag refs so users get compatible fixes. That is defensible, but external organizations with full-SHA policy need an official path.

Evidence:

- Source repository workflows and root `action.yml` use full-SHA-pinned third-party actions.
- Generated template workflows use refs such as `actions/checkout@v7`.
- Generated wrapper uses `reponomics/reponomics-dashboard-action@v0`.
- `docs/SECURITY_CHECKS.md` and `docs/DEPENDENCY_MANAGEMENT.md` explain this distinction for maintainers, but external-user guidance is not yet complete.

Required outcomes:

- Publish a generated-repo hardening guide for orgs that enforce full-SHA actions.
- Explain how to resolve the accepted action tag to a SHA using template provenance.
- State the tradeoff: SHA-pinned users own manual upgrades and may miss compatible fixes until they update.
- Consider a generated-template hardening variant or script that rewrites allowed refs to exact SHAs with provenance.

Done when:

- An organization with strict action pinning can adopt the beta without reverse-engineering the wrapper and provenance model.

### 9. Promote Demo And Promotional Assets To Beta-Grade

Problem: demo generation works, but the public showcase and promotional guide are not yet a complete onboarding bridge.

Evidence:

- `make verify-demo` and `make publish-demo-dry-run` passed.
- `docs/VERSIONING_AND_RELEASE.md` recommends moving daily demo refresh from `main` to a promoted stable ref at beta or wider public release.
- The promotional dashboard guide is not yet wired as a copy-template/live-demo/setup-checklist path.

Required outcomes:

- Decide whether demo follows `main`, `demo-stable`, or a release tag for beta.
- If beta users will see the demo, promote it only after staging checks pass.
- Add live demo, copy-template path, setup checklist, beta warning, known limits, and support links to promotional assets.

Done when:

- The demo cannot accidentally showcase unreleased or unvalidated behavior to external users.
- The promotional path helps users decide whether they are in the intended beta cohort.

## P2 Milestones

### 10. Reduce Runtime Coupling And Import Global State

The runtime still relies on bundled scripts inserted into `sys.path`, mutable module globals, and facade helpers for test patching. This is not an immediate launch blocker, but it increases the cost of future maintenance. Move gradually toward package imports and explicit context objects when touching these areas for other reasons.

### 11. Improve Browser-Side Coverage Where It Matters

JS module tests and smoke passed, but JS coverage is low and much of the browser confidence comes from generated snapshots. Before wider release, add focused tests for unlock/export failure modes, chunked data loading, dashboard controls, and mobile layout. Keep copied-repository browser smoke as the higher-value gate.

### 12. Clarify Python Package Intent

The Python package metadata is adequate for action development, but if the runtime is ever meant to be consumed outside the GitHub Action source archive, package metadata, entry points, and distribution posture need a separate pass. This is not required for a template/action beta.

## Recommended Invite Criteria

Invite external users only when all P0 milestones are complete and the highest-risk P1 items are either complete or deliberately deferred with user-facing disclosure.

Minimum criteria:

- Public channel is consistent (`v0` beta or `v1`, not both).
- External onboarding produces a first dashboard in a documented, tested path.
- Support and security policies are real, not placeholders.
- A copied-repository staging smoke pass has current evidence.
- Retained-state concurrency and artifact restore/encryption boundaries are hardened.
- Security, template release, demo, JS smoke, and compatibility gates pass on the launch candidate.
- Known limits are disclosed: repository caps, one collection credential, GitHub Actions artifact retention, Pages manual setup, encrypted/plaintext mode boundaries, and beta compatibility scope.

Suggested first cohort:

- Maintainers comfortable with GitHub Actions and repository secrets.
- One GitHub owner or organization per dashboard where possible.
- Curated portfolios of roughly 1-30 repositories, with no more than 8 published in the dashboard.
- Users willing to run Doctor and share diagnostic artifacts when support is needed.
- Users who understand that the beta may require coordinated migration if the `v0` contract changes.

## Appendix: Commands Run

```sh
git fetch --all --prune
python3 /Users/hesreallyhim/.codex/skills/repo-audit/scripts/branch_maturity.py --profile delivery --top 15
make ci
make security
make template-release-gates
make js-coverage
make js-smoke
make verify-demo
make publish-demo-dry-run
git status --short
```
